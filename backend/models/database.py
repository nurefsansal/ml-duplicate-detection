"""
SQLAlchemy ORM Models - Veritabanı şeması için Python sınıfları
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, 
    Boolean, Text, Index, create_engine, JSON, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, Session

Base = declarative_base()


# ============================================================================
# 1. UPLOADS MODEL - Dosya yükleme kaydı
# ============================================================================
class Upload(Base):
    __tablename__ = "uploads"

    id = Column(Integer, primary_key=True)
    file_name = Column(String, nullable=False)
    file_size_bytes = Column(Integer)
    total_records = Column(Integer, default=0)
    status = Column(String(32), default='pending')  # pending, processing, completed, failed
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String(255))

    # İlişkiler
    raw_donors = relationship("RawDonor", back_populates="upload", cascade="all, delete-orphan")
    normalized_donors = relationship("NormalizedDonor", back_populates="upload", cascade="all, delete-orphan")
    matches = relationship("Match", back_populates="upload", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Upload(id={self.id}, file_name='{self.file_name}', status='{self.status}')>"


# ============================================================================
# 2. RAW_DONORS MODEL - Ham veri
# ============================================================================
class RawDonor(Base):
    __tablename__ = "raw_donors"

    id = Column(Integer, primary_key=True)
    upload_id = Column(Integer, ForeignKey("uploads.id", ondelete="CASCADE"), nullable=False)
    row_number = Column(Integer)  # Excel'de hangi satırdan
    full_name = Column(String)
    email = Column(String)
    phone = Column(String)
    city = Column(String)
    extra_fields = Column(JSONB)  # Başka sütunlar
    created_at = Column(DateTime, default=datetime.utcnow)

    # İlişkiler
    upload = relationship("Upload", back_populates="raw_donors")
    normalized_donor = relationship("NormalizedDonor", back_populates="raw_donor", uselist=False)

    __table_args__ = (
        Index("idx_raw_donors_upload_id", "upload_id"),
        Index("idx_raw_donors_full_name", "full_name"),
    )

    def __repr__(self):
        return f"<RawDonor(id={self.id}, name='{self.full_name}')>"


# ============================================================================
# 3. NORMALIZED_DONORS MODEL - Temizlenmiş veri (Blocking anahtarları ile)
# ============================================================================
class NormalizedDonor(Base):
    __tablename__ = "normalized_donors"

    id = Column(Integer, primary_key=True)
    upload_id = Column(Integer, ForeignKey("uploads.id", ondelete="CASCADE"), nullable=False)
    raw_id = Column(Integer, ForeignKey("raw_donors.id", ondelete="CASCADE"))

    # Temel alanlar
    full_name = Column(String)
    first_name = Column(String)
    last_name = Column(String)
    email = Column(String)
    phone = Column(String)
    city = Column(String)

    # Blocking anahtarları (Performans için ÇOK ÖNEMLİ!)
    clean_tc = Column(String)
    clean_phone = Column(String)
    clean_email = Column(String)
    clean_city = Column(String)
    email_normalized_key = Column(String)  # ahmet+spam@gmail → ahmet@gmail
    name_phonetic_key = Column(String)     # Ahmet → AHM (Soundex)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # İlişkiler
    upload = relationship("Upload", back_populates="normalized_donors")
    raw_donor = relationship("RawDonor", back_populates="normalized_donor")
    matches_as_donor1 = relationship("Match", foreign_keys="Match.donor1_id", back_populates="donor1")
    matches_as_donor2 = relationship("Match", foreign_keys="Match.donor2_id", back_populates="donor2")
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

    def __repr__(self):
        return f"<NormalizedDonor(id={self.id}, name='{self.full_name}')>"


# ============================================================================
# 4. MATCHES MODEL - Eşleşme adayları (EN ÖNEMLİ)
# ============================================================================
class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True)
    upload_id = Column(Integer, ForeignKey("uploads.id", ondelete="CASCADE"), nullable=False)
    donor1_id = Column(Integer, ForeignKey("normalized_donors.id", ondelete="CASCADE"), nullable=False)
    donor2_id = Column(Integer, ForeignKey("normalized_donors.id", ondelete="CASCADE"), nullable=False)

    # Puanlama
    similarity = Column(Float)  # Basit benzerlik
    ml_score = Column(Float)   # ML modeli puanı (0-1)
    confidence = Column(Float) # Güven seviyesi

    # Karar
    status = Column(String(32), default='pending')  # pending, confirmed, rejected, merged
    decision_reason = Column(String(255))  # same_person, different_person, household_risk

    # Detaylı özellikler (JSON olarak tutulur)
    features = Column(JSONB)  # 15+ feature: name_sim, phone_match, vb.

    # Admin onayı (Audit trail!)
    approved_by = Column(String(255))    # Hangi operatör?
    approved_at = Column(DateTime)       # Ne zaman?
    rejected_reason = Column(String(255))
    rejected_at = Column(DateTime)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # İlişkiler
    upload = relationship("Upload", back_populates="matches")
    donor1 = relationship("NormalizedDonor", foreign_keys=[donor1_id], back_populates="matches_as_donor1")
    donor2 = relationship("NormalizedDonor", foreign_keys=[donor2_id], back_populates="matches_as_donor2")
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

    def __repr__(self):
        return f"<Match(id={self.id}, donor1={self.donor1_id}, donor2={self.donor2_id}, status='{self.status}')>"


# ============================================================================
# 5. ENTITIES MODEL - Gerçek/Birleştirilmiş Kişiler
# ============================================================================
class Entity(Base):
    __tablename__ = "entities"

    id = Column(Integer, primary_key=True)

    # Canonical (En iyi) veriler
    canonical_name = Column(String, nullable=False)
    canonical_email = Column(String)
    canonical_phone = Column(String)
    canonical_city = Column(String)

    # Metadata
    donor_count = Column(Integer, default=1)  # Kaç kayıt birleşti?
    merged_count = Column(Integer, default=0)  # Kaç merge işlemi?
    confidence_score = Column(Float, default=1.0)  # 0-1: Birleştirme güven

    # Audit trail
    merged_by = Column(String(255))  # Hangi admin yaptı?
    merged_at = Column(DateTime)     # Ne zaman?

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # İlişkiler
    entity_maps = relationship("EntityMap", back_populates="entity", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_entities_canonical_name", "canonical_name"),
        Index("idx_entities_canonical_email", "canonical_email"),
        Index("idx_entities_canonical_phone", "canonical_phone"),
        Index("idx_entities_created_at", "created_at"),
    )

    def __repr__(self):
        return f"<Entity(id={self.id}, name='{self.canonical_name}', donors={self.donor_count})>"


# ============================================================================
# 6. ENTITY_MAP MODEL - Mapping (EN ÖNEMLİ)
# Bu tablo her donor'ın hangi entity'ye ait olduğunu söyler
# ============================================================================
class EntityMap(Base):
    __tablename__ = "entity_map"

    id = Column(Integer, primary_key=True)
    entity_id = Column(Integer, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False)
    donor_id = Column(Integer, ForeignKey("normalized_donors.id", ondelete="CASCADE"), nullable=False)

    # Hangi match'den geliyor?
    match_id = Column(Integer, ForeignKey("matches.id", ondelete="SET NULL"))

    # Admin onayı
    created_by = Column(String(255))  # Kim yaptı? (system/operator_name)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Soft delete - Geri almak isteyebiliriz
    is_active = Column(Boolean, default=True)

    # İlişkiler
    entity = relationship("Entity", back_populates="entity_maps")
    donor = relationship("NormalizedDonor", back_populates="entity_maps")
    match = relationship("Match", back_populates="entity_map")

    __table_args__ = (
        UniqueConstraint("entity_id", "donor_id", name="uq_entity_donor"),
        Index("idx_entity_map_entity_id", "entity_id"),
        Index("idx_entity_map_donor_id", "donor_id"),
        Index("idx_entity_map_is_active", "is_active"),
    )

    def __repr__(self):
        return f"<EntityMap(entity={self.entity_id}, donor={self.donor_id})>"


# ============================================================================
# Export
# ============================================================================
__all__ = [
    "Base",
    "Upload",
    "RawDonor",
    "NormalizedDonor",
    "Match",
    "Entity",
    "EntityMap",
]
