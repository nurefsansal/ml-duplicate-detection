"""
Muhatap birleştirme raporu: özet metin, upload listesi ve PDF üretimi.
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models.database import Entity, EntityMembership, NormalizedRecord, Upload
from backend.services.review_service import _entity_merge_groups_for_upload


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def build_merge_summary(
    golden_record: dict[str, Any],
    *,
    muhatap_codes: list[str] | None = None,
) -> dict[str, Any]:
    """Hedef / önceki kodlar ve okunabilir rapor satırı."""
    target_code = _safe_str(golden_record.get("clean_muhatap_no"))
    target_name = _safe_str(golden_record.get("clean_name"))
    snaps = golden_record.get("merged_member_snapshots") or []
    sources = golden_record.get("merged_muhatap_sources") or []

    code_set: set[str] = set()
    if muhatap_codes:
        for code in muhatap_codes:
            c = _safe_str(code)
            if c:
                code_set.add(c)
    for snap in snaps:
        c = _safe_str(snap.get("muhatap_no_effective")) or _safe_str(snap.get("clean_muhatap_no"))
        if c:
            code_set.add(c)
    for item in sources:
        c = _safe_str(item.get("clean_muhatap_no"))
        if c:
            code_set.add(c)

    prior_codes = sorted(c for c in code_set if c and c != target_code)

    member_lines: list[str] = []
    for snap in snaps:
        nm = _safe_str(snap.get("clean_name")) or "—"
        mc = _safe_str(snap.get("muhatap_no_effective")) or _safe_str(snap.get("clean_muhatap_no")) or "—"
        member_lines.append(f"{nm} ({mc})")
    if not member_lines and sources:
        for item in sources:
            nm = _safe_str(item.get("clean_name")) or "—"
            mc = _safe_str(item.get("clean_muhatap_no")) or "—"
            member_lines.append(f"{nm} ({mc})")

    prior_str = ", ".join(prior_codes) if prior_codes else "—"
    members_str = " · ".join(member_lines) if member_lines else "—"

    report_line = (
        f"Hedef muhatap: {target_code or '—'} ({target_name or '—'}) · "
        f"Önceki kodlar: {prior_str} · "
        f"Birleştirilen kayıtlar: {members_str}"
    )

    excluded = golden_record.get("excluded_member_snapshots") or []
    if excluded:
        ex_parts = []
        for snap in excluded:
            nm = _safe_str(snap.get("clean_name")) or "—"
            mc = _safe_str(snap.get("muhatap_no_effective")) or _safe_str(snap.get("clean_muhatap_no")) or "—"
            ex_parts.append(f"{nm} ({mc})")
        report_line += (
            " · Birleşime dahil edilmeyen: "
            + " · ".join(ex_parts)
            + " (bekleyen grupta yeniden incelenebilir)."
        )
    else:
        report_line += " · Tek muhatap kodunda birleştirildi."

    return {
        "target_muhatap_code": target_code,
        "target_name": target_name,
        "prior_muhatap_codes": prior_codes,
        "merged_muhatap_report_line": report_line,
    }


def group_has_merge_detail(group: dict[str, Any]) -> bool:
    gr = group.get("golden_record") or {}
    return bool(gr.get("merged_member_snapshots") or gr.get("merged_muhatap_report_line"))


def _enrich_merge_group(group: dict[str, Any]) -> dict[str, Any]:
    gr = dict(group.get("golden_record") or {})
    summary = build_merge_summary(gr, muhatap_codes=group.get("muhatap_codes"))
    gr["merged_muhatap_report_line"] = summary["merged_muhatap_report_line"]
    gr["target_muhatap_code"] = summary["target_muhatap_code"]
    gr["prior_muhatap_codes"] = summary["prior_muhatap_codes"]
    return {
        "group_id": group.get("group_id"),
        "entity_id": group.get("entity_id"),
        "muhatap_codes": group.get("muhatap_codes"),
        "record_ids": group.get("record_ids"),
        "group_score": group.get("group_score"),
        "golden_record": gr,
        "merge_summary": summary,
        "records": group.get("records"),
    }


def collect_muhatap_merge_groups(
    session: Session,
    *,
    upload_id: int | None = None,
    decision: str = "approved",
    limit: int = 5000,
) -> list[dict[str, Any]]:
    """Onaylı entity birleştirmelerinden rapor grupları (graf yeniden hesabı yok)."""
    if upload_id is None:
        return []

    groups = _entity_merge_groups_for_upload(
        session,
        upload_id=upload_id,
        limit=limit,
        different_muhatap_code=False,
    )
    out: list[dict[str, Any]] = []
    for g in groups:
        if not group_has_merge_detail(g):
            continue
        out.append(_enrich_merge_group(g))
    return out


def count_merge_groups_by_upload(session: Session) -> dict[int, int]:
    counts: dict[int, int] = {}
    rows = (
        session.query(NormalizedRecord.upload_id, func.count(Entity.id))
        .join(EntityMembership, EntityMembership.normalized_record_id == NormalizedRecord.id)
        .join(Entity, Entity.id == EntityMembership.entity_id)
        .filter(EntityMembership.status == "confirmed")
        .filter(
            (Entity.canonical_data["merged_member_snapshots"].isnot(None))
            | (Entity.canonical_data["merged_muhatap_report_line"].isnot(None))
        )
        .group_by(NormalizedRecord.upload_id)
        .all()
    )
    for upload_id, cnt in rows:
        if upload_id is not None:
            counts[int(upload_id)] = int(cnt or 0)
    return counts


def list_uploads_with_muhatap_merge(session: Session, *, limit: int = 100) -> list[dict[str, Any]]:
    counts = count_merge_groups_by_upload(session)
    if not counts:
        return []

    uploads = (
        session.query(Upload)
        .filter(Upload.id.in_(counts.keys()))
        .order_by(Upload.created_at.desc())
        .limit(limit)
        .all()
    )
    result: list[dict[str, Any]] = []
    for upload in uploads:
        result.append(
            {
                "id": upload.id,
                "file_name": upload.file_name,
                "source_type": upload.source_type or "unknown",
                "total_records": upload.total_records or 0,
                "status": upload.status,
                "created_at": upload.created_at.isoformat() if upload.created_at else None,
                "merge_group_count": counts.get(int(upload.id), 0),
            }
        )
    return result


def generate_muhatap_merge_pdf(
    *,
    upload: Upload | None,
    groups: list[dict[str, Any]],
) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
    except ImportError as exc:
        raise ImportError(
            "reportlab paketi kurulu değil. Sunucuda: pip install reportlab"
        ) from exc

    from backend.services.pdf_fonts import ensure_pdf_fonts_registered

    font_regular, font_bold = ensure_pdf_fonts_registered()

    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="Muhatap Birleştirme Raporu",
    )

    styles = getSampleStyleSheet()
    navy = colors.HexColor("#1e3a5f")
    blue = colors.HexColor("#2563eb")
    green = colors.HexColor("#059669")
    muted = colors.HexColor("#64748b")
    ink = colors.HexColor("#0f172a")
    line_bg = colors.HexColor("#eff6ff")
    card_border = colors.HexColor("#cbd5e1")
    row_alt = colors.HexColor("#f8fafc")

    title_style = ParagraphStyle(
        "Title",
        parent=styles["Heading1"],
        fontName=font_bold,
        fontSize=20,
        textColor=navy,
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "Subtitle",
        parent=styles["Normal"],
        fontName=font_regular,
        fontSize=10,
        textColor=muted,
        spaceAfter=10,
    )
    section_style = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        fontName=font_bold,
        fontSize=12,
        textColor=blue,
        spaceBefore=8,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontName=font_regular,
        fontSize=9,
        textColor=ink,
        leading=13,
    )
    small_style = ParagraphStyle(
        "Small",
        parent=styles["Normal"],
        fontName=font_regular,
        fontSize=8,
        textColor=muted,
        leading=11,
    )

    def _table_font_style(*, header_bg: colors.Color, header_fg: colors.Color) -> TableStyle:
        return TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), header_bg),
                ("TEXTCOLOR", (0, 0), (-1, 0), header_fg),
                ("FONTNAME", (0, 0), (-1, 0), font_bold),
                ("FONTNAME", (0, 1), (-1, -1), font_regular),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 0.25, card_border),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, row_alt]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )

    story: list[Any] = []

    upload_label = upload.file_name if upload else "Tüm yüklemeler"
    upload_id_txt = f"#{upload.id}" if upload else "—"
    generated = datetime.now().strftime("%d.%m.%Y %H:%M")

    story.append(Paragraph("Muhatap Birleştirme Raporu", title_style))
    story.append(
        Paragraph(
            f"Yükleme {upload_id_txt} · {upload_label}<br/>"
            f"Oluşturulma: {generated} · Grup sayısı: {len(groups)}",
            subtitle_style,
        ),
    )

    summary_table = Table(
        [
            ["Özet", "Değer"],
            ["Birleştirilmiş grup", str(len(groups))],
            [
                "Toplam dahil kayıt",
                str(
                    sum(
                        len((g.get("golden_record") or {}).get("merged_member_snapshots") or [])
                        for g in groups
                    )
                ),
            ],
        ],
        colWidths=[70 * mm, 90 * mm],
    )
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), navy),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), font_bold),
                ("FONTNAME", (0, 1), (-1, -1), font_regular),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.4, card_border),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, row_alt]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(summary_table)
    story.append(Spacer(1, 10))

    if not groups:
        story.append(
            Paragraph(
                "Bu yükleme için kayıtlı muhatap birleştirme detayı bulunamadı.",
                body_style,
            )
        )
        doc.build(story)
        return buffer.getvalue()

    def _member_table(snaps: list[dict], *, header_bg: colors.Color) -> Table:
        header = ["Kayıt", "Muhatap", "Ad", "TC", "Telefon", "E-posta"]
        rows = [header]
        for snap in snaps:
            rows.append(
                [
                    str(snap.get("record_id") or "—"),
                    _safe_str(snap.get("muhatap_no_effective"))
                    or _safe_str(snap.get("clean_muhatap_no"))
                    or "—",
                    _safe_str(snap.get("clean_name")) or "—",
                    _safe_str(snap.get("clean_tc")) or "—",
                    _safe_str(snap.get("clean_phone")) or "—",
                    _safe_str(snap.get("clean_email")) or "—",
                ]
            )
        tbl = Table(rows, colWidths=[18 * mm, 22 * mm, 32 * mm, 24 * mm, 26 * mm, 38 * mm])
        tbl.setStyle(_table_font_style(header_bg=header_bg, header_fg=colors.white))
        return tbl

    for index, group in enumerate(groups, start=1):
        if index > 1:
            story.append(Spacer(1, 6))
        gr = group.get("golden_record") or {}
        summary = group.get("merge_summary") or build_merge_summary(
            gr, muhatap_codes=group.get("muhatap_codes")
        )
        prior = summary.get("prior_muhatap_codes") or []
        target = summary.get("target_muhatap_code") or "—"
        target_name = summary.get("target_name") or "—"
        score_pct = f"{float(group.get('group_score') or 0) * 100:.1f}"

        story.append(
            Paragraph(
                f"{index}. {group.get('group_id')} · Entity #{group.get('entity_id') or '—'} · Skor %{score_pct}",
                section_style,
            )
        )

        transition = Table(
            [
                ["Önceki muhatap kodları", " → ", "Hedef muhatap kodu"],
                [", ".join(prior) if prior else "—", "", f"{target} ({target_name})"],
            ],
            colWidths=[68 * mm, 10 * mm, 72 * mm],
        )
        transition.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), line_bg),
                    ("BACKGROUND", (0, 1), (-1, 1), colors.white),
                    ("TEXTCOLOR", (0, 0), (-1, 0), navy),
                    ("TEXTCOLOR", (0, 1), (-1, 1), ink),
                    ("FONTNAME", (0, 0), (-1, 0), font_bold),
                    ("FONTNAME", (0, 1), (-1, 1), font_regular),
                    ("FONTNAME", (2, 1), (2, 1), font_bold),
                    ("TEXTCOLOR", (2, 1), (2, 1), green),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("ALIGN", (1, 0), (1, 1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("BOX", (0, 0), (-1, -1), 0.6, blue),
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, card_border),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        story.append(transition)
        story.append(Spacer(1, 4))
        story.append(Paragraph(summary.get("merged_muhatap_report_line", ""), small_style))
        story.append(Spacer(1, 6))

        snaps = gr.get("merged_member_snapshots") or []
        if snaps:
            story.append(Paragraph("Birleşime dahil edilen kayıtlar", body_style))
            story.append(Spacer(1, 3))
            story.append(_member_table(snaps, header_bg=blue))

        excluded = gr.get("excluded_member_snapshots") or []
        if excluded:
            story.append(Spacer(1, 6))
            story.append(Paragraph("Birleşime dahil edilmeyen kayıtlar", body_style))
            story.append(Spacer(1, 3))
            story.append(_member_table(excluded, header_bg=green))

        if index < len(groups) and index % 2 == 0:
            story.append(PageBreak())

    doc.build(story)
    return buffer.getvalue()
