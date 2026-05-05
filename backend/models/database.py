"""
SQLAlchemy ORM models for duplicate-detection storage.

This module keeps the legacy schema intact while extending it with a more
production-oriented data pipeline:

uploads -> raw_records -> normalized_records -> detection_runs ->
match_candidates -> review_actions -> entities/entity_memberships
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Upload(Base):
    __tablename__ = "uploads"

    id = Column(Integer, primary_key=True)

    # Legacy/current fields
    file_name = Column(String, nullable=False)
    file_size_bytes = Column(Integer)
    total_records = Column(Integer, default=0)
    status = Column(String(32), default="pending")
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String(255))

    # New pipeline metadata
    source_type = Column(String(32))
    source_name = Column(String(255))
    completed_at = Column(DateTime)
    processing_stage = Column(String(64), default="uploaded")

    # Legacy relationships
    raw_donors = relationship(
        "RawDonor",
        back_populates="upload",
        cascade="all, delete-orphan",
    )
    normalized_donors = relationship(
        "NormalizedDonor",
        back_populates="upload",
        cascade="all, delete-orphan",
    )
    matches = relationship(
        "Match",
        back_populates="upload",
        cascade="all, delete-orphan",
    )

    # New pipeline relationships
    raw_records = relationship(
        "RawRecord",
        back_populates="upload",
        cascade="all, delete-orphan",
    )
    column_mappings = relationship(
        "ColumnMapping",
        back_populates="upload",
        cascade="all, delete-orphan",
    )
    normalization_runs = relationship(
        "NormalizationRun",
        back_populates="upload",
        cascade="all, delete-orphan",
    )
    normalized_records = relationship(
        "NormalizedRecord",
        back_populates="upload",
        cascade="all, delete-orphan",
    )
    detection_runs = relationship(
        "DetectionRun",
        back_populates="upload",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_uploads_status", "status"),
        Index("idx_uploads_created_at", "created_at"),
        Index("idx_uploads_source_type", "source_type"),
        Index("idx_uploads_processing_stage", "processing_stage"),
        Index("idx_uploads_completed_at", "completed_at"),
    )

    def __repr__(self) -> str:
        return f"<Upload(id={self.id}, file_name='{self.file_name}', status='{self.status}')>"


class RawDonor(Base):
    __tablename__ = "raw_donors"

    id = Column(Integer, primary_key=True)
    upload_id = Column(Integer, ForeignKey("uploads.id", ondelete="CASCADE"), nullable=False)
    row_number = Column(Integer)
    full_name = Column(String)
    email = Column(String)
    phone = Column(String)
    city = Column(String)
    extra_fields = Column(JSONB)
    created_at = Column(DateTime, default=datetime.utcnow)

    upload = relationship("Upload", back_populates="raw_donors")
    normalized_donor = relationship(
        "NormalizedDonor",
        back_populates="raw_donor",
        uselist=False,
    )

    __table_args__ = (
        Index("idx_raw_donors_upload_id", "upload_id"),
        Index("idx_raw_donors_full_name", "full_name"),
    )

    def __repr__(self) -> str:
        return f"<RawDonor(id={self.id}, name='{self.full_name}')>"


class NormalizedDonor(Base):
    __tablename__ = "normalized_donors"

    id = Column(Integer, primary_key=True)
    upload_id = Column(Integer, ForeignKey("uploads.id", ondelete="CASCADE"), nullable=False)
    raw_id = Column(Integer, ForeignKey("raw_donors.id", ondelete="CASCADE"))

    full_name = Column(String)
    first_name = Column(String)
    last_name = Column(String)
    email = Column(String)
    phone = Column(String)
    city = Column(String)

    clean_tc = Column(String)
    clean_phone = Column(String)
    clean_email = Column(String)
    clean_city = Column(String)
    email_normalized_key = Column(String)
    name_phonetic_key = Column(String)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    upload = relationship("Upload", back_populates="normalized_donors")
    raw_donor = relationship("RawDonor", back_populates="normalized_donor")
    matches_as_donor1 = relationship(
        "Match",
        foreign_keys="Match.donor1_id",
        back_populates="donor1",
    )
    matches_as_donor2 = relationship(
        "Match",
        foreign_keys="Match.donor2_id",
        back_populates="donor2",
    )
    entity_maps = relationship("EntityMap", back_populates="donor")

    __table_args__ = (
        Index("idx_norm_donors_upload_id", "upload_id"),
        Index("idx_norm_donors_raw_id", "raw_id"),
        Index("idx_norm_donors_email", "clean_email"),
        Index("idx_norm_donors_phone", "clean_phone"),
        Index("idx_norm_donors_tc", "clean_tc"),
        Index("idx_norm_donors_city", "clean_city"),
        Index("idx_norm_donors_phonetic", "name_phonetic_key"),
        Index("idx_norm_donors_email_key", "email_normalized_key"),
    )

    def __repr__(self) -> str:
        return f"<NormalizedDonor(id={self.id}, name='{self.full_name}')>"


class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True)
    upload_id = Column(Integer, ForeignKey("uploads.id", ondelete="CASCADE"), nullable=False)
    donor1_id = Column(Integer, ForeignKey("normalized_donors.id", ondelete="CASCADE"), nullable=False)
    donor2_id = Column(Integer, ForeignKey("normalized_donors.id", ondelete="CASCADE"), nullable=False)

    similarity = Column(Float)
    ml_score = Column(Float)
    confidence = Column(Float)

    status = Column(String(32), default="pending")
    decision_reason = Column(String(255))

    features = Column(JSONB)

    approved_by = Column(String(255))
    approved_at = Column(DateTime)
    rejected_reason = Column(String(255))
    rejected_at = Column(DateTime)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    upload = relationship("Upload", back_populates="matches")
    donor1 = relationship(
        "NormalizedDonor",
        foreign_keys=[donor1_id],
        back_populates="matches_as_donor1",
    )
    donor2 = relationship(
        "NormalizedDonor",
        foreign_keys=[donor2_id],
        back_populates="matches_as_donor2",
    )
    entity_map = relationship("EntityMap", back_populates="match", uselist=False)

    __table_args__ = (
        UniqueConstraint("donor1_id", "donor2_id", name="uq_match_pair"),
        Index("idx_matches_upload_id", "upload_id"),
        Index("idx_matches_donor1_id", "donor1_id"),
        Index("idx_matches_donor2_id", "donor2_id"),
        Index("idx_matches_status", "status"),
        Index("idx_matches_ml_score", "ml_score"),
        Index("idx_matches_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<Match(id={self.id}, donor1={self.donor1_id}, donor2={self.donor2_id}, "
            f"status='{self.status}')>"
        )


class RawRecord(Base):
    __tablename__ = "raw_records"

    id = Column(Integer, primary_key=True)
    upload_id = Column(Integer, ForeignKey("uploads.id", ondelete="CASCADE"), nullable=False)
    batch_id = Column(String)
    row_index = Column(Integer)
    raw_payload = Column(JSONB, nullable=False, default=dict)
    ingestion_hash = Column(String(128))
    row_status = Column(String(32), default="pending")
    validation_errors = Column(JSONB, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

    upload = relationship("Upload", back_populates="raw_records")
    normalized_records = relationship(
        "NormalizedRecord",
        back_populates="raw_record",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_raw_records_upload_id", "upload_id"),
        Index("idx_raw_records_batch_id", "batch_id"),
        Index("idx_raw_records_ingestion_hash", "ingestion_hash"),
        Index("idx_raw_records_row_status", "row_status"),
    )

    def __repr__(self) -> str:
        return f"<RawRecord(id={self.id}, upload_id={self.upload_id}, row_status='{self.row_status}')>"


class ColumnMapping(Base):
    __tablename__ = "column_mappings"

    id = Column(Integer, primary_key=True)
    upload_id = Column(Integer, ForeignKey("uploads.id", ondelete="CASCADE"), nullable=False)
    source_column_name = Column(String(255), nullable=False)
    target_field_name = Column(String(128), nullable=False)
    is_required = Column(Boolean, default=False)
    mapping_type = Column(String(32), default="direct")
    created_at = Column(DateTime, default=datetime.utcnow)

    upload = relationship("Upload", back_populates="column_mappings")
    normalization_runs = relationship("NormalizationRun", back_populates="mapping")

    __table_args__ = (
        UniqueConstraint(
            "upload_id",
            "source_column_name",
            "target_field_name",
            name="uq_column_mapping_upload_source_target",
        ),
        Index("idx_column_mappings_upload_id", "upload_id"),
        Index("idx_column_mappings_target_field_name", "target_field_name"),
        Index("idx_column_mappings_mapping_type", "mapping_type"),
    )

    def __repr__(self) -> str:
        return (
            f"<ColumnMapping(id={self.id}, source='{self.source_column_name}', "
            f"target='{self.target_field_name}')>"
        )


class NormalizationRun(Base):
    __tablename__ = "normalization_runs"

    id = Column(Integer, primary_key=True)
    upload_id = Column(Integer, ForeignKey("uploads.id", ondelete="CASCADE"), nullable=False)
    mapping_id = Column(Integer, ForeignKey("column_mappings.id", ondelete="SET NULL"))
    normalization_profile = Column(String(128))
    total_processed = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    upload = relationship("Upload", back_populates="normalization_runs")
    mapping = relationship("ColumnMapping", back_populates="normalization_runs")
    normalized_records = relationship("NormalizedRecord", back_populates="normalization_run")
    detection_runs = relationship("DetectionRun", back_populates="normalization_run")

    __table_args__ = (
        Index("idx_normalization_runs_upload_id", "upload_id"),
        Index("idx_normalization_runs_mapping_id", "mapping_id"),
        Index("idx_normalization_runs_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<NormalizationRun(id={self.id}, upload_id={self.upload_id})>"


class NormalizedRecord(Base):
    __tablename__ = "normalized_records"

    id = Column(Integer, primary_key=True)
    raw_id = Column(Integer, ForeignKey("raw_records.id", ondelete="CASCADE"), nullable=False)
    upload_id = Column(Integer, ForeignKey("uploads.id", ondelete="CASCADE"), nullable=False)
    normalization_run_id = Column(
        Integer,
        ForeignKey("normalization_runs.id", ondelete="SET NULL"),
    )

    clean_name = Column(String)
    first_name = Column(String)
    last_name = Column(String)
    ordered_name = Column(String)
    name_phonetic = Column(String)

    clean_phone = Column(String)
    phone_last7 = Column(String(7))
    clean_email = Column(String)
    clean_tc = Column(String)

    clean_city = Column(String)
    clean_address = Column(Text)
    clean_muhatap_no = Column(String)

    blocking_key = Column(String(255))
    is_valid = Column(Boolean, default=True)
    normalized_payload = Column(JSONB, nullable=False, default=dict)

    created_at = Column(DateTime, default=datetime.utcnow)

    raw_record = relationship("RawRecord", back_populates="normalized_records")
    upload = relationship("Upload", back_populates="normalized_records")
    normalization_run = relationship("NormalizationRun", back_populates="normalized_records")
    left_match_candidates = relationship(
        "MatchCandidate",
        foreign_keys="MatchCandidate.left_id",
        back_populates="left_record",
    )
    right_match_candidates = relationship(
        "MatchCandidate",
        foreign_keys="MatchCandidate.right_id",
        back_populates="right_record",
    )
    entity_memberships = relationship(
        "EntityMembership",
        back_populates="normalized_record",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_normalized_records_raw_id", "raw_id"),
        Index("idx_normalized_records_upload_id", "upload_id"),
        Index("idx_normalized_records_normalization_run_id", "normalization_run_id"),
        Index("idx_normalized_records_clean_tc", "clean_tc"),
        Index("idx_normalized_records_clean_phone", "clean_phone"),
        Index("idx_normalized_records_clean_email", "clean_email"),
        Index("idx_normalized_records_name_phonetic", "name_phonetic"),
        Index("idx_normalized_records_clean_city", "clean_city"),
        Index("idx_normalized_records_blocking_key", "blocking_key"),
        Index("idx_normalized_records_is_valid", "is_valid"),
    )

    def __repr__(self) -> str:
        return f"<NormalizedRecord(id={self.id}, raw_id={self.raw_id}, upload_id={self.upload_id})>"


class DetectionRun(Base):
    __tablename__ = "detection_runs"

    id = Column(Integer, primary_key=True)
    upload_id = Column(Integer, ForeignKey("uploads.id", ondelete="CASCADE"), nullable=False)
    normalization_run_id = Column(
        Integer,
        ForeignKey("normalization_runs.id", ondelete="SET NULL"),
    )
    model_version = Column(String(128))
    threshold = Column(Float)
    duplicate_group_count = Column(Integer, default=0)
    affected_record_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    upload = relationship("Upload", back_populates="detection_runs")
    normalization_run = relationship("NormalizationRun", back_populates="detection_runs")
    match_candidates = relationship(
        "MatchCandidate",
        back_populates="detection_run",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_detection_runs_upload_id", "upload_id"),
        Index("idx_detection_runs_normalization_run_id", "normalization_run_id"),
        Index("idx_detection_runs_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<DetectionRun(id={self.id}, upload_id={self.upload_id})>"


class MatchCandidate(Base):
    __tablename__ = "match_candidates"

    id = Column(Integer, primary_key=True)
    detection_run_id = Column(
        Integer,
        ForeignKey("detection_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    left_id = Column(
        Integer,
        ForeignKey("normalized_records.id", ondelete="CASCADE"),
        nullable=False,
    )
    right_id = Column(
        Integer,
        ForeignKey("normalized_records.id", ondelete="CASCADE"),
        nullable=False,
    )
    score = Column(Float)
    match_type = Column(String(32))
    decision = Column(String(32), default="pending")
    confidence = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

    detection_run = relationship("DetectionRun", back_populates="match_candidates")
    left_record = relationship(
        "NormalizedRecord",
        foreign_keys=[left_id],
        back_populates="left_match_candidates",
    )
    right_record = relationship(
        "NormalizedRecord",
        foreign_keys=[right_id],
        back_populates="right_match_candidates",
    )
    review_actions = relationship(
        "ReviewAction",
        back_populates="match_candidate",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "detection_run_id",
            "left_id",
            "right_id",
            name="uq_match_candidate_run_pair",
        ),
        Index("idx_match_candidates_detection_run_id", "detection_run_id"),
        Index("idx_match_candidates_left_id", "left_id"),
        Index("idx_match_candidates_right_id", "right_id"),
        Index("idx_match_candidates_decision", "decision"),
        Index("idx_match_candidates_match_type", "match_type"),
        Index("idx_match_candidates_score", "score"),
    )

    def __repr__(self) -> str:
        return (
            f"<MatchCandidate(id={self.id}, run={self.detection_run_id}, "
            f"left={self.left_id}, right={self.right_id})>"
        )


class ReviewAction(Base):
    __tablename__ = "review_actions"

    id = Column(Integer, primary_key=True)
    match_id = Column(
        Integer,
        ForeignKey("match_candidates.id", ondelete="CASCADE"),
        nullable=False,
    )
    decision = Column(String(32), nullable=False)
    decided_by = Column(String(255))
    decided_at = Column(DateTime, default=datetime.utcnow)
    reason = Column(Text)

    match_candidate = relationship("MatchCandidate", back_populates="review_actions")

    __table_args__ = (
        Index("idx_review_actions_match_id", "match_id"),
        Index("idx_review_actions_decided_by", "decided_by"),
        Index("idx_review_actions_decided_at", "decided_at"),
    )

    def __repr__(self) -> str:
        return f"<ReviewAction(id={self.id}, match_id={self.match_id}, decision='{self.decision}')>"


class Entity(Base):
    __tablename__ = "entities"

    id = Column(Integer, primary_key=True)

    canonical_name = Column(String, nullable=False)
    canonical_email = Column(String)
    canonical_phone = Column(String)
    canonical_city = Column(String)

    # New production field
    canonical_tc = Column(String)
    canonical_muhatap_no = Column(String)
    canonical_data = Column(JSONB, default=dict)
    golden_record_id = Column(Integer, ForeignKey("normalized_records.id", ondelete="SET NULL"))
    confidence = Column(Float)

    # Legacy/current metadata
    donor_count = Column(Integer, default=1)
    merged_count = Column(Integer, default=0)
    confidence_score = Column(Float, default=1.0)
    merged_by = Column(String(255))
    merged_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    entity_maps = relationship(
        "EntityMap",
        back_populates="entity",
        cascade="all, delete-orphan",
    )
    memberships = relationship(
        "EntityMembership",
        back_populates="entity",
        cascade="all, delete-orphan",
    )
    golden_record = relationship("NormalizedRecord", foreign_keys=[golden_record_id])

    __table_args__ = (
        Index("idx_entities_canonical_name", "canonical_name"),
        Index("idx_entities_canonical_email", "canonical_email"),
        Index("idx_entities_canonical_phone", "canonical_phone"),
        Index("idx_entities_canonical_city", "canonical_city"),
        Index("idx_entities_canonical_tc", "canonical_tc"),
        Index("idx_entities_canonical_muhatap_no", "canonical_muhatap_no"),
        Index("idx_entities_golden_record_id", "golden_record_id"),
        Index("idx_entities_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Entity(id={self.id}, name='{self.canonical_name}', donors={self.donor_count})>"


class EntityMap(Base):
    __tablename__ = "entity_map"

    id = Column(Integer, primary_key=True)
    entity_id = Column(Integer, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False)
    donor_id = Column(Integer, ForeignKey("normalized_donors.id", ondelete="CASCADE"), nullable=False)
    match_id = Column(Integer, ForeignKey("matches.id", ondelete="SET NULL"))
    created_by = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    entity = relationship("Entity", back_populates="entity_maps")
    donor = relationship("NormalizedDonor", back_populates="entity_maps")
    match = relationship("Match", back_populates="entity_map")

    __table_args__ = (
        UniqueConstraint("entity_id", "donor_id", name="uq_entity_donor"),
        Index("idx_entity_map_entity_id", "entity_id"),
        Index("idx_entity_map_donor_id", "donor_id"),
        Index("idx_entity_map_is_active", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<EntityMap(entity={self.entity_id}, donor={self.donor_id})>"


class EntityMembership(Base):
    __tablename__ = "entity_memberships"

    id = Column(Integer, primary_key=True)
    entity_id = Column(Integer, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False)
    normalized_record_id = Column(
        Integer,
        ForeignKey("normalized_records.id", ondelete="CASCADE"),
        nullable=False,
    )
    confidence_at_merge = Column(Float)
    status = Column(String(32), nullable=False, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)

    entity = relationship("Entity", back_populates="memberships")
    normalized_record = relationship("NormalizedRecord", back_populates="entity_memberships")

    __table_args__ = (
        UniqueConstraint(
            "entity_id",
            "normalized_record_id",
            name="uq_entity_membership_entity_record",
        ),
        Index("idx_entity_memberships_entity_id", "entity_id"),
        Index("idx_entity_memberships_normalized_record_id", "normalized_record_id"),
        Index("idx_entity_memberships_status", "status"),
    )

    def __repr__(self) -> str:
        return (
            f"<EntityMembership(entity_id={self.entity_id}, "
            f"normalized_record_id={self.normalized_record_id})>"
        )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    action_type = Column(String(64), nullable=False)
    entity_type = Column(String(64), nullable=False)
    entity_id = Column(Integer, nullable=False)
    payload = Column(JSONB, default=dict)
    created_by = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_audit_logs_action_type", "action_type"),
        Index("idx_audit_logs_entity_lookup", "entity_type", "entity_id"),
        Index("idx_audit_logs_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, action_type='{self.action_type}', entity_type='{self.entity_type}')>"


class AppSettings(Base):
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True)
    key = Column(String(128), unique=True, nullable=False)
    value = Column(JSONB, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(String(255))

    __table_args__ = (
        Index("idx_app_settings_key", "key"),
        Index("idx_app_settings_updated_at", "updated_at"),
    )

    def __repr__(self) -> str:
        return f"<AppSettings(key='{self.key}')>"


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True)
    type = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="pending")
    progress = Column(Float, nullable=False, default=0.0)
    total_rows = Column(Integer, default=0)
    processed_rows = Column(Integer, default=0)
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_jobs_type", "type"),
        Index("idx_jobs_status", "status"),
        Index("idx_jobs_created_at", "created_at"),
        Index("idx_jobs_updated_at", "updated_at"),
    )

    def __repr__(self) -> str:
        return f"<Job(id={self.id}, type='{self.type}', status='{self.status}', progress={self.progress})>"


__all__ = [
    "Base",
    "Upload",
    "RawDonor",
    "NormalizedDonor",
    "Match",
    "RawRecord",
    "ColumnMapping",
    "NormalizationRun",
    "NormalizedRecord",
    "DetectionRun",
    "MatchCandidate",
    "ReviewAction",
    "Entity",
    "EntityMap",
    "EntityMembership",
    "AuditLog",
    "AppSettings",
    "Job",
]
