from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
import hashlib
import json
from typing import Any

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from src.db import create_db_engine
from backend.models.database import (
    ColumnMapping,
    NormalizationRun,
    NormalizedRecord,
    RawRecord,
    Upload,
)
from backend.services.normalization_service import (
    CITY_COLUMN,
    EMAIL_COLUMN,
    NAME_COLUMN,
    PHONE_COLUMN,
    TC_COLUMN,
    build_preview_rows,
    extract_first_last_name,
    prepare_normalized_dataframe,
)

DEFAULT_NORMALIZATION_PROFILE = "default_person_normalization_v1"

ENGINE = create_db_engine()
SessionLocal = sessionmaker(bind=ENGINE)


def _ensure_import_batch(session, upload: Upload) -> str:
    batch_id = f"upload-{upload.id}"
    session.execute(
        text(
            """
            INSERT INTO import_batches (
                batch_id,
                source_name,
                source_type,
                status,
                record_count,
                created_at
            )
            VALUES (
                :batch_id,
                :source_name,
                :source_type,
                :status,
                :record_count,
                COALESCE(:created_at, CURRENT_TIMESTAMP)
            )
            ON CONFLICT (batch_id) DO NOTHING
            """
        ),
        {
            "batch_id": batch_id,
            "source_name": upload.file_name or upload.source_name or f"upload-{upload.id}",
            "source_type": upload.source_type or "unknown",
            "status": upload.status or "uploaded",
            "record_count": upload.total_records or 0,
            "created_at": upload.created_at,
        },
    )
    return batch_id


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item") and callable(value.item):
        try:
            value = value.item()
        except Exception:
            pass
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    return value


def _row_to_payload(row: pd.Series | dict[str, Any]) -> dict[str, Any]:
    if isinstance(row, pd.Series):
        data = row.to_dict()
    else:
        data = dict(row)
    return {str(key): _to_jsonable(value) for key, value in data.items()}


def generate_ingestion_hash(row_payload: dict[str, Any]) -> str:
    serialized = json.dumps(row_payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _validation_codes(row_payload: dict[str, Any]) -> list[str]:
    codes: list[str] = []
    name_value = str(row_payload.get(NAME_COLUMN, "") or "").strip()
    tc_value = str(row_payload.get(TC_COLUMN, "") or "").strip()
    phone_value = str(row_payload.get(PHONE_COLUMN, "") or "").strip()
    email_value = str(row_payload.get(EMAIL_COLUMN, "") or "").strip()

    if not name_value:
        codes.append("missing_required_name")
    if not any([tc_value, phone_value, email_value]):
        codes.append("missing_all_primary_identifiers")
    return codes


def _build_validation_payload(row_payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    codes = _validation_codes(row_payload)
    row_status = "invalid" if "missing_required_name" in codes else "valid"
    if not codes:
        return row_status, {}
    return row_status, {"warnings": codes}


def _summarize_validation_warnings(counter: Counter[str]) -> list[str]:
    warnings: list[str] = []
    if counter.get("missing_required_name", 0):
        warnings.append(
            f"{counter['missing_required_name']} satirda zorunlu 'Ad Soyad' alani bos; "
            "kayitlar invalid olarak saklandi."
        )
    if counter.get("missing_all_primary_identifiers", 0):
        warnings.append(
            f"{counter['missing_all_primary_identifiers']} satirda TC, telefon ve e-posta birlikte bos; "
            "kayitlar dusuk bilgi kalitesiyle saklandi."
        )
    return warnings


def _get_or_create_upload(
    *,
    session,
    upload_id: int | None,
    source_type: str,
    source_name: str | None,
    file_name: str,
    total_records: int,
    created_by: str,
) -> Upload:
    upload: Upload | None = None
    if upload_id is not None:
        upload = session.query(Upload).filter(Upload.id == upload_id).first()

    if upload is None:
        upload = Upload(
            source_type=source_type,
            source_name=source_name,
            file_name=file_name,
            file_size_bytes=0,
            total_records=total_records,
            created_by=created_by,
            status="processing",
            processing_stage="normalizing",
        )
        session.add(upload)
        session.flush()
        return upload

    upload.source_type = source_type
    upload.source_name = source_name or upload.source_name
    upload.file_name = file_name or upload.file_name
    upload.total_records = total_records
    upload.status = "processing"
    upload.processing_stage = "normalizing"
    upload.updated_at = datetime.now(UTC).replace(tzinfo=None)
    session.flush()
    return upload


def _persist_column_mappings(
    *,
    session,
    upload_id: int,
    mapping_definitions: list[dict[str, Any]],
) -> None:
    if not mapping_definitions:
        return

    existing = {
        (mapping.source_column_name, mapping.target_field_name)
        for mapping in session.query(ColumnMapping).filter(ColumnMapping.upload_id == upload_id).all()
    }

    for mapping in mapping_definitions:
        key = (mapping["source_column_name"], mapping["target_field_name"])
        if key in existing:
            continue

        session.add(
            ColumnMapping(
                upload_id=upload_id,
                source_column_name=mapping["source_column_name"],
                target_field_name=mapping["target_field_name"],
                is_required=bool(mapping.get("is_required", False)),
                mapping_type=str(mapping.get("mapping_type", "direct")),
            )
        )
        existing.add(key)

    session.flush()


def persist_normalization_pipeline(
    *,
    original_df: pd.DataFrame,
    processing_df: pd.DataFrame,
    source_type: str,
    source_name: str | None,
    file_name: str,
    created_by: str,
    upload_id: int | None = None,
    normalization_profile: str = DEFAULT_NORMALIZATION_PROFILE,
    mapping_definitions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized_df = prepare_normalized_dataframe(processing_df)
    normalized_payload_rows = build_preview_rows(normalized_df)

    total_processed = len(processing_df)
    success_count = int(normalized_df["is_valid"].fillna(False).sum()) if total_processed else 0
    failed_count = total_processed - success_count

    original_payloads = [_row_to_payload(row) for _, row in original_df.iterrows()]
    processing_payloads = [_row_to_payload(row) for _, row in processing_df.iterrows()]
    normalized_payloads = [_row_to_payload(row) for _, row in normalized_df.iterrows()]

    warning_counter: Counter[str] = Counter()
    validation_rows: list[tuple[str, dict[str, Any]]] = []
    for processing_payload in processing_payloads:
        row_status, validation_payload = _build_validation_payload(processing_payload)
        warning_counter.update(validation_payload.get("warnings", []))
        validation_rows.append((row_status, validation_payload))

    session = SessionLocal()
    try:
        upload = _get_or_create_upload(
            session=session,
            upload_id=upload_id,
            source_type=source_type,
            source_name=source_name,
            file_name=file_name,
            total_records=total_processed,
            created_by=created_by,
        )

        _persist_column_mappings(
            session=session,
            upload_id=upload.id,
            mapping_definitions=mapping_definitions or [],
        )

        raw_records: list[RawRecord] = []
        batch_id = _ensure_import_batch(session, upload)
        for row_index, (row_payload, (row_status, validation_payload)) in enumerate(
            zip(
                original_payloads,
                validation_rows,
                strict=True,
            ),
            start=1,
        ):
            raw_record = RawRecord(
                upload_id=upload.id,
                batch_id=batch_id,
                row_index=row_index,
                raw_payload=row_payload,
                ingestion_hash=generate_ingestion_hash(row_payload),
                row_status=row_status,
                validation_errors=validation_payload,
            )
            session.add(raw_record)
            raw_records.append(raw_record)

        session.flush()

        normalization_run = NormalizationRun(
            upload_id=upload.id,
            normalization_profile=normalization_profile,
            total_processed=total_processed,
            success_count=success_count,
            failed_count=failed_count,
        )
        session.add(normalization_run)
        session.flush()

        for raw_record, normalized_payload in zip(raw_records, normalized_payloads, strict=True):
            clean_name = str(normalized_payload.get("clean_name", "") or "")
            first_name = str(normalized_payload.get("first_name", "") or "")
            last_name = str(normalized_payload.get("last_name", "") or "")
            ordered_name = str(normalized_payload.get("ordered_name", "") or "")
            if not first_name or not last_name:
                derived_first_name, derived_last_name = extract_first_last_name(clean_name)
                first_name = first_name or derived_first_name
                last_name = last_name or derived_last_name

            session.add(
                NormalizedRecord(
                    raw_id=raw_record.id,
                    upload_id=upload.id,
                    normalization_run_id=normalization_run.id,
                    clean_name=clean_name,
                    first_name=first_name,
                    last_name=last_name,
                    ordered_name=ordered_name,
                    name_phonetic=str(normalized_payload.get("name_phonetic", "") or ""),
                    clean_phone=str(normalized_payload.get("clean_phone", "") or ""),
                    phone_last7=str(normalized_payload.get("phone_last7", "") or ""),
                    clean_email=str(normalized_payload.get("clean_email", "") or ""),
                    clean_tc=str(normalized_payload.get("clean_tc", "") or ""),
                    clean_city=str(normalized_payload.get("clean_city", "") or ""),
                    clean_address=str(normalized_payload.get("clean_address", "") or ""),
                    blocking_key=str(normalized_payload.get("blocking_key", "") or ""),
                    is_valid=bool(normalized_payload.get("is_valid", False)),
                    normalized_payload=normalized_payload,
                )
            )

        upload.total_records = total_processed
        upload.status = "completed"
        upload.processing_stage = "normalized"
        upload.completed_at = datetime.now(UTC).replace(tzinfo=None)
        upload.updated_at = datetime.now(UTC).replace(tzinfo=None)

        session.commit()

        preview_rows = normalized_payload_rows[: min(len(normalized_payload_rows), 50)]
        validation_warnings = _summarize_validation_warnings(warning_counter)

        return {
            "uploadId": upload.id,
            "normalizationRunId": normalization_run.id,
            "totalProcessed": total_processed,
            "successCount": success_count,
            "failedCount": failed_count,
            "previewRows": preview_rows,
            "validationWarnings": validation_warnings,
            "upload_id": upload.id,
            "normalization_run_id": normalization_run.id,
            "total_processed": total_processed,
            "success_count": success_count,
            "failed_count": failed_count,
            "preview_rows": preview_rows,
            "validation_warnings": validation_warnings,
            "totalRecords": total_processed,
            "normalizedRecords": normalized_payload_rows,
        }
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
