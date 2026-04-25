from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

TARGET_FIELDS = [
    "name",
    "first_name",
    "last_name",
    "phone",
    "email",
    "tc",
    "city",
    "address",
    "external_record_id",
    "birth_date",
    "country",
    "district",
    "ignored",
]

_ALIASES: dict[str, list[str]] = {
    "name": [
        "ad soyad",
        "isim soyisim",
        "isim",
        "full_name",
        "name",
        "donor_name",
        "muhatap",
        "muhatap adı",
        "musteri adı",
        "bağışçı adı",
    ],
    "phone": ["telefon", "telefon no", "gsm", "cep", "mobile", "phone", "tel"],
    "email": ["email", "e-mail", "eposta", "e-posta", "mail"],
    "tc": [
        "tc",
        "tckn",
        "tc kimlik",
        "tc kimlik no",
        "kimlik no",
        "identity",
        "national id",
    ],
    "city": ["şehir", "sehir", "il", "city"],
    "address": ["adres", "address", "açık adres", "acik adres"],
    "external_record_id": [
        "bağışçı no",
        "bagisci no",
        "donor id",
        "donor_no",
        "muhatap no",
        "müşteri no",
        "customer id",
    ],
}


def _normalize_key(value: str) -> str:
    value = (value or "").strip().lower()
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _get_table_columns(db: Session, table_name: str) -> set[str]:
    rows = db.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :table_name
            """
        ),
        {"table_name": table_name},
    ).fetchall()
    return {str(row[0]) for row in rows}


def _extract_columns_from_json_payload(payload: Any) -> list[str]:
    if isinstance(payload, dict):
        return [str(key) for key in payload.keys()]
    return []


def get_source_columns_for_upload(db: Session, upload_id: int) -> list[str]:
    source_columns: set[str] = set()

    table_columns = _get_table_columns(db, "raw_records")
    if table_columns:
        data_column = "raw_payload" if "raw_payload" in table_columns else "payload" if "payload" in table_columns else None
        if data_column:
            row = db.execute(
                text(f"SELECT {data_column} FROM raw_records WHERE upload_id = :upload_id ORDER BY id ASC LIMIT 1"),
                {"upload_id": upload_id},
            ).fetchone()
            if row:
                source_columns.update(_extract_columns_from_json_payload(row[0]))

    donor_columns = _get_table_columns(db, "raw_donors")
    if donor_columns:
        selected = [c for c in ["full_name", "phone", "email", "city"] if c in donor_columns]
        extra_col = "extra_fields" if "extra_fields" in donor_columns else None
        select_clause = ", ".join(selected + ([extra_col] if extra_col else []))
        if select_clause:
            row = db.execute(
                text(
                    f"SELECT {select_clause} FROM raw_donors "
                    "WHERE upload_id = :upload_id ORDER BY id ASC LIMIT 1"
                ),
                {"upload_id": upload_id},
            ).fetchone()
            if row:
                for col in selected:
                    value = getattr(row, col, None)
                    if value not in (None, ""):
                        source_columns.add(col)
                if extra_col:
                    source_columns.update(_extract_columns_from_json_payload(getattr(row, extra_col, None)))

    return sorted(source_columns)


def suggest_mappings(db: Session, upload_id: int) -> dict[str, Any]:
    source_columns = get_source_columns_for_upload(db, upload_id)
    normalized_alias_map: dict[str, str] = {}
    for field_name, aliases in _ALIASES.items():
        for alias in aliases:
            normalized_alias_map[_normalize_key(alias)] = field_name

    suggestions: list[dict[str, Any]] = []
    for source_col in source_columns:
        normalized_source = _normalize_key(source_col)
        target = normalized_alias_map.get(normalized_source)
        if target:
            suggestions.append(
                {
                    "sourceColumnName": source_col,
                    "targetFieldName": target,
                    "confidence": 0.95,
                    "mappingType": "direct",
                }
            )
            continue

        for alias_key, alias_target in normalized_alias_map.items():
            if alias_key and (alias_key in normalized_source or normalized_source in alias_key):
                suggestions.append(
                    {
                        "sourceColumnName": source_col,
                        "targetFieldName": alias_target,
                        "confidence": 0.8,
                        "mappingType": "heuristic",
                    }
                )
                break

    return {
        "uploadId": upload_id,
        "sourceColumns": source_columns,
        "suggestions": suggestions,
    }


def get_mappings(db: Session, upload_id: int) -> dict[str, Any]:
    cols = _get_table_columns(db, "column_mappings")
    if not cols:
        return {"uploadId": upload_id, "sourceColumns": [], "suggestions": []}

    select_cols = [c for c in ["source_column_name", "target_field_name", "confidence", "mapping_type"] if c in cols]
    rows = db.execute(
        text(
            f"SELECT {', '.join(select_cols)} FROM column_mappings "
            "WHERE upload_id = :upload_id ORDER BY id ASC"
        ),
        {"upload_id": upload_id},
    ).fetchall()

    suggestions = []
    for row in rows:
        suggestions.append(
            {
                "sourceColumnName": getattr(row, "source_column_name", ""),
                "targetFieldName": getattr(row, "target_field_name", ""),
                "confidence": float(getattr(row, "confidence", 1.0) or 1.0),
                "mappingType": getattr(row, "mapping_type", "manual") or "manual",
            }
        )

    source_columns = [str(item["sourceColumnName"]) for item in suggestions if item.get("sourceColumnName")]
    return {"uploadId": upload_id, "sourceColumns": source_columns, "suggestions": suggestions}


def save_mappings(db: Session, upload_id: int, mappings: list[dict[str, Any]], replace_existing: bool = True) -> dict[str, Any]:
    cols = _get_table_columns(db, "column_mappings")
    if not cols:
        raise ValueError("column_mappings table not found")

    if replace_existing:
        db.execute(text("DELETE FROM column_mappings WHERE upload_id = :upload_id"), {"upload_id": upload_id})

    insertable_cols = [c for c in ["upload_id", "source_column_name", "target_field_name", "confidence", "mapping_type"] if c in cols]
    if {"upload_id", "source_column_name", "target_field_name"} - set(insertable_cols):
        raise ValueError("column_mappings columns are incompatible")

    values_sql = ", ".join(insertable_cols)
    params_sql = ", ".join(f":{col}" for col in insertable_cols)
    stmt = text(f"INSERT INTO column_mappings ({values_sql}) VALUES ({params_sql})")

    for item in mappings:
        payload = {
            "upload_id": upload_id,
            "source_column_name": item.get("sourceColumnName", ""),
            "target_field_name": item.get("targetFieldName", ""),
            "confidence": item.get("confidence", 1.0),
            "mapping_type": item.get("mappingType", "manual"),
        }
        db.execute(stmt, {k: v for k, v in payload.items() if k in insertable_cols})

    db.commit()
    return get_mappings(db, upload_id)


def get_target_fields() -> list[str]:
    return TARGET_FIELDS[:]


def get_raw_rows_for_upload(db: Session, upload_id: int) -> list[dict[str, Any]]:
    pairs = get_raw_record_rows_for_upload(db, upload_id)
    return [payload for _, payload in pairs]


def get_raw_record_rows_for_upload(db: Session, upload_id: int) -> list[tuple[int | None, dict[str, Any]]]:
    table_columns = _get_table_columns(db, "raw_records")
    if table_columns:
        data_col = "raw_payload" if "raw_payload" in table_columns else "payload" if "payload" in table_columns else None
        if data_col:
            has_id = "id" in table_columns
            select_sql = f"id, {data_col}" if has_id else data_col
            rows = db.execute(
                text(
                    f"SELECT {select_sql} FROM raw_records WHERE upload_id = :upload_id ORDER BY id ASC"
                ),
                {"upload_id": upload_id},
            ).fetchall()
            out: list[tuple[int | None, dict[str, Any]]] = []
            for row in rows:
                if has_id:
                    rid = int(row[0]) if row[0] is not None else None
                    payload = row[1]
                else:
                    rid = None
                    payload = row[0]
                if isinstance(payload, dict):
                    out.append((rid, payload))
            return out

    donor_columns = _get_table_columns(db, "raw_donors")
    if donor_columns:
        rows = db.execute(
            text(
                "SELECT full_name, phone, email, city, extra_fields "
                "FROM raw_donors WHERE upload_id = :upload_id ORDER BY id ASC"
            ),
            {"upload_id": upload_id},
        ).fetchall()
        out2: list[tuple[int | None, dict[str, Any]]] = []
        for row in rows:
            item: dict[str, Any] = {}
            extra = getattr(row, "extra_fields", None)
            if isinstance(extra, dict):
                item.update(extra)
            item.setdefault("full_name", getattr(row, "full_name", "") or "")
            item.setdefault("phone", getattr(row, "phone", "") or "")
            item.setdefault("email", getattr(row, "email", "") or "")
            item.setdefault("city", getattr(row, "city", "") or "")
            out2.append((None, item))
        return out2

    return []


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if hasattr(value, "item") and callable(getattr(value, "item")):
        try:
            return value.item()
        except Exception:
            return str(value)
    return value


def _is_blank_scalar(val: Any) -> bool:
    if val is None:
        return True
    if isinstance(val, float) and val != val:
        return True
    if isinstance(val, str) and not val.strip():
        return True
    return False


def get_value(row: dict[str, Any], *possible_keys: str) -> Any:
    """First non-blank value from row for any of the given keys (snake_case or source labels)."""
    for key in possible_keys:
        if key not in row:
            continue
        val = row[key]
        if _is_blank_scalar(val):
            continue
        return val
    return None


def _phone_last7_from_row(row: dict[str, Any]) -> str | None:
    v = get_value(row, "phone_last7", "phone_last_7")
    if v is not None:
        s = str(v).strip()
        return s or None
    phone = get_value(row, "clean_phone", "Telefon")
    if phone is None:
        return None
    digits = re.sub(r"\D", "", str(phone))
    if not digits:
        return None
    return digits[-7:] if len(digits) >= 7 else digits


def _add_structured_normalized_columns(
    insert_fields: dict[str, Any], rec_cols: set[str], norm_dict: dict[str, Any]
) -> None:
    """Populate denormalized columns on normalized_records when those columns exist."""

    def put_text(col: str, val: Any) -> None:
        if col not in rec_cols or val is None:
            return
        s = str(val).strip()
        if not s:
            return
        insert_fields[col] = s

    put_text(
        "clean_name",
        get_value(norm_dict, "clean_name", "clean_name_ordered")
        or get_value(norm_dict, "Ad Soyad"),
    )
    put_text("first_name", get_value(norm_dict, "first_name", "clean_first_name"))
    put_text("last_name", get_value(norm_dict, "last_name", "clean_surname", "clean_last_name"))
    put_text("ordered_name", get_value(norm_dict, "ordered_name", "clean_name_ordered"))
    put_text(
        "ordered_normalized_name",
        get_value(norm_dict, "ordered_normalized_name", "ordered_name", "clean_name_ordered"),
    )
    put_text("clean_phone", get_value(norm_dict, "clean_phone", "Telefon"))
    put_text("phone_last7", _phone_last7_from_row(norm_dict))
    put_text("clean_email", get_value(norm_dict, "clean_email", "E-mail"))
    put_text("clean_tc", get_value(norm_dict, "clean_tc", "TC"))
    put_text("clean_city", get_value(norm_dict, "clean_city", "Şehir"))
    put_text("clean_address", get_value(norm_dict, "clean_address", "Adres"))
    put_text("external_record_id", get_value(norm_dict, "external_record_id"))


def persist_upload_normalization_results(
    db: Session,
    upload_id: int,
    normalized_rows: list[dict[str, Any]],
    raw_row_ids: list[int | None],
    *,
    success_count: int,
    failed_count: int,
) -> int | None:
    """
    If normalization_runs / normalized_records tables exist with compatible columns,
    replace normalized rows for this upload and return the new normalization_run id.
    Otherwise no-op and return None.
    """
    run_cols = _get_table_columns(db, "normalization_runs")
    rec_cols = _get_table_columns(db, "normalized_records")
    if not rec_cols or "upload_id" not in rec_cols:
        return None

    payload_col = next(
        (c for c in ("normalized_payload", "payload", "data", "normalized_data", "record") if c in rec_cols),
        None,
    )
    if not payload_col:
        return None

    total_in = success_count + failed_count
    run_id: int | None = None

    try:
        if run_cols and "upload_id" in run_cols:
            run_payload: dict[str, Any] = {}
            if "upload_id" in run_cols:
                run_payload["upload_id"] = upload_id
            if "status" in run_cols:
                run_payload["status"] = "completed"
            for col in ("total_records", "records_total", "input_count", "record_count", "total_input"):
                if col in run_cols:
                    run_payload[col] = total_in
                    break
            if "success_count" in run_cols:
                run_payload["success_count"] = success_count
            if "failed_count" in run_cols:
                run_payload["failed_count"] = failed_count

            keys = list(run_payload.keys())
            if keys:
                returning = " RETURNING id" if "id" in run_cols else ""
                stmt = text(
                    f"INSERT INTO normalization_runs ({', '.join(keys)}) "
                    f"VALUES ({', '.join(':' + k for k in keys)}){returning}"
                )
                result = db.execute(stmt, run_payload)
                if returning:
                    row = result.fetchone()
                    if row and row[0] is not None:
                        run_id = int(row[0])

        db.execute(
            text("DELETE FROM normalized_records WHERE upload_id = :upload_id"),
            {"upload_id": upload_id},
        )

        row_num_col = next(
            (c for c in ("row_number", "row_index", "line_number", "row_idx") if c in rec_cols),
            None,
        )

        needs_raw_id = "raw_id" in rec_cols
        for idx, norm_dict in enumerate(normalized_rows):
            raw_id = raw_row_ids[idx] if idx < len(raw_row_ids) else None
            if needs_raw_id and raw_id is None:
                raise ValueError("raw_id missing during normalization")

            insert_fields: dict[str, Any] = {
                "upload_id": upload_id,
                payload_col: json.dumps(_json_safe(norm_dict)),
            }
            if needs_raw_id:
                insert_fields["raw_id"] = int(raw_id)
            if "normalization_run_id" in rec_cols and run_id is not None:
                insert_fields["normalization_run_id"] = run_id
            if row_num_col:
                insert_fields[row_num_col] = idx + 1
            if "raw_record_id" in rec_cols and raw_id is not None:
                insert_fields["raw_record_id"] = raw_id

            _add_structured_normalized_columns(insert_fields, rec_cols, norm_dict)

            cols = list(insert_fields.keys())
            stmt = text(
                f"INSERT INTO normalized_records ({', '.join(cols)}) "
                f"VALUES ({', '.join(':' + c for c in cols)})"
            )
            db.execute(stmt, insert_fields)

        db.commit()
        return run_id
    except Exception:
        db.rollback()
        raise
