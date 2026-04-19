"""Document service for file storage and metadata handling."""
import os
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from config.settings import get_settings
from config.logging import logger
from src.models.database import DocumentTracker, DocumentTypeMaster, StatusMaster
from src.constants.constants import StatusType, DocumentCategory

settings = get_settings()


class DocumentService:
    """Service for document storage and management."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.storage_path = Path(settings.DOCUMENT_STORAGE_PATH)
        self.temp_path = Path(settings.TEMP_STORAGE_PATH)
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Ensure storage directories exist."""
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.temp_path.mkdir(parents=True, exist_ok=True)

        # Create category subdirectories
        for category in [DocumentCategory.EDUCATION, DocumentCategory.EMPLOYMENT,
                         DocumentCategory.PERSONAL_DETAILS, DocumentCategory.UNMATCHED]:
            (self.storage_path / category).mkdir(exist_ok=True)

    def get_candidate_directory(self, cin: str) -> Path:
        """Get or create directory for a candidate's documents."""
        candidate_dir = self.storage_path / cin
        candidate_dir.mkdir(parents=True, exist_ok=True)
        return candidate_dir

    async def save_document(
        self,
        cin: str,
        filename: str,
        content: bytes,
        category: Optional[str] = None
    ) -> Dict[str, Any]:
        """Save a document to the appropriate directory."""
        candidate_dir = self.get_candidate_directory(cin)

        # Determine category subdirectory
        if category and category != DocumentCategory.UNMATCHED:
            save_dir = candidate_dir / category
            save_dir.mkdir(exist_ok=True)
        else:
            save_dir = candidate_dir / DocumentCategory.UNMATCHED
            save_dir.mkdir(exist_ok=True)

        # Generate unique filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_filename = f"{timestamp}_{filename}"
        file_path = save_dir / safe_filename

        # Write file
        with open(file_path, "wb") as f:
            f.write(content)

        logger.info(f"Saved document: {file_path}")

        return {
            "path": str(file_path),
            "filename": safe_filename,
            "original_filename": filename,
            "size": len(content),
            "category": category or DocumentCategory.UNMATCHED,
            "cin": cin
        }

    async def get_document_types_for_candidate(
        self,
        candidate_type_id: int
    ) -> List[DocumentTypeMaster]:
        """Get required document types for a candidate type."""
        result = await self.db.execute(
            select(DocumentTypeMaster).where(
                DocumentTypeMaster.is_active == True
            )
        )
        all_types = result.scalars().all()

        # Filter based on candidate type
        if candidate_type_id == 1:  # Fresher
            return [t for t in all_types if t.fresher]
        elif candidate_type_id == 2:  # Experience
            return [t for t in all_types if t.experience]
        elif candidate_type_id == 3:  # Dev Partner
            return [t for t in all_types if t.dev_partner]
        return all_types

    async def create_document_tracker(
        self,
        candidate_id: int,
        document_type_id: int,
        job_id: int,
        document_store_id: Optional[int] = None,
        comments: Optional[str] = None
    ) -> DocumentTracker:
        """Create a new document tracker entry."""
        # Get pending status
        status_result = await self.db.execute(
            select(StatusMaster).where(StatusMaster.status_type == "pending")
        )
        pending_status = status_result.scalar_one_or_none()
        status_id = pending_status.status_id if pending_status else StatusType.PENDING

        tracker = DocumentTracker(
            candidate_id=candidate_id,
            document_type_id=document_type_id,
            document_store_id=document_store_id,
            status_id=status_id,
            job_id=job_id,
            comments=comments,
            document_received_on=datetime.now().date()
        )

        self.db.add(tracker)
        await self.db.commit()
        await self.db.refresh(tracker)

        return tracker

    async def update_document_status(
        self,
        document_tracker_id: int,
        status_id: int,
        comments: Optional[str] = None
    ) -> Optional[DocumentTracker]:
        """Update document tracker status."""
        result = await self.db.execute(
            select(DocumentTracker).where(
                DocumentTracker.document_tracker_id == document_tracker_id
            )
        )
        tracker = result.scalar_one_or_none()

        if tracker:
            tracker.status_id = status_id
            tracker.updated_on = datetime.utcnow()
            if comments:
                tracker.comments = comments
            self.db.add(tracker)
            await self.db.commit()
            await self.db.refresh(tracker)

        return tracker

    async def get_pending_documents(self, candidate_id: int) -> List[DocumentTracker]:
        """Get all pending documents for a candidate."""
        pending_status = await self._get_status_id("pending")

        result = await self.db.execute(
            select(DocumentTracker).where(
                DocumentTracker.candidate_id == candidate_id,
                DocumentTracker.status_id == pending_status,
                DocumentTracker.is_active == True
            )
        )
        return result.scalars().all()

    async def get_completed_documents(
        self,
        candidate_id: int
    ) -> List[DocumentTracker]:
        """Get all completed documents for a candidate."""
        complete_status = await self._get_status_id("complete")

        result = await self.db.execute(
            select(DocumentTracker).where(
                DocumentTracker.candidate_id == candidate_id,
                DocumentTracker.status_id == complete_status,
                DocumentTracker.is_active == True
            )
        )
        return result.scalars().all()

    async def _get_status_id(self, status_type: str) -> int:
        """Get status ID by type name."""
        result = await self.db.execute(
            select(StatusMaster).where(StatusMaster.status_type == status_type)
        )
        status = result.scalar_one_or_none()
        return status.status_id if status else StatusType.PENDING

    def categorize_document(self, document_type: str) -> str:
        """Determine document category based on type."""
        education_docs = [
            "10th marksheet", "12th marksheet", "degree certificate",
            "graduation certificate", "post graduation certificate",
            "diploma certificate", "marksheet", "degree"
        ]
        employment_docs = [
            "relieving letter", "experience certificate", "salary slip",
            "form 16", "offer letter", "appointment letter"
        ]
        personal_docs = [
            "aadhaar card", "pan card", "passport photo",
            "bank passbook", "cancelled cheque", "passport"
        ]

        doc_lower = document_type.lower()

        if any(edu in doc_lower for edu in education_docs):
            return DocumentCategory.EDUCATION
        elif any(emp in doc_lower for emp in employment_docs):
            return DocumentCategory.EMPLOYMENT
        elif any(per in doc_lower for per in personal_docs):
            return DocumentCategory.PERSONAL_DETAILS

        return DocumentCategory.UNMATCHED

    async def move_to_category(
        self,
        source_path: Path,
        cin: str,
        category: str
    ) -> Path:
        """Move document to appropriate category directory."""
        candidate_dir = self.get_candidate_directory(cin)
        category_dir = candidate_dir / category
        category_dir.mkdir(exist_ok=True)

        destination = category_dir / source_path.name

        if source_path.exists():
            shutil.move(str(source_path), str(destination))
            logger.info(f"Moved document to {destination}")

        return destination