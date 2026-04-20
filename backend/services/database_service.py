"""
Database Service Layer - ORM modelleriyle çalışan servis fonksiyonları
"""
from datetime import datetime
from typing import List, Optional, Dict, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from backend.models.database import (
    Upload, RawDonor, NormalizedDonor, Match, Entity, EntityMap
)


# ============================================================================
# UPLOADS SERVICE
# ============================================================================

class UploadService:
    """Upload (dosya yükleme) işlemleri"""
    
    @staticmethod
    def create_upload(
        session: Session,
        file_name: str,
        file_size_bytes: int,
        created_by: str = "system"
    ) -> Upload:
        """Yeni upload kaydı oluştur"""
        upload = Upload(
            file_name=file_name,
            file_size_bytes=file_size_bytes,
            created_by=created_by,
            status='pending'
        )
        session.add(upload)
        session.flush()
        return upload

    @staticmethod
    def get_upload(session: Session, upload_id: int) -> Optional[Upload]:
        """Upload'ı ID'siyle getir"""
        return session.query(Upload).filter(Upload.id == upload_id).first()

    @staticmethod
    def update_upload_status(
        session: Session,
        upload_id: int,
        status: str,
        error_message: str = None
    ) -> Upload:
        """Upload'ın durumunu güncelle"""
        upload = UploadService.get_upload(session, upload_id)
        if upload:
            upload.status = status
            if error_message:
                upload.error_message = error_message
            upload.updated_at = datetime.utcnow()
        return upload

    @staticmethod
    def update_total_records(session: Session, upload_id: int, count: int) -> Upload:
        """Upload'da kaç kayıt işlendiğini kayıt et"""
        upload = UploadService.get_upload(session, upload_id)
        if upload:
            upload.total_records = count
        return upload


# ============================================================================
# RAW_DONORS SERVICE
# ============================================================================

class RawDonorService:
    """Ham veri (raw) işlemleri"""
    
    @staticmethod
    def create_raw_donor(
        session: Session,
        upload_id: int,
        row_number: int,
        full_name: str,
        email: str = None,
        phone: str = None,
        city: str = None,
        extra_fields: Dict = None
    ) -> RawDonor:
        """Yeni raw donor kaydı oluştur"""
        raw_donor = RawDonor(
            upload_id=upload_id,
            row_number=row_number,
            full_name=full_name,
            email=email,
            phone=phone,
            city=city,
            extra_fields=extra_fields
        )
        session.add(raw_donor)
        session.flush()
        return raw_donor

    @staticmethod
    def create_raw_donors_batch(
        session: Session,
        upload_id: int,
        records: List[Dict]
    ) -> List[RawDonor]:
        """Toplu raw donor kaydı oluştur"""
        raw_donors = []
        for idx, record in enumerate(records, start=1):
            raw_donor = RawDonor(
                upload_id=upload_id,
                row_number=idx,
                full_name=record.get("adSoyad"),
                email=record.get("email"),
                phone=record.get("telefon"),
                city=record.get("sehir"),
                extra_fields=record.get("extra", {})
            )
            session.add(raw_donor)
            raw_donors.append(raw_donor)
        session.flush()
        return raw_donors

    @staticmethod
    def get_raw_donors_by_upload(session: Session, upload_id: int) -> List[RawDonor]:
        """Upload'a ait tüm raw donor'ları getir"""
        return session.query(RawDonor).filter(
            RawDonor.upload_id == upload_id
        ).all()


# ============================================================================
# NORMALIZED_DONORS SERVICE
# ============================================================================

class NormalizedDonorService:
    """Temizlenmiş veri (normalized) işlemleri"""
    
    @staticmethod
    def create_normalized_donor(
        session: Session,
        upload_id: int,
        raw_id: int,
        full_name: str,
        first_name: str,
        last_name: str,
        email: str = None,
        phone: str = None,
        city: str = None,
        clean_tc: str = None,
        clean_phone: str = None,
        clean_email: str = None,
        clean_city: str = None,
        email_normalized_key: str = None,
        name_phonetic_key: str = None
    ) -> NormalizedDonor:
        """Yeni normalized donor kaydı oluştur"""
        norm_donor = NormalizedDonor(
            upload_id=upload_id,
            raw_id=raw_id,
            full_name=full_name,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            city=city,
            clean_tc=clean_tc,
            clean_phone=clean_phone,
            clean_email=clean_email,
            clean_city=clean_city,
            email_normalized_key=email_normalized_key,
            name_phonetic_key=name_phonetic_key
        )
        session.add(norm_donor)
        session.flush()
        return norm_donor

    @staticmethod
    def get_normalized_donor(session: Session, donor_id: int) -> Optional[NormalizedDonor]:
        """Normalized donor'ı ID'siyle getir"""
        return session.query(NormalizedDonor).filter(
            NormalizedDonor.id == donor_id
        ).first()

    @staticmethod
    def get_normalized_donors_by_upload(
        session: Session, 
        upload_id: int
    ) -> List[NormalizedDonor]:
        """Upload'a ait tüm normalized donor'ları getir"""
        return session.query(NormalizedDonor).filter(
            NormalizedDonor.upload_id == upload_id
        ).all()

    @staticmethod
    def find_by_blocking_key(
        session: Session,
        key_column: str,
        key_value: str
    ) -> List[NormalizedDonor]:
        """Blocking anahtarına göre donor'ları bul (performans)"""
        # Örnek: find_by_blocking_key(session, "clean_phone", "5551234567")
        if key_column == "clean_tc":
            return session.query(NormalizedDonor).filter(
                NormalizedDonor.clean_tc == key_value
            ).all()
        elif key_column == "clean_phone":
            return session.query(NormalizedDonor).filter(
                NormalizedDonor.clean_phone == key_value
            ).all()
        elif key_column == "email_normalized_key":
            return session.query(NormalizedDonor).filter(
                NormalizedDonor.email_normalized_key == key_value
            ).all()
        elif key_column == "name_phonetic_key":
            return session.query(NormalizedDonor).filter(
                NormalizedDonor.name_phonetic_key == key_value
            ).all()
        elif key_column == "clean_city":
            return session.query(NormalizedDonor).filter(
                NormalizedDonor.clean_city == key_value
            ).all()
        return []


# ============================================================================
# MATCHES SERVICE
# ============================================================================

class MatchService:
    """Eşleşme (match) işlemleri"""
    
    @staticmethod
    def create_match(
        session: Session,
        upload_id: int,
        donor1_id: int,
        donor2_id: int,
        similarity: float = None,
        ml_score: float = None,
        confidence: float = None,
        features: Dict = None,
        decision_reason: str = None
    ) -> Match:
        """Yeni match kaydı oluştur"""
        # Ensure donor1_id < donor2_id to avoid duplicates
        if donor1_id > donor2_id:
            donor1_id, donor2_id = donor2_id, donor1_id
            
        match = Match(
            upload_id=upload_id,
            donor1_id=donor1_id,
            donor2_id=donor2_id,
            similarity=similarity,
            ml_score=ml_score,
            confidence=confidence,
            features=features,
            decision_reason=decision_reason,
            status='pending'
        )
        session.add(match)
        session.flush()
        return match

    @staticmethod
    def create_matches_batch(
        session: Session,
        upload_id: int,
        matches_data: List[Dict]
    ) -> List[Match]:
        """Toplu match kaydı oluştur"""
        matches = []
        for data in matches_data:
            match = Match(
                upload_id=upload_id,
                donor1_id=data["donor1_id"],
                donor2_id=data["donor2_id"],
                similarity=data.get("similarity"),
                ml_score=data.get("ml_score"),
                confidence=data.get("confidence"),
                features=data.get("features"),
                decision_reason=data.get("decision_reason"),
                status='pending'
            )
            session.add(match)
            matches.append(match)
        session.flush()
        return matches

    @staticmethod
    def get_match(session: Session, match_id: int) -> Optional[Match]:
        """Match'ı ID'siyle getir"""
        return session.query(Match).filter(Match.id == match_id).first()

    @staticmethod
    def get_pending_matches(
        session: Session,
        upload_id: int = None,
        limit: int = 100
    ) -> List[Match]:
        """Henüz onaylanmamış match'leri getir"""
        query = session.query(Match).filter(Match.status == 'pending')
        if upload_id:
            query = query.filter(Match.upload_id == upload_id)
        return query.order_by(Match.ml_score.desc()).limit(limit).all()

    @staticmethod
    def approve_match(
        session: Session,
        match_id: int,
        approved_by: str = "system"
    ) -> Match:
        """Match'i onayla"""
        match = MatchService.get_match(session, match_id)
        if match:
            match.status = 'confirmed'
            match.approved_by = approved_by
            match.approved_at = datetime.utcnow()
        return match

    @staticmethod
    def reject_match(
        session: Session,
        match_id: int,
        reason: str = None,
        rejected_by: str = "system"
    ) -> Match:
        """Match'i reddet"""
        match = MatchService.get_match(session, match_id)
        if match:
            match.status = 'rejected'
            match.rejected_reason = reason
            match.rejected_at = datetime.utcnow()
            match.approved_by = rejected_by
        return match

    @staticmethod
    def get_matches_by_upload(
        session: Session,
        upload_id: int,
        status: str = None
    ) -> List[Match]:
        """Upload'a ait match'leri getir"""
        query = session.query(Match).filter(Match.upload_id == upload_id)
        if status:
            query = query.filter(Match.status == status)
        return query.all()

    @staticmethod
    def get_match_statistics(
        session: Session,
        upload_id: int
    ) -> Dict:
        """Upload'ın match istatistikleri"""
        matches = MatchService.get_matches_by_upload(session, upload_id)
        
        total = len(matches)
        pending = sum(1 for m in matches if m.status == 'pending')
        confirmed = sum(1 for m in matches if m.status == 'confirmed')
        rejected = sum(1 for m in matches if m.status == 'rejected')
        merged = sum(1 for m in matches if m.status == 'merged')
        
        avg_score = sum(m.ml_score or 0 for m in matches) / total if total > 0 else 0
        
        return {
            "total": total,
            "pending": pending,
            "confirmed": confirmed,
            "rejected": rejected,
            "merged": merged,
            "avg_ml_score": round(avg_score, 4)
        }


# ============================================================================
# ENTITIES SERVICE
# ============================================================================

class EntityService:
    """Varlık (entity) işlemleri - Birleştirilmiş kişiler"""
    
    @staticmethod
    def create_entity(
        session: Session,
        canonical_name: str,
        canonical_email: str = None,
        canonical_phone: str = None,
        canonical_city: str = None,
        merged_by: str = "system",
        confidence_score: float = 1.0
    ) -> Entity:
        """Yeni entity (birleştirilmiş kişi) oluştur"""
        entity = Entity(
            canonical_name=canonical_name,
            canonical_email=canonical_email,
            canonical_phone=canonical_phone,
            canonical_city=canonical_city,
            merged_by=merged_by,
            merged_at=datetime.utcnow(),
            confidence_score=confidence_score,
            donor_count=0,
            merged_count=0
        )
        session.add(entity)
        session.flush()
        return entity

    @staticmethod
    def get_entity(session: Session, entity_id: int) -> Optional[Entity]:
        """Entity'yi ID'siyle getir"""
        return session.query(Entity).filter(Entity.id == entity_id).first()

    @staticmethod
    def find_entity_by_canonical_name(
        session: Session,
        canonical_name: str
    ) -> Optional[Entity]:
        """Entity'yi canonical isim'le bul"""
        return session.query(Entity).filter(
            Entity.canonical_name == canonical_name
        ).first()

    @staticmethod
    def update_entity(
        session: Session,
        entity_id: int,
        canonical_email: str = None,
        canonical_phone: str = None,
        canonical_city: str = None
    ) -> Entity:
        """Entity'yi güncelle"""
        entity = EntityService.get_entity(session, entity_id)
        if entity:
            if canonical_email:
                entity.canonical_email = canonical_email
            if canonical_phone:
                entity.canonical_phone = canonical_phone
            if canonical_city:
                entity.canonical_city = canonical_city
            entity.updated_at = datetime.utcnow()
        return entity


# ============================================================================
# ENTITY_MAP SERVICE
# ============================================================================

class EntityMapService:
    """Entity mapping işlemleri - Donor'lar entity'ye bağlanır"""
    
    @staticmethod
    def create_entity_map(
        session: Session,
        entity_id: int,
        donor_id: int,
        match_id: int = None,
        created_by: str = "system"
    ) -> EntityMap:
        """Donor'ı entity'ye mapla"""
        entity_map = EntityMap(
            entity_id=entity_id,
            donor_id=donor_id,
            match_id=match_id,
            created_by=created_by,
            is_active=True
        )
        session.add(entity_map)
        session.flush()
        
        # Entity'nin donor sayısını güncelle
        entity = EntityService.get_entity(session, entity_id)
        if entity:
            entity.donor_count += 1
            entity.updated_at = datetime.utcnow()
        
        return entity_map

    @staticmethod
    def get_entity_map(session: Session, entity_map_id: int) -> Optional[EntityMap]:
        """Entity map'i getir"""
        return session.query(EntityMap).filter(
            EntityMap.id == entity_map_id
        ).first()

    @staticmethod
    def get_entity_donors(
        session: Session,
        entity_id: int,
        active_only: bool = True
    ) -> List[NormalizedDonor]:
        """Entity'ye bağlı tüm donor'ları getir"""
        query = session.query(NormalizedDonor).join(
            EntityMap, NormalizedDonor.id == EntityMap.donor_id
        ).filter(EntityMap.entity_id == entity_id)
        
        if active_only:
            query = query.filter(EntityMap.is_active == True)
        
        return query.all()

    @staticmethod
    def deactivate_entity_map(
        session: Session,
        entity_map_id: int
    ) -> EntityMap:
        """Entity map'i deaktif et (soft delete)"""
        entity_map = EntityMapService.get_entity_map(session, entity_map_id)
        if entity_map:
            entity_map.is_active = False
            
            # Entity'nin donor sayısını azalt
            entity = EntityService.get_entity(session, entity_map.entity_id)
            if entity and entity.donor_count > 0:
                entity.donor_count -= 1
        
        return entity_map

    @staticmethod
    def get_entity_maps_by_donor(
        session: Session,
        donor_id: int
    ) -> List[EntityMap]:
        """Donor'ın tüm entity mapping'lerini getir"""
        return session.query(EntityMap).filter(
            EntityMap.donor_id == donor_id,
            EntityMap.is_active == True
        ).all()


# ============================================================================
# Composite Operations (Kompleks işlemler)
# ============================================================================

class CompositeService:
    """Çok adımlı işlemler"""
    
    @staticmethod
    def merge_donors_to_entity(
        session: Session,
        donor_ids: List[int],
        canonical_name: str,
        canonical_email: str = None,
        canonical_phone: str = None,
        canonical_city: str = None,
        merged_by: str = "system",
        match_id: int = None
    ) -> Entity:
        """Bir match'e ait iki donor'ı entity'ye birleştir"""
        # Entity oluştur
        entity = EntityService.create_entity(
            session,
            canonical_name,
            canonical_email,
            canonical_phone,
            canonical_city,
            merged_by
        )
        
        # Tüm donor'ları entity'ye mapla
        for donor_id in donor_ids:
            EntityMapService.create_entity_map(
                session,
                entity.id,
                donor_id,
                match_id,
                merged_by
            )
        
        # Match'i merged olarak işaretle
        if match_id:
            match = MatchService.get_match(session, match_id)
            if match:
                match.status = 'merged'
                match.updated_at = datetime.utcnow()
        
        return entity

    @staticmethod
    def workflow_upload_to_normalized(
        session: Session,
        upload_id: int,
        records: List[Dict],
        normalize_func
    ) -> Tuple[int, int]:
        """
        Workflow: Raw data → Normalized data
        
        Args:
            upload_id: Upload ID
            records: Raw kayıtlar
            normalize_func: Normalizasyon fonksiyonu (name → first_name, last_name vs)
        
        Returns:
            (raw_count, normalized_count)
        """
        # Raw donor'ları oluştur
        raw_donors = RawDonorService.create_raw_donors_batch(
            session, upload_id, records
        )
        session.commit()
        
        # Normalize işlemi
        for raw_donor in raw_donors:
            normalized_data = normalize_func(raw_donor.full_name)
            
            NormalizedDonorService.create_normalized_donor(
                session,
                upload_id,
                raw_donor.id,
                full_name=raw_donor.full_name,
                first_name=normalized_data.get("first_name", ""),
                last_name=normalized_data.get("last_name", ""),
                email=raw_donor.email,
                phone=raw_donor.phone,
                city=raw_donor.city,
                clean_tc=normalized_data.get("clean_tc"),
                clean_phone=normalized_data.get("clean_phone"),
                clean_email=normalized_data.get("clean_email"),
                clean_city=normalized_data.get("clean_city"),
                email_normalized_key=normalized_data.get("email_normalized_key"),
                name_phonetic_key=normalized_data.get("name_phonetic_key")
            )
        
        session.commit()
        
        return len(raw_donors), session.query(NormalizedDonor).filter(
            NormalizedDonor.upload_id == upload_id
        ).count()


# ============================================================================
# Export
# ============================================================================
__all__ = [
    "UploadService",
    "RawDonorService",
    "NormalizedDonorService",
    "MatchService",
    "EntityService",
    "EntityMapService",
    "CompositeService",
]
