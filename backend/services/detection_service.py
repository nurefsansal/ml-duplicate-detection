from __future__ import annotations

import logging
import os
import time
from datetime import UTC, datetime
from typing import Any

import pandas as pd
from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload, sessionmaker

logger = logging.getLogger(__name__)

from src.db import create_db_engine
from backend.models.database import (
    DetectionRun,
    MatchCandidate,
    MaterializedDuplicateGroup,
    MaterializedDuplicateGroupMember,
    NormalizationRun,
    NormalizedRecord,
)
from backend.services.job_service import update_job_progress
from backend.schemas.requests import RecordIn
from backend.services.matching_service import (
    DEFAULT_MODEL_VERSION,
    extract_confidence,
    infer_match_type,
    run_matching,
)
from backend.services.scoring_app_settings import load_scoring_app_settings
from backend.services.normalization_persistence_service import (
    persist_normalization_pipeline,
)
from backend.services.normalization_service import (
    ADDRESS_COLUMN,
    CITY_COLUMN,
    EMAIL_COLUMN,
    MUHATAP_NO_COLUMN,
    NAME_COLUMN,
    PHONE_COLUMN,
    TC_COLUMN,
    build_column_mapping_definitions,
    canonicalize_upload_dataframe,
    metaphone_name_key,
    normalize_email_key,
    to_dataframe,
)

ENGINE = create_db_engine()
SessionLocal = sessionmaker(bind=ENGINE)

DEFAULT_DETECTION_THRESHOLD = 0.30
DETECTION_SYNC_MAX_RECORDS = int(os.getenv("DETECTION_SYNC_MAX_RECORDS", "50000"))
# Max normalized rows passed to a single Splink / matching run (packed bins).
DETECTION_MATCHING_BATCH_SIZE = int(os.getenv("DETECTION_MATCHING_BATCH_SIZE", "9000"))
# Oversized blocking_key buckets are split so that any pairwise merge uses at most this many rows.
DETECTION_MAX_MATCHING_ROWS = int(os.getenv("DETECTION_MAX_MATCHING_ROWS", "18000"))

_EMPTY_BLOCKING_SENTINEL = "__EMPTY__"


def _resolve_session_id(session_id: str | None) -> str:
    if session_id:
        return session_id
    return str(int(datetime.now(tz=UTC).timestamp() * 1000))


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def _normalise_mapping_key(value: str) -> str:
    text = str(value or "")
    for source, target in {
        "Ã…Â": "S",
        "Ã…Å¸": "s",
        "Å": "S",
        "ÅŸ": "s",
        "ÃƒÂ": "S",
        "ÃƒÂ¾": "s",
        "Ä": "G",
        "ÄŸ": "g",
        "Ãœ": "U",
        "Ã¼": "u",
        "Ã–": "O",
        "Ã¶": "o",
        "Ã‡": "C",
        "Ã§": "c",
        "Ä°": "I",
        "Ä±": "i",
    }.items():
        text = text.replace(source, target)
    return "".join(ch for ch in text.casefold() if ch.isalnum())


def _pick_mapping_value(*mappings: dict[str, Any], aliases: tuple[str, ...]) -> str:
    actual_keys: dict[str, str] = {}
    merged: dict[str, Any] = {}

    for mapping in mappings:
        if not isinstance(mapping, dict):
            continue
        merged.update(mapping)
        for key in mapping.keys():
            actual_keys[_normalise_mapping_key(key)] = key

    for alias in aliases:
        actual_key = actual_keys.get(_normalise_mapping_key(alias))
        if actual_key is None:
            continue
        value = _safe_str(merged.get(actual_key))
        if value:
            return value
    return ""


def _normalized_record_to_matching_row(record: NormalizedRecord) -> dict[str, Any]:
    normalized_payload = (
        record.normalized_payload if isinstance(record.normalized_payload, dict) else {}
    )
    raw_payload = (
        record.raw_record.raw_payload
        if record.raw_record is not None and isinstance(record.raw_record.raw_payload, dict)
        else {}
    )

    clean_name_ordered = _safe_str(
        normalized_payload.get("clean_name") or record.clean_name
    )
    clean_name = _safe_str(
        normalized_payload.get("canonical_name")
        or normalized_payload.get("ordered_name")
        or record.ordered_name
        or clean_name_ordered
    )
    clean_first_name = _safe_str(
        normalized_payload.get("first_name") or record.first_name
    )
    clean_surname = _safe_str(
        normalized_payload.get("last_name") or record.last_name
    )
    clean_email = _safe_str(
        normalized_payload.get("clean_email") or record.clean_email
    )

    return {
        NAME_COLUMN: _pick_mapping_value(
            normalized_payload,
            raw_payload,
            aliases=(NAME_COLUMN, "adSoyad", "name", "fullName", "full_name"),
        ),
        TC_COLUMN: _pick_mapping_value(
            normalized_payload,
            raw_payload,
            aliases=(TC_COLUMN, "tcKimlikNo", "tc", "identity", "idNumber"),
        ),
        PHONE_COLUMN: _pick_mapping_value(
            normalized_payload,
            raw_payload,
            aliases=(PHONE_COLUMN, "telefon", "phone", "mobile"),
        ),
        EMAIL_COLUMN: _pick_mapping_value(
            normalized_payload,
            raw_payload,
            aliases=(EMAIL_COLUMN, "email", "mail"),
        ),
        CITY_COLUMN: _pick_mapping_value(
            normalized_payload,
            raw_payload,
            aliases=(CITY_COLUMN, "Sehir", "Şehir", "sehir", "city"),
        ),
        ADDRESS_COLUMN: _pick_mapping_value(
            normalized_payload,
            raw_payload,
            aliases=(ADDRESS_COLUMN, "adres", "address"),
        ),
        MUHATAP_NO_COLUMN: _pick_mapping_value(
            normalized_payload,
            raw_payload,
            aliases=(MUHATAP_NO_COLUMN, "muhatap_no", "muhatap kodu", "customer_id", "donor_id"),
        ),
        "clean_name": clean_name,
        "clean_name_ordered": clean_name_ordered,
        "clean_first_name": clean_first_name,
        "clean_surname": clean_surname,
        "clean_tc": _safe_str(normalized_payload.get("clean_tc") or record.clean_tc),
        "clean_phone": _safe_str(
            normalized_payload.get("clean_phone") or record.clean_phone
        ),
        "clean_email": clean_email,
        "clean_city": _safe_str(
            normalized_payload.get("clean_city") or record.clean_city
        ),
        "clean_muhatap_no": _safe_str(
            normalized_payload.get("clean_muhatap_no")
            or (record.clean_muhatap_no if hasattr(record, "clean_muhatap_no") else "")
        ),
        "name_phonetic_key": _safe_str(
            normalized_payload.get("name_phonetic_key")
            or normalized_payload.get("name_phonetic")
            or record.name_phonetic
        ),
        "email_normalized_key": _safe_str(
            normalized_payload.get("email_normalized_key")
            or normalize_email_key(clean_email)
        ),
        "name_metaphone_key": _safe_str(
            normalized_payload.get("name_metaphone_key")
            or metaphone_name_key(clean_name)
        ),
        "blocking_key": _safe_str(
            normalized_payload.get("blocking_key") or record.blocking_key
        ),
        "is_valid": bool(
            normalized_payload.get("is_valid")
            if "is_valid" in normalized_payload
            else record.is_valid
        ),
        "normalized_record_id": int(record.id),
        "raw_id": int(record.raw_id),
        "upload_id": int(record.upload_id),
        "normalization_run_id": (
            int(record.normalization_run_id)
            if record.normalization_run_id is not None
            else None
        ),
    }


def _build_matching_dataframe(
    normalized_records: list[NormalizedRecord],
) -> tuple[pd.DataFrame, dict[int, int]]:
    rows = [_normalized_record_to_matching_row(record) for record in normalized_records]
    df_clean = pd.DataFrame(rows)
    index_to_normalized_id = {
        int(index): int(normalized_record_id)
        for index, normalized_record_id in enumerate(
            df_clean.get("normalized_record_id", pd.Series(dtype=int)).tolist()
        )
    }
    return df_clean, index_to_normalized_id


def _blocking_coalesce_expr():
    return func.coalesce(func.nullif(NormalizedRecord.blocking_key, ""), _EMPTY_BLOCKING_SENTINEL)


def _apply_normalized_scope(
    query,
    *,
    resolved_upload_id: int,
    resolved_normalization_run_id: int | None,
):
    if resolved_normalization_run_id is not None:
        return query.filter(
            NormalizedRecord.normalization_run_id == resolved_normalization_run_id
        )
    return query.filter(NormalizedRecord.upload_id == resolved_upload_id)


def _resolve_detection_scope_meta(
    *,
    session,
    upload_id: int | None,
    normalization_run_id: int | None,
    max_records: int,
    background_mode: bool,
) -> tuple[int, int | None, int]:
    """Resolve upload / normalization run and count rows without loading all NormalizedRecord rows."""
    t_scope = time.monotonic()
    if upload_id is None and normalization_run_id is None:
        raise HTTPException(
            status_code=400,
            detail="Mükerrer tespit için uploadId veya normalizationRunId zorunludur.",
        )

    resolved_upload_id = upload_id
    resolved_normalization_run_id = normalization_run_id

    if resolved_normalization_run_id is not None:
        normalization_run = (
            session.query(NormalizationRun)
            .filter(NormalizationRun.id == resolved_normalization_run_id)
            .first()
        )
        if normalization_run is None:
            raise HTTPException(
                status_code=404,
                detail=f"Normalizasyon çalışması bulunamadı: ID={resolved_normalization_run_id}",
            )
        resolved_upload_id = int(normalization_run.upload_id)
    elif resolved_upload_id is not None:
        latest_run = (
            session.query(NormalizationRun)
            .filter(NormalizationRun.upload_id == resolved_upload_id)
            .order_by(NormalizationRun.created_at.desc(), NormalizationRun.id.desc())
            .first()
        )
        if latest_run is not None:
            resolved_normalization_run_id = int(latest_run.id)

    count_query = session.query(NormalizedRecord.id)
    count_query = _apply_normalized_scope(
        count_query,
        resolved_upload_id=int(resolved_upload_id),
        resolved_normalization_run_id=resolved_normalization_run_id,
    )
    record_count = count_query.count()
    logger.info(
        "[detect] Scope count: uploadId=%s normalizationRunId=%s record_count=%d elapsed=%.2fs",
        resolved_upload_id,
        resolved_normalization_run_id,
        record_count,
        time.monotonic() - t_scope,
    )

    if record_count > max_records and not background_mode:
        logger.warning(
            "[detect] Sync limit exceeded: uploadId=%s normalizationRunId=%s record_count=%d limit=%d",
            resolved_upload_id,
            resolved_normalization_run_id,
            record_count,
            max_records,
        )
        raise HTTPException(
            status_code=413,
            detail="Bu veri seti senkron mükerrer tespit için çok büyük. Background job gereklidir.",
        )

    if record_count == 0:
        raise HTTPException(
            status_code=404,
            detail=(
                "Bu yükleme için normalize edilmiş kayıt bulunamadı. "
                "Önce Veri Normalizasyon adımını tamamlayın."
            ),
        )

    return int(resolved_upload_id), resolved_normalization_run_id, record_count


def _load_all_normalized_records(
    session,
    *,
    resolved_upload_id: int,
    resolved_normalization_run_id: int | None,
) -> list[NormalizedRecord]:
    query = session.query(NormalizedRecord).options(joinedload(NormalizedRecord.raw_record))
    query = _apply_normalized_scope(
        query,
        resolved_upload_id=resolved_upload_id,
        resolved_normalization_run_id=resolved_normalization_run_id,
    )
    return query.order_by(NormalizedRecord.id.asc()).all()


def _histogram_blocking_keys(
    session,
    *,
    resolved_upload_id: int,
    resolved_normalization_run_id: int | None,
) -> list[tuple[str, int]]:
    bk = _blocking_coalesce_expr()
    q = session.query(bk, func.count(NormalizedRecord.id))
    q = _apply_normalized_scope(
        q,
        resolved_upload_id=resolved_upload_id,
        resolved_normalization_run_id=resolved_normalization_run_id,
    )
    q = q.group_by(bk).order_by(func.count(NormalizedRecord.id).desc())
    return [(str(row[0] or _EMPTY_BLOCKING_SENTINEL), int(row[1])) for row in q.all()]


def _equal_chunk_offsets(total: int, num_chunks: int) -> list[tuple[int, int]]:
    if num_chunks <= 0:
        num_chunks = 1
    if total <= 0:
        return []
    base = total // num_chunks
    rem = total % num_chunks
    out: list[tuple[int, int]] = []
    pos = 0
    for i in range(num_chunks):
        sz = base + (1 if i < rem else 0)
        out.append((pos, sz))
        pos += sz
    return out


def _oversized_key_num_chunks(record_count: int, max_pair_rows: int) -> int:
    """Chunks for one blocking_key so any union of two chunks is at most max_pair_rows rows."""
    max_chunk = max(1, max_pair_rows // 2)
    return max(1, (record_count + max_chunk - 1) // max_chunk)


def _fetch_blocking_key_slice(
    session,
    *,
    resolved_upload_id: int,
    resolved_normalization_run_id: int | None,
    blocking_sentinel: str,
    offset: int,
    limit: int,
) -> list[NormalizedRecord]:
    q = session.query(NormalizedRecord).options(joinedload(NormalizedRecord.raw_record))
    q = _apply_normalized_scope(
        q,
        resolved_upload_id=resolved_upload_id,
        resolved_normalization_run_id=resolved_normalization_run_id,
    )
    if blocking_sentinel == _EMPTY_BLOCKING_SENTINEL:
        q = q.filter(
            or_(
                NormalizedRecord.blocking_key.is_(None),
                NormalizedRecord.blocking_key == "",
            )
        )
    else:
        q = q.filter(NormalizedRecord.blocking_key == blocking_sentinel)
    return (
        q.order_by(NormalizedRecord.id.asc()).offset(offset).limit(limit).all()
    )


def _fetch_records_for_blocking_keys(
    session,
    *,
    resolved_upload_id: int,
    resolved_normalization_run_id: int | None,
    blocking_sentinels: list[str],
) -> list[NormalizedRecord]:
    q = session.query(NormalizedRecord).options(joinedload(NormalizedRecord.raw_record))
    q = _apply_normalized_scope(
        q,
        resolved_upload_id=resolved_upload_id,
        resolved_normalization_run_id=resolved_normalization_run_id,
    )
    concrete = [k for k in blocking_sentinels if k != _EMPTY_BLOCKING_SENTINEL]
    has_empty = _EMPTY_BLOCKING_SENTINEL in blocking_sentinels
    conds = []
    if concrete:
        conds.append(NormalizedRecord.blocking_key.in_(concrete))
    if has_empty:
        conds.append(
            or_(
                NormalizedRecord.blocking_key.is_(None),
                NormalizedRecord.blocking_key == "",
            )
        )
    if not conds:
        return []
    if len(conds) == 1:
        q = q.filter(conds[0])
    else:
        q = q.filter(or_(*conds))
    return q.order_by(NormalizedRecord.id.asc()).all()


def _pack_small_blocking_keys(
    items: list[tuple[str, int]],
    batch_row_cap: int,
) -> list[list[str]]:
    """Greedy pack keys (each with count <= batch_row_cap) into bins with total rows <= batch_row_cap."""
    items = sorted(items, key=lambda x: -x[1])
    bins: list[list[str]] = []
    cur_keys: list[str] = []
    cur_sum = 0
    for key, c in items:
        if cur_sum + c > batch_row_cap and cur_keys:
            bins.append(cur_keys)
            cur_keys = [key]
            cur_sum = c
        else:
            cur_keys.append(key)
            cur_sum += c
    if cur_keys:
        bins.append(cur_keys)
    return bins


def _normalize_match_decision(value: Any) -> str:
    normalized = _safe_str(value).lower()
    if normalized in {"approved", "same_person"}:
        return "approved"
    if normalized in {"rejected", "different_person"}:
        return "rejected"
    return "pending"


def _edges_by_decision_from_duplicate_payloads(
    duplicates: list[dict[str, Any]],
    index_to_normalized_id: dict[int, int],
) -> dict[str, list[tuple[int, int, float]]]:
    decisions = ("pending", "approved", "rejected")
    edges_by_decision: dict[str, list[tuple[int, int, float]]] = {d: [] for d in decisions}
    for payload in duplicates:
        left_index = int(payload.get("left_index", -1))
        right_index = int(payload.get("right_index", -1))
        left_id = index_to_normalized_id.get(left_index)
        right_id = index_to_normalized_id.get(right_index)
        if left_id is None or right_id is None or left_id == right_id:
            continue
        if left_id > right_id:
            left_id, right_id = right_id, left_id
        dec = _normalize_match_decision(
            payload.get("decision") or payload.get("finalDecision")
        )
        score = float(extract_confidence(payload) or 0.0)
        edges_by_decision[dec].append((int(left_id), int(right_id), score))
    return edges_by_decision


def _edges_by_decision_from_match_candidates(
    session,
    detection_run_id: int,
) -> dict[str, list[tuple[int, int, float]]]:
    decisions = ("pending", "approved", "rejected")
    edges_by_decision: dict[str, list[tuple[int, int, float]]] = {d: [] for d in decisions}
    q = session.query(MatchCandidate).filter(MatchCandidate.detection_run_id == detection_run_id)
    for mc in q.yield_per(2000):
        left_id, right_id = int(mc.left_id), int(mc.right_id)
        if left_id == right_id:
            continue
        if left_id > right_id:
            left_id, right_id = right_id, left_id
        dec = _normalize_match_decision(mc.decision)
        conf = mc.confidence
        score = float(conf if conf is not None else (mc.score or 0.0))
        edges_by_decision[dec].append((left_id, right_id, score))
    return edges_by_decision


def _materialize_edges_by_decision(
    *,
    session,
    detection_run_id: int,
    upload_id: int,
    normalization_run_id: int | None,
    edges_by_decision: dict[str, list[tuple[int, int, float]]],
) -> int:
    decisions = ("pending", "approved", "rejected")
    inserted = 0

    for dec in decisions:
        edges = edges_by_decision.get(dec) or []
        if not edges:
            continue

        parent: dict[int, int] = {}

        def find(x: int) -> int:
            parent.setdefault(x, x)
            if parent[x] != x:
                parent[x] = find(parent[x])
            return parent[x]

        def union(a: int, b: int) -> None:
            parent.setdefault(a, a)
            parent.setdefault(b, b)
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for a, b, _score in edges:
            union(a, b)

        components: dict[int, set[int]] = {}
        for node in list(parent):
            root = find(node)
            components.setdefault(root, set()).add(node)
        member_lists = [sorted(m) for m in components.values() if len(m) >= 2]
        if not member_lists:
            continue

        all_record_ids = sorted({rid for members in member_lists for rid in members})
        muhatap_rows = (
            session.query(NormalizedRecord.id, NormalizedRecord.clean_muhatap_no)
            .filter(NormalizedRecord.id.in_(all_record_ids))
            .all()
        )
        muhatap_by_id = {int(rid): (_safe_str(code) or "") for rid, code in muhatap_rows}

        comp_key_by_node: dict[int, tuple[int, ...]] = {}
        scores_by_comp: dict[tuple[int, ...], list[float]] = {}
        edge_count_by_comp: dict[tuple[int, ...], int] = {}
        for members in member_lists:
            key = tuple(members)
            for rid in members:
                comp_key_by_node[rid] = key
            scores_by_comp[key] = []
            edge_count_by_comp[key] = 0

        for a, b, score in edges:
            comp_key = comp_key_by_node.get(a)
            if comp_key is None:
                continue
            scores_by_comp[comp_key].append(score)
            edge_count_by_comp[comp_key] += 1

        for members in member_lists:
            key = tuple(members)
            scores = scores_by_comp.get(key) or []
            match_count = int(edge_count_by_comp.get(key) or 0)
            avg_score = float(sum(scores) / len(scores)) if scores else 0.0
            max_score = float(max(scores)) if scores else 0.0

            codes = sorted({c for c in (muhatap_by_id.get(rid) for rid in members) if c})
            different_muhatap = len(codes) > 1

            group_key = "rec_" + "_".join(str(x) for x in members[:50])
            group = MaterializedDuplicateGroup(
                detection_run_id=detection_run_id,
                upload_id=upload_id,
                normalization_run_id=normalization_run_id,
                decision=dec,
                group_key=group_key,
                record_count=len(members),
                match_count=match_count,
                avg_score=avg_score,
                max_score=max_score,
                different_muhatap_code=different_muhatap,
                muhatap_codes=codes,
            )
            session.add(group)
            session.flush()

            session.bulk_save_objects(
                [
                    MaterializedDuplicateGroupMember(
                        group_id=int(group.id),
                        normalized_record_id=int(rid),
                    )
                    for rid in members
                ]
            )
            inserted += 1

    return inserted


def _compute_duplicate_groups_from_db(session, detection_run_id: int) -> tuple[int, int]:
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        parent.setdefault(x, x)
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(a: int, b: int) -> None:
        parent.setdefault(a, a)
        parent.setdefault(b, b)
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    q = session.query(MatchCandidate.left_id, MatchCandidate.right_id).filter(
        MatchCandidate.detection_run_id == detection_run_id
    )
    for left_id, right_id in q.yield_per(2000):
        if left_id == right_id:
            continue
        union(int(left_id), int(right_id))

    if not parent:
        return 0, 0

    groups: dict[int, set[int]] = {}
    for node in list(parent):
        root = find(node)
        groups.setdefault(root, set()).add(node)

    real_groups = {root: members for root, members in groups.items() if len(members) >= 2}
    return len(real_groups), sum(len(m) for m in real_groups.values())


def _resolve_detection_scope(
    *,
    session,
    upload_id: int | None,
    normalization_run_id: int | None,
) -> tuple[int, int | None, list[NormalizedRecord]]:
    resolved_upload_id = upload_id
    resolved_normalization_run_id = normalization_run_id

    if resolved_normalization_run_id is not None:
        normalization_run = (
            session.query(NormalizationRun)
            .filter(NormalizationRun.id == resolved_normalization_run_id)
            .first()
        )
        if normalization_run is None:
            raise HTTPException(
                status_code=404,
                detail=f"Normalizasyon çalışması bulunamadı: ID={resolved_normalization_run_id}",
            )
        resolved_upload_id = int(normalization_run.upload_id)
        logger.info(
            "[detect] normalizationRunId=%s → upload_id=%s",
            resolved_normalization_run_id,
            resolved_upload_id,
        )
    elif resolved_upload_id is not None:
        latest_run = (
            session.query(NormalizationRun)
            .filter(NormalizationRun.upload_id == resolved_upload_id)
            .order_by(NormalizationRun.created_at.desc(), NormalizationRun.id.desc())
            .first()
        )
        if latest_run is not None:
            resolved_normalization_run_id = int(latest_run.id)
            logger.info(
                "[detect] uploadId=%s → latest normalizationRunId=%s",
                resolved_upload_id,
                resolved_normalization_run_id,
            )
        else:
            logger.info(
                "[detect] uploadId=%s → no normalization run found, filtering by upload_id directly",
                resolved_upload_id,
            )
    else:
        raise HTTPException(
            status_code=400,
            detail="uploadId, normalizationRunId veya records alanlarından en az biri sağlanmalıdır.",
        )

    # Explicitly scoped query — never scans full normalized_records table
    query = session.query(NormalizedRecord).options(joinedload(NormalizedRecord.raw_record))
    if resolved_normalization_run_id is not None:
        query = query.filter(
            NormalizedRecord.normalization_run_id == resolved_normalization_run_id
        )
        logger.info(
            "[detect] Scope: normalized_records WHERE normalization_run_id=%s",
            resolved_normalization_run_id,
        )
    else:
        query = query.filter(NormalizedRecord.upload_id == resolved_upload_id)
        logger.info(
            "[detect] Scope: normalized_records WHERE upload_id=%s",
            resolved_upload_id,
        )

    normalized_records = query.order_by(NormalizedRecord.id.asc()).all()
    logger.info("[detect] Kapsam içi normalize kayıt sayısı: %d", len(normalized_records))

    if not normalized_records:
        raise HTTPException(
            status_code=404,
            detail=(
                "Bu yükleme için normalize edilmiş kayıt bulunamadı. "
                "Önce Veri Normalizasyon adımını tamamlayın."
            ),
        )

    return int(resolved_upload_id), resolved_normalization_run_id, normalized_records


def _compute_duplicate_groups(
    duplicates: list[dict[str, Any]],
    index_to_normalized_id: dict[int, int],
) -> tuple[int, int]:
    """Union-Find over the duplicate pairs to compute connected components.

    Returns (duplicate_group_count, affected_record_count).

    Example: pairs A-B, A-C, B-C → 1 group, 3 affected records.
    """
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        parent.setdefault(x, x)
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(a: int, b: int) -> None:
        parent.setdefault(a, a)
        parent.setdefault(b, b)
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for payload in duplicates:
        left_index = int(payload.get("left_index", -1))
        right_index = int(payload.get("right_index", -1))
        left_id = index_to_normalized_id.get(left_index)
        right_id = index_to_normalized_id.get(right_index)
        if left_id is not None and right_id is not None and left_id != right_id:
            union(left_id, right_id)

    if not parent:
        return 0, 0

    groups: dict[int, set[int]] = {}
    for node in list(parent):
        root = find(node)
        groups.setdefault(root, set()).add(node)

    real_groups = {root: members for root, members in groups.items() if len(members) >= 2}
    return len(real_groups), sum(len(m) for m in real_groups.values())


def _materialize_duplicate_groups(
    *,
    session,
    detection_run_id: int,
    upload_id: int,
    normalization_run_id: int | None,
    duplicates: list[dict[str, Any]],
    index_to_normalized_id: dict[int, int],
) -> int:
    """
    Persist duplicate groups so /admin/duplicate-groups can paginate at DB level.

    Best-effort: if tables are missing, caller should ignore failures.
    """
    edges_by_decision = _edges_by_decision_from_duplicate_payloads(
        duplicates, index_to_normalized_id
    )
    return _materialize_edges_by_decision(
        session=session,
        detection_run_id=detection_run_id,
        upload_id=upload_id,
        normalization_run_id=normalization_run_id,
        edges_by_decision=edges_by_decision,
    )


def _materialize_duplicate_groups_from_match_candidates(
    *,
    session,
    detection_run_id: int,
    upload_id: int,
    normalization_run_id: int | None,
) -> int:
    edges_by_decision = _edges_by_decision_from_match_candidates(session, detection_run_id)
    return _materialize_edges_by_decision(
        session=session,
        detection_run_id=detection_run_id,
        upload_id=upload_id,
        normalization_run_id=normalization_run_id,
        edges_by_decision=edges_by_decision,
    )


def _persist_match_candidates(
    *,
    session,
    detection_run_id: int,
    duplicates: list[dict[str, Any]],
    index_to_normalized_id: dict[int, int],
) -> int:
    inserted = 0

    for payload in duplicates:
        left_index = int(payload.get("left_index", -1))
        right_index = int(payload.get("right_index", -1))
        left_id = index_to_normalized_id.get(left_index)
        right_id = index_to_normalized_id.get(right_index)
        if left_id is None or right_id is None or left_id == right_id:
            continue
        # Canonical ordering to prevent (A,B) and (B,A) duplicates.
        if left_id > right_id:
            left_id, right_id = right_id, left_id

        confidence = extract_confidence(payload)
        persisted_decision = _normalize_match_decision(
            payload.get("decision") or payload.get("finalDecision")
        )
        # Deduplicate within the same detection run (same pair can appear via multiple sources).
        existing = (
            session.query(MatchCandidate.id)
            .filter(MatchCandidate.detection_run_id == detection_run_id)
            .filter(MatchCandidate.left_id == left_id)
            .filter(MatchCandidate.right_id == right_id)
            .first()
        )
        if existing is not None:
            continue
        session.add(
            MatchCandidate(
                detection_run_id=detection_run_id,
                left_id=left_id,
                right_id=right_id,
                score=confidence,
                match_type=infer_match_type(payload),
                decision=persisted_decision,
                confidence=confidence,
            )
        )
        inserted += 1

    session.flush()
    return inserted


def _build_batched_detection_work(
    histogram: list[tuple[str, int]],
    pack_row_cap: int,
    max_pair_rows: int,
) -> tuple[list[dict[str, Any]], dict[str, list[tuple[int, int]]]]:
    """Blocking-key batch plans: packed multi-key runs and oversized-key chunk pairs."""
    specs_by_key: dict[str, list[tuple[int, int]]] = {}
    plans: list[dict[str, Any]] = []
    small: list[tuple[str, int]] = []

    for key, cnt in histogram:
        if cnt > pack_row_cap:
            k = _oversized_key_num_chunks(cnt, max_pair_rows)
            specs = _equal_chunk_offsets(cnt, k)
            specs_by_key[key] = specs
            for i in range(k):
                for j in range(i, k):
                    plans.append({"kind": "oversized", "key": key, "i": i, "j": j})
        else:
            small.append((key, cnt))

    for bin_keys in _pack_small_blocking_keys(small, pack_row_cap):
        plans.append({"kind": "packed", "keys": bin_keys})

    return plans, specs_by_key


def run_detection_from_database(
    *,
    upload_id: int | None,
    normalization_run_id: int | None,
    min_rules_to_match: int,
    session_id: str | None,
    save_to_db: bool,
    job_id: int | None = None,
    background_mode: bool = False,
) -> dict[str, Any]:
    resolved_session_id = _resolve_session_id(session_id)
    session = SessionLocal()
    t_start = time.monotonic()

    logger.info(
        "[detect] Başlatıldı — uploadId=%s normalizationRunId=%s minRules=%s sessionId=%s",
        upload_id,
        normalization_run_id,
        min_rules_to_match,
        resolved_session_id,
    )

    try:
        if job_id is not None:
            update_job_progress(
                session,
                job_id=job_id,
                status="running",
                progress=5,
            )
            session.commit()

        resolved_upload_id, resolved_normalization_run_id, record_count = _resolve_detection_scope_meta(
            session=session,
            upload_id=upload_id,
            normalization_run_id=normalization_run_id,
            max_records=(10**9 if background_mode else DETECTION_SYNC_MAX_RECORDS),
            background_mode=background_mode,
        )

        use_batched = record_count > DETECTION_MATCHING_BATCH_SIZE
        normalized_records: list[NormalizedRecord] = []
        if not use_batched:
            normalized_records = _load_all_normalized_records(
                session,
                resolved_upload_id=resolved_upload_id,
                resolved_normalization_run_id=resolved_normalization_run_id,
            )

        logger.info(
            "[detect] Analiz edilecek kayıt sayısı: %d (upload_id=%s, normalization_run_id=%s) batched=%s",
            record_count,
            resolved_upload_id,
            resolved_normalization_run_id,
            use_batched,
        )
        if job_id is not None:
            update_job_progress(
                session,
                job_id=job_id,
                status="running",
                progress=20,
                total_rows=record_count,
                processed_rows=0 if use_batched else record_count,
            )
            session.commit()

        detection_run = None
        detection_run_id: int | None = None
        if save_to_db:
            detection_run = DetectionRun(
                upload_id=resolved_upload_id,
                normalization_run_id=resolved_normalization_run_id,
                model_version=DEFAULT_MODEL_VERSION,
                threshold=DEFAULT_DETECTION_THRESHOLD,
            )
            session.add(detection_run)
            session.flush()
            detection_run_id = int(detection_run.id)
            logger.info("[detect] DetectionRun olusturuldu: id=%s", detection_run_id)
        else:
            logger.info("[detect] saveToDb=false; detection_run ve match_candidates yazilmayacak.")

        t_match = time.monotonic()
        candidate_pairs = 0
        candidate_pairs_limited = False
        duplicate_pairs = 0
        duplicates_list: list[dict[str, Any]] = []
        inserted = 0
        resolved_model_version = DEFAULT_MODEL_VERSION
        duplicate_group_count = 0
        affected_record_count = 0

        if use_batched:
            logger.info(
                "[detect] Batched matching: pack_row_cap=%d max_pair_rows=%d",
                DETECTION_MATCHING_BATCH_SIZE,
                DETECTION_MAX_MATCHING_ROWS,
            )
            hist = _histogram_blocking_keys(
                session,
                resolved_upload_id=resolved_upload_id,
                resolved_normalization_run_id=resolved_normalization_run_id,
            )
            plans, specs_by_key = _build_batched_detection_work(
                hist,
                pack_row_cap=DETECTION_MATCHING_BATCH_SIZE,
                max_pair_rows=DETECTION_MAX_MATCHING_ROWS,
            )
            total_plans = max(len(plans), 1)
            if job_id is not None:
                update_job_progress(
                    session,
                    job_id=job_id,
                    status="running",
                    progress=30,
                    total_rows=record_count,
                    processed_rows=0,
                )
                session.commit()

            scoring_weights, decision_thresholds = load_scoring_app_settings(session)
            if job_id is not None:
                update_job_progress(
                    session,
                    job_id=job_id,
                    status="running",
                    progress=40,
                    total_rows=record_count,
                    processed_rows=0,
                )
                session.commit()

            for plan_idx, plan in enumerate(plans):
                if plan["kind"] == "packed":
                    recs = _fetch_records_for_blocking_keys(
                        session,
                        resolved_upload_id=resolved_upload_id,
                        resolved_normalization_run_id=resolved_normalization_run_id,
                        blocking_sentinels=plan["keys"],
                    )
                else:
                    specs = specs_by_key[plan["key"]]
                    i, j = int(plan["i"]), int(plan["j"])
                    off_i, lim_i = specs[i]
                    rows_i = _fetch_blocking_key_slice(
                        session,
                        resolved_upload_id=resolved_upload_id,
                        resolved_normalization_run_id=resolved_normalization_run_id,
                        blocking_sentinel=plan["key"],
                        offset=off_i,
                        limit=lim_i,
                    )
                    if i == j:
                        recs = rows_i
                    else:
                        off_j, lim_j = specs[j]
                        rows_j = _fetch_blocking_key_slice(
                            session,
                            resolved_upload_id=resolved_upload_id,
                            resolved_normalization_run_id=resolved_normalization_run_id,
                            blocking_sentinel=plan["key"],
                            offset=off_j,
                            limit=lim_j,
                        )
                        recs = rows_i + rows_j

                if len(recs) < 2:
                    if job_id is not None:
                        prog = 20 + int(70 * (plan_idx + 1) / total_plans)
                        update_job_progress(
                            session,
                            job_id=job_id,
                            status="running",
                            progress=min(prog, 89),
                            total_rows=record_count,
                            processed_rows=min(
                                record_count,
                                int(record_count * (plan_idx + 1) / total_plans),
                            ),
                        )
                        session.commit()
                    continue

                df_clean, index_to_normalized_id = _build_matching_dataframe(recs)
                batch_duplicates, resolved_model_version = run_matching(
                    df_clean=df_clean,
                    min_rules_to_match=min_rules_to_match,
                    scoring_weights=scoring_weights,
                    decision_thresholds=decision_thresholds,
                )
                del df_clean

                candidate_pairs += int(
                    getattr(batch_duplicates, "candidate_pairs", len(batch_duplicates))
                )
                candidate_pairs_limited = candidate_pairs_limited or bool(
                    getattr(batch_duplicates, "candidate_pairs_limited", False)
                )
                duplicate_pairs += int(
                    getattr(batch_duplicates, "duplicate_pairs", len(batch_duplicates))
                )

                if save_to_db and detection_run_id is not None:
                    inserted += _persist_match_candidates(
                        session=session,
                        detection_run_id=detection_run_id,
                        duplicates=list(batch_duplicates),
                        index_to_normalized_id=index_to_normalized_id,
                    )

                if job_id is not None:
                    prog = 20 + int(70 * (plan_idx + 1) / total_plans)
                    update_job_progress(
                        session,
                        job_id=job_id,
                        status="running",
                        progress=min(prog, 89),
                        total_rows=record_count,
                        processed_rows=min(
                            record_count,
                            int(record_count * (plan_idx + 1) / total_plans),
                        ),
                    )
                    session.commit()

            t_match_elapsed = time.monotonic() - t_match
            if detection_run is not None:
                detection_run.model_version = resolved_model_version

            logger.info(
                "[detect] Batched eşleştirme tamamlandı: %.2fs — model=%s — plans=%d aggCandidatePairs=%d",
                t_match_elapsed,
                resolved_model_version,
                len(plans),
                candidate_pairs,
            )
            if job_id is not None:
                update_job_progress(
                    session,
                    job_id=job_id,
                    status="running",
                    progress=70,
                    total_rows=record_count,
                    processed_rows=record_count,
                )
                session.commit()

            logger.info("[detect] MatchCandidate toplu akış: yeni satir=%d", inserted)

            if save_to_db and detection_run_id is not None:
                duplicate_pairs = int(
                    session.query(func.count(MatchCandidate.id))
                    .filter(MatchCandidate.detection_run_id == detection_run_id)
                    .scalar()
                    or 0
                )
                duplicate_group_count, affected_record_count = _compute_duplicate_groups_from_db(
                    session, detection_run_id
                )
            if job_id is not None:
                update_job_progress(
                    session,
                    job_id=job_id,
                    status="running",
                    progress=90,
                    total_rows=record_count,
                    processed_rows=record_count,
                )
                session.commit()

            logger.info(
                "[detect] Grup analizi (DB): %d grup, %d etkilenen kayıt",
                duplicate_group_count,
                affected_record_count,
            )

            if detection_run is not None:
                detection_run.duplicate_group_count = duplicate_group_count
                detection_run.affected_record_count = affected_record_count

            if save_to_db and detection_run_id is not None:
                try:
                    # Savepoint: missing DB tables or materialize errors must not poison the outer txn.
                    with session.begin_nested():
                        _materialize_duplicate_groups_from_match_candidates(
                            session=session,
                            detection_run_id=detection_run_id,
                            upload_id=resolved_upload_id,
                            normalization_run_id=resolved_normalization_run_id,
                        )
                except Exception as exc:
                    logger.warning("[detect] Group materialization skipped: %s", exc)
        else:
            df_clean, index_to_normalized_id = _build_matching_dataframe(normalized_records)
            if job_id is not None:
                update_job_progress(
                    session,
                    job_id=job_id,
                    status="running",
                    progress=30,
                    total_rows=record_count,
                    processed_rows=record_count,
                )
                session.commit()
            scoring_weights, decision_thresholds = load_scoring_app_settings(session)
            if job_id is not None:
                update_job_progress(
                    session,
                    job_id=job_id,
                    status="running",
                    progress=40,
                    total_rows=record_count,
                    processed_rows=record_count,
                )
                session.commit()
            duplicates, resolved_model_version = run_matching(
                df_clean=df_clean,
                min_rules_to_match=min_rules_to_match,
                scoring_weights=scoring_weights,
                decision_thresholds=decision_thresholds,
            )
            t_match_elapsed = time.monotonic() - t_match
            if detection_run is not None:
                detection_run.model_version = resolved_model_version

            duplicates_list = list(duplicates)
            candidate_pairs = int(getattr(duplicates, "candidate_pairs", len(duplicates)))
            candidate_pairs_limited = bool(
                getattr(duplicates, "candidate_pairs_limited", False)
            )
            duplicate_pairs = int(getattr(duplicates, "duplicate_pairs", len(duplicates)))
            logger.info(
                "[detect] Eşleştirme tamamlandı: %.2fs — model=%s — candidatePairs=%d duplicatePairs=%d",
                t_match_elapsed,
                resolved_model_version,
                candidate_pairs,
                duplicate_pairs,
            )
            if job_id is not None:
                update_job_progress(
                    session,
                    job_id=job_id,
                    status="running",
                    progress=70,
                    processed_rows=len(normalized_records),
                )
                session.commit()

            if save_to_db and detection_run_id is not None:
                inserted = _persist_match_candidates(
                    session=session,
                    detection_run_id=detection_run_id,
                    duplicates=duplicates_list,
                    index_to_normalized_id=index_to_normalized_id,
                )
                logger.info("[detect] MatchCandidate kaydedildi: %d satir", inserted)
            else:
                logger.info("[detect] saveToDb=false; MatchCandidate insert atlandi.")
            if job_id is not None:
                update_job_progress(
                    session,
                    job_id=job_id,
                    status="running",
                    progress=90,
                    processed_rows=len(normalized_records),
                )
                session.commit()

            duplicate_group_count, affected_record_count = _compute_duplicate_groups(
                duplicates_list, index_to_normalized_id
            )
            logger.info(
                "[detect] Grup analizi: %d grup, %d etkilenen kayıt",
                duplicate_group_count,
                affected_record_count,
            )

            if detection_run is not None:
                detection_run.duplicate_group_count = duplicate_group_count
                detection_run.affected_record_count = affected_record_count

            if save_to_db and detection_run_id is not None:
                try:
                    with session.begin_nested():
                        _materialize_duplicate_groups(
                            session=session,
                            detection_run_id=detection_run_id,
                            upload_id=resolved_upload_id,
                            normalization_run_id=resolved_normalization_run_id,
                            duplicates=duplicates_list,
                            index_to_normalized_id=index_to_normalized_id,
                        )
                except Exception as exc:
                    logger.warning("[detect] Group materialization skipped: %s", exc)

        if save_to_db:
            session.commit()
        if job_id is not None:
            update_job_progress(
                session,
                job_id=job_id,
                status="completed",
                progress=100,
                processed_rows=record_count,
            )
            session.commit()

        t_total = time.monotonic() - t_start
        logger.info("[detect] Toplam süre: %.2fs", t_total)

        return {
            "sessionId": resolved_session_id,
            "jobId": job_id,
            "uploadId": resolved_upload_id,
            "normalizationRunId": resolved_normalization_run_id,
            "detectionRunId": detection_run_id,
            "candidatePairs": candidate_pairs,
            "candidatePairsLimited": candidate_pairs_limited,
            "duplicatePairs": duplicate_pairs,
            "duplicateGroupCount": duplicate_group_count,
            "affectedRecordCount": affected_record_count,
            "insertedRows": inserted,
            "totalRecords": record_count,
            "duplicates": duplicates_list,
        }
    except HTTPException as exc:
        session.rollback()
        # For large datasets, the API route may fallback to a background job.
        # Don't mark the job as failed on the initial 413; let the background worker update it.
        if job_id is not None and getattr(exc, "status_code", None) != 413:
            update_job_progress(
                session,
                job_id=job_id,
                status="failed",
                error_message=str(getattr(exc, "detail", None) or "Detection failed with HTTPException"),
            )
            session.commit()
        raise
    except Exception as exc:
        session.rollback()
        logger.exception("[detect] Hata: %s", exc)
        if job_id is not None:
            update_job_progress(
                session,
                job_id=job_id,
                status="failed",
                error_message=str(exc),
            )
            session.commit()
        raise HTTPException(
            status_code=500, detail=f"Tespit sırasında hata oluştu: {exc}"
        ) from exc
    finally:
        session.close()


def detect_core(
    *,
    records: list[RecordIn],
    min_rules_to_match: int,
    save_to_db: bool,
    session_id: str | None,
    upload_id: int | None = None,
    normalization_run_id: int | None = None,
    job_id: int | None = None,
    background_mode: bool = False,
) -> dict[str, Any]:
    if normalization_run_id is not None or upload_id is not None:
        return run_detection_from_database(
            upload_id=upload_id,
            normalization_run_id=normalization_run_id,
            min_rules_to_match=min_rules_to_match,
            session_id=session_id,
            save_to_db=save_to_db,
            job_id=job_id,
            background_mode=background_mode,
        )

    # In-memory /detect: persist a lightweight normalization run, then detect via DB pipeline.
    resolved_session_id = _resolve_session_id(session_id)
    df_original = pd.DataFrame(
        [
            {
                "Ad Soyad": _safe_str(r.adSoyad),
                "TC Kimlik No": _safe_str(r.tcKimlikNo),
                "Telefon": _safe_str(r.telefon),
                "E-posta": _safe_str(r.email),
                "Şehir": _safe_str(r.sehir),
                "Adres": _safe_str(getattr(r, "adres", "")),
            }
            for r in (records or [])
        ]
    )
    if df_original.empty:
        raise HTTPException(status_code=400, detail="Detect için records alanı zorunludur.")

    try:
        df_processing = canonicalize_upload_dataframe(df_original)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    mapping_definitions = build_column_mapping_definitions([str(c) for c in df_original.columns])
    normalization_result = persist_normalization_pipeline(
        original_df=df_original,
        processing_df=df_processing,
        source_type="api_records",
        source_name="api_records",
        file_name="api_records",
        created_by="api_detect",
        upload_id=None,
        mapping_definitions=mapping_definitions,
    )

    return run_detection_from_database(
        upload_id=int(normalization_result["uploadId"]),
        normalization_run_id=int(normalization_result["normalizationRunId"]),
        min_rules_to_match=min_rules_to_match,
        session_id=resolved_session_id,
        save_to_db=save_to_db,
        job_id=job_id,
        background_mode=background_mode,
    )


def detect_file_dataframe(
    *,
    df_original: pd.DataFrame,
    file_name: str,
    source_type: str,
    min_rules_to_match: int,
    save_to_db: bool,
    session_id: str | None,
    upload_id: int | None = None,
    job_id: int | None = None,
) -> dict[str, Any]:
    resolved_session_id = _resolve_session_id(session_id)
    mapping_definitions = build_column_mapping_definitions(
        [str(column) for column in df_original.columns]
    )

    try:
        df_processing = canonicalize_upload_dataframe(df_original)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    normalization_result = persist_normalization_pipeline(
        original_df=df_original,
        processing_df=df_processing,
        source_type=source_type,
        source_name=file_name,
        file_name=file_name,
        created_by="api_detect_file",
        upload_id=upload_id,
        mapping_definitions=mapping_definitions,
    )

    return run_detection_from_database(
        upload_id=int(normalization_result["uploadId"]),
        normalization_run_id=int(normalization_result["normalizationRunId"]),
        min_rules_to_match=min_rules_to_match,
        session_id=resolved_session_id,
        save_to_db=save_to_db,
        job_id=job_id,
    )
