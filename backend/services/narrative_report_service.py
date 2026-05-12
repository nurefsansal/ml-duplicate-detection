"""
Yükleme bazlı sözel (metin) özet raporu — operasyonel okuma için paragraf formatında.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.api.routes.normalized_records_route import (
    _approved_pair_merge_groups,
    _confirmed_entity_memberships_for_scope,
    build_merge_lineage_rows,
)
from backend.models.database import DetectionRun, MatchCandidate, NormalizedRecord, RawRecord, Upload


def _fmt_dt(value: Optional[datetime]) -> str:
    if value is None:
        return "—"
    try:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return str(value)


def build_upload_narrative_report(
    db: Session,
    *,
    upload_id: int,
    lang: str = "tr",
) -> str:
    """
    Tek bir yükleme için UTF-8 düz metin rapor (TR veya EN).
    """
    lang = (lang or "tr").lower()[:2]
    if lang not in ("tr", "en"):
        lang = "tr"

    upload = db.query(Upload).filter(Upload.id == upload_id).first()
    if upload is None:
        raise ValueError(f"upload not found: {upload_id}")

    raw_total = (
        db.query(func.count(RawRecord.id)).filter(RawRecord.upload_id == upload_id).scalar() or 0
    )
    norm_total = (
        db.query(func.count(NormalizedRecord.id))
        .filter(NormalizedRecord.upload_id == upload_id)
        .scalar()
        or 0
    )
    norm_invalid = (
        db.query(func.count(NormalizedRecord.id))
        .filter(
            NormalizedRecord.upload_id == upload_id,
            NormalizedRecord.is_valid.is_(False),
        )
        .scalar()
        or 0
    )

    memberships_by_entity, confirmed_ids = _confirmed_entity_memberships_for_scope(
        db,
        upload_id=upload_id,
        normalization_run_id=None,
    )
    entity_group_count = len(memberships_by_entity)

    merge_groups, merge_consumed = _approved_pair_merge_groups(
        db,
        upload_id=upload_id,
        normalization_run_id=None,
        excluded_record_ids=confirmed_ids,
    )
    approved_merge_group_count = sum(1 for g in merge_groups if len(g) >= 2)

    exclude_ids = confirmed_ids | merge_consumed
    singleton_q = db.query(func.count(NormalizedRecord.id)).filter(
        NormalizedRecord.upload_id == upload_id
    )
    if exclude_ids:
        singleton_q = singleton_q.filter(~NormalizedRecord.id.in_(exclude_ids))
    singleton_count = int(singleton_q.scalar() or 0)

    clean_row_count = entity_group_count + approved_merge_group_count + singleton_count

    cand_base = (
        db.query(MatchCandidate)
        .join(DetectionRun, MatchCandidate.detection_run_id == DetectionRun.id)
        .filter(DetectionRun.upload_id == upload_id)
    )
    cand_approved = cand_base.filter(MatchCandidate.decision == "approved").count()
    cand_pending = cand_base.filter(MatchCandidate.decision == "pending").count()
    cand_rejected = cand_base.filter(MatchCandidate.decision == "rejected").count()

    detection_runs = (
        db.query(func.count(DetectionRun.id)).filter(DetectionRun.upload_id == upload_id).scalar()
        or 0
    )

    lineage = build_merge_lineage_rows(db, upload_id=upload_id)
    merged_people = sum(int(r.get("member_count") or 0) for r in lineage)
    sample_lines: list[str] = []
    for row in lineage[:4]:
        kind = row.get("merge_kind") or ""
        names_before = str(row.get("clean_name_values_before") or "").replace("|", ", ")
        name_after = str(row.get("clean_name_after") or "").strip() or "—"
        m_before = str(row.get("muhatap_values_before") or "").replace("|", ", ")
        m_after = str(row.get("muhatap_value_after") or "").strip() or "—"
        if lang == "en":
            if kind == "entity":
                sample_lines.append(
                    f"  • Entity #{row.get('entity_id')}: names before [{names_before}] → golden «{name_after}»; "
                    f"muhatap before [{m_before}] → «{m_after}»."
                )
            else:
                sample_lines.append(
                    f"  • Approved merge group: names before [{names_before}] → «{name_after}»; "
                    f"muhatap before [{m_before}] → «{m_after}»."
                )
        else:
            if kind == "entity":
                sample_lines.append(
                    f"  • Entity #{row.get('entity_id')}: adlar önce [{names_before}] → golden «{name_after}»; "
                    f"muhatap önce [{m_before}] → «{m_after}»."
                )
            else:
                sample_lines.append(
                    f"  • Onaylı çift birleşimi: adlar önce [{names_before}] → «{name_after}»; "
                    f"muhatap önce [{m_before}] → «{m_after}»."
                )

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if lang == "en":
        lines = [
            "=" * 72,
            "DUPLICATE MANAGEMENT — NARRATIVE SUMMARY",
            "=" * 72,
            "",
            "1. Upload",
            f"   • Internal id: {upload_id}",
            f"   • File name: {upload.file_name or '—'}",
            f"   • Status: {upload.status or '—'}",
            f"   • Declared row count (upload): {upload.total_records or 0}",
            f"   • Created: {_fmt_dt(upload.created_at)}",
            f"   • Completed: {_fmt_dt(upload.completed_at)}",
            "",
            "2. Ingestion and normalization",
            f"   • Raw rows stored: {raw_total}",
            f"   • Normalized rows: {norm_total}",
            f"   • Normalized rows flagged not valid: {norm_invalid}",
            "",
            "3. Operational single-customer view (clean export)",
            "   One output row = one person / counterparty after merges.",
            f"   • Golden Entity groups (confirmed membership): {entity_group_count}",
            f"   • Approved match merges (no Entity row yet): {approved_merge_group_count}",
            f"   • Standalone normalized rows (not merged): {singleton_count}",
            f"   • Total clean export rows: {clean_row_count}",
            "",
            "4. Match decisions (this upload, all detection runs)",
            f"   • Detection runs: {detection_runs}",
            f"   • Candidate pairs approved: {cand_approved}",
            f"   • Candidate pairs pending review: {cand_pending}",
            f"   • Candidate pairs rejected: {cand_rejected}",
            "",
            "5. Merge coverage (lineage)",
            f"   • Merge / entity groups listed in lineage export: {len(lineage)}",
            f"   • Sum of member normalized rows across those groups: {merged_people}",
            "",
        ]
        if sample_lines:
            lines.append("   Examples (first groups, name & muhatap before → after):")
            lines.extend(sample_lines)
        else:
            lines.append("   (No merge groups to sample yet.)")
        lines.extend(
            [
                "",
                "6. How to read this",
                "   Use the CSV exports for full audit. This text is a management summary only.",
                "   Raw and normalized rows are retained in the database; the clean file is the",
                "   deduplicated operational view.",
                "",
                f"— Generated automatically at {now}.",
                "",
            ]
        )
        return "\n".join(lines)

    lines = [
        "=" * 72,
        "MÜKERRER YÖNETİMİ — SÖZEL ÖZET RAPOR",
        "=" * 72,
        "",
        "1. Yükleme bilgisi",
        f"   • Yükleme numarası (id): {upload_id}",
        f"   • Dosya adı: {upload.file_name or '—'}",
        f"   • Durum: {upload.status or '—'}",
        f"   • Bildirilen kayıt sayısı (yükleme): {upload.total_records or 0}",
        f"   • Oluşturulma: {_fmt_dt(upload.created_at)}",
        f"   • Tamamlanma: {_fmt_dt(upload.completed_at)}",
        "",
        "2. Ham veri ve normalizasyon",
        f"   • Veritabanındaki ham satır sayısı: {raw_total}",
        f"   • Normalize edilmiş satır sayısı: {norm_total}",
        f"   • Geçersiz işaretli normalize satır: {norm_invalid}",
        "",
        "3. Tekil operasyonel görünüm (temiz dışa aktarım)",
        "   Her çıktı satırı, birleşimler sonrası tek müşteri / muhatap anlamına gelir.",
        f"   • Golden Entity grupları (onaylı üyelik): {entity_group_count}",
        f"   • Sadece onaylı eşleşmeyle birleşen gruplar (Entity kaydı yok): {approved_merge_group_count}",
        f"   • Birleşime girmeyen tekil normalize satırlar: {singleton_count}",
        f"   • Temiz export toplam satır sayısı: {clean_row_count}",
        "",
        "4. Eşleşme kararları (bu yükleme, tüm tespit koşuları)",
        f"   • Tespit koşusu (detection run) sayısı: {detection_runs}",
        f"   • Onaylı aday çift: {cand_approved}",
        f"   • İncelemede (bekleyen) çift: {cand_pending}",
        f"   • Reddedilen çift: {cand_rejected}",
        "",
        "5. Birleşim özeti (lineage ile uyumlu)",
        f"   • Lineage raporunda listelenen birleşim / entity grubu: {len(lineage)}",
        f"   • Bu gruplardaki toplam üye normalize satırı: {merged_people}",
        "",
    ]
    if sample_lines:
        lines.append("   Örnekler (ilk gruplar; ad ve muhatap önce → sonra):")
        lines.extend(sample_lines)
    else:
        lines.append("   (Henüz örnekleyecek birleşim grubu yok.)")
    lines.extend(
        [
            "",
            "6. Yorum",
            "   Ayrıntılı denetim için CSV dışa aktarımlarını kullanın; bu metin yönetim özeti niteliğindedir.",
            "   Ham ve normalize kayıtlar veritabanında saklanmaya devam eder; temiz dosya tekilleştirilmiş operasyonel görünümdür.",
            "",
            f"— Rapor otomatik üretildi: {now}.",
            "",
        ]
    )
    return "\n".join(lines)
