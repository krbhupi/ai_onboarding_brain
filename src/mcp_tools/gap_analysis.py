"""MCP Tool: Gap analysis for missing documents."""
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from config.logging import logger
from src.models.database import (
    DocumentTracker, DocumentTypeMaster, StatusMaster,
    CandidateInfo, JobTracker, JobTypeMaster
)
from src.constants.constants import StatusType, JobType
from src.services.llm_service import LLMService


class GapAnalysisTool:
    """Tool for analyzing document gaps and updating status."""

    def __init__(self, db: AsyncSession, llm_service: LLMService = None):
        self.db = db
        self.llm_service = llm_service or LLMService()
        self.name = "gap_analysis"
        self.description = "Analyze document gaps and update tracker status"

    async def execute(
        self,
        candidate_id: int,
        received_documents: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Perform gap analysis for a candidate's documents.

        Args:
            candidate_id: Database ID of the candidate
            received_documents: Optional list of validated received documents

        Returns:
            Gap analysis result with missing and completed documents
        """
        # Get candidate info
        candidate = await self._get_candidate(candidate_id)
        if not candidate:
            return {
                "error": f"Candidate not found: {candidate_id}",
                "candidate_id": candidate_id
            }

        # Get required document types for this candidate
        required_types = await self._get_required_documents(candidate.candidate_type_id)

        # Get current document tracker entries
        tracker_entries = await self._get_tracker_entries(candidate_id)

        # If validation results provided, update statuses
        if received_documents:
            await self._update_document_status(tracker_entries, received_documents)

        # Refresh tracker entries after update
        tracker_entries = await self._get_tracker_entries(candidate_id)

        # Analyze gaps
        analysis = self._analyze_gaps(required_types, tracker_entries)

        # Get missing documents
        missing = self._get_missing_documents(required_types, tracker_entries)

        # Determine next steps
        next_steps = await self._determine_next_steps(
            analysis,
            candidate,
            len(missing)
        )

        # Use LLM for additional insights
        llm_analysis = await self.llm_service.analyze_gap(
            [t.document_name for t in required_types],
            received_documents or []
        )

        result = {
            "candidate_id": candidate_id,
            "cin": candidate.cin,
            "candidate_name": candidate.candidate_name,
            "required_documents": [t.document_name for t in required_types],
            "completed_documents": analysis["completed"],
            "pending_documents": analysis["pending"],
            "missing_documents": missing,
            "invalid_documents": analysis["invalid"],
            "completion_percentage": analysis["completion_percentage"],
            "next_steps": next_steps,
            "llm_insights": llm_analysis,
            "timestamp": datetime.utcnow().isoformat()
        }

        logger.info(
            f"Gap analysis for {candidate.cin}: "
            f"{len(analysis['completed'])}/{len(required_types)} documents complete"
        )

        return result

    async def _get_candidate(self, candidate_id: int) -> Optional[CandidateInfo]:
        """Get candidate by ID."""
        result = await self.db.execute(
            select(CandidateInfo).where(CandidateInfo.candidate_id == candidate_id)
        )
        return result.scalar_one_or_none()

    async def _get_required_documents(
        self,
        candidate_type_id: int
    ) -> List[DocumentTypeMaster]:
        """Get required document types for candidate type."""
        result = await self.db.execute(
            select(DocumentTypeMaster).where(DocumentTypeMaster.is_active == True)
        )
        all_types = result.scalars().all()

        # Filter based on candidate type
        if candidate_type_id == 1:  # Fresher
            return [t for t in all_types if t.fresher]
        elif candidate_type_id == 2:  # Experience
            return [t for t in all_types if t.experience]
        elif candidate_type_id == 3:  # Dev Partner
            return [t for t in all_types if t.dev_partner]

        return list(all_types)

    async def _get_tracker_entries(
        self,
        candidate_id: int
    ) -> List[DocumentTracker]:
        """Get all document tracker entries for candidate."""
        result = await self.db.execute(
            select(DocumentTracker).where(
                DocumentTracker.candidate_id == candidate_id,
                DocumentTracker.is_active == True
            )
        )
        return list(result.scalars().all())

    async def _update_document_status(
        self,
        tracker_entries: List[DocumentTracker],
        received_documents: List[Dict[str, Any]]
    ) -> None:
        """Update document status based on validation results."""
        # Get status IDs
        complete_status = await self._get_status_id("complete")
        pending_status = await self._get_status_id("pending")

        for received in received_documents:
            # Find matching tracker entry
            for entry in tracker_entries:
                if received.get("expected_type") == entry.document_type.document_name:
                    if received.get("is_valid"):
                        entry.status_id = complete_status
                        entry.comments = f"Validated on {datetime.utcnow().isoformat()}"
                    else:
                        entry.status_id = pending_status
                        entry.comments = f"Invalid: {received.get('reason', 'Unknown')}"

                    entry.updated_on = datetime.utcnow()
                    self.db.add(entry)
                    break

        await self.db.commit()

    async def _get_status_id(self, status_type: str) -> int:
        """Get status ID by type."""
        result = await self.db.execute(
            select(StatusMaster).where(StatusMaster.status_type == status_type)
        )
        status = result.scalar_one_or_none()
        return status.status_id if status else StatusType.PENDING

    def _analyze_gaps(
        self,
        required_types: List[DocumentTypeMaster],
        tracker_entries: List[DocumentTracker]
    ) -> Dict[str, Any]:
        """Analyze document status gaps."""
        completed = []
        pending = []
        invalid = []

        required_ids = {t.document_type_id for t in required_types}

        for entry in tracker_entries:
            if entry.document_type_id not in required_ids:
                continue

            doc_name = entry.document_type.document_name if entry.document_type else "Unknown"

            if entry.status_id == StatusType.COMPLETE:
                completed.append(doc_name)
            elif entry.status_id == StatusType.FAILED:
                invalid.append({
                    "name": doc_name,
                    "reason": entry.comments or "Validation failed"
                })
            else:
                pending.append(doc_name)

        total_required = len(required_types)
        completion_percentage = (
            (len(completed) / total_required * 100) if total_required > 0 else 0
        )

        return {
            "completed": completed,
            "pending": pending,
            "invalid": invalid,
            "completion_percentage": round(completion_percentage, 2)
        }

    def _get_missing_documents(
        self,
        required_types: List[DocumentTypeMaster],
        tracker_entries: List[DocumentTracker]
    ) -> List[str]:
        """Get list of documents not yet submitted."""
        submitted_ids = {e.document_type_id for e in tracker_entries}

        missing = []
        for doc_type in required_types:
            if doc_type.document_type_id not in submitted_ids:
                missing.append(doc_type.document_name)

        return missing

    async def _determine_next_steps(
        self,
        analysis: Dict[str, Any],
        candidate: CandidateInfo,
        missing_count: int
    ) -> List[str]:
        """Determine next actions based on gap analysis."""
        steps = []

        if analysis["completion_percentage"] == 100:
            steps.append("All documents received - proceed to verification")
            steps.append("Update candidate status to 'documents_complete'")
            steps.append("Notify HR for final approval")

        elif missing_count > 0:
            steps.append(f"Send follow-up email for {missing_count} missing documents")
            steps.append("Schedule reminder for 3 business days")

            if len(analysis["invalid"]) > 0:
                steps.append(f"Request re-submission for {len(analysis['invalid'])} invalid documents")

        elif len(analysis["pending"]) > 0:
            steps.append("Process pending documents")
            steps.append("Run OCR validation on new documents")

        # Create follow-up job if needed
        if missing_count > 0:
            await self._create_followup_job(candidate.candidate_id)

        return steps

    async def _create_followup_job(self, candidate_id: int) -> None:
        """Create a follow-up job for missing documents."""
        job_type_result = await self.db.execute(
            select(JobTypeMaster).where(
                JobTypeMaster.job_type == "followup_mail"
            )
        )
        job_type = job_type_result.scalar_one_or_none()

        if job_type:
            pending_status = await self._get_status_id("pending")

            job = JobTracker(
                candidate_id=candidate_id,
                job_type_id=job_type.job_type_id,
                status_id=pending_status,
                action_date=datetime.utcnow().date(),
                human_action_required=True,
                start_time=datetime.utcnow()
            )
            self.db.add(job)
            await self.db.commit()

    def get_tool_schema(self) -> Dict[str, Any]:
        """Return the tool schema for MCP."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "candidate_id": {
                        "type": "integer",
                        "description": "Database ID of the candidate"
                    },
                    "received_documents": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "expected_type": {"type": "string"},
                                "is_valid": {"type": "boolean"},
                                "path": {"type": "string"}
                            }
                        },
                        "description": "List of validated received documents"
                    }
                },
                "required": ["candidate_id"]
            }
        }