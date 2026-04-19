"""Main agent orchestrator for HR onboarding workflow."""
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from config.logging import logger
from config.settings import get_settings
from src.models.database import JobTracker, CandidateInfo, StatusMaster
from src.constants.constants import JobType, StatusType, HumanAction

from src.services.email_service import EmailService
from src.services.document_service import DocumentService
from src.services.llm_service import LLMService

from src.mcp_tools.save_attachment import SaveAttachmentTool
from src.mcp_tools.followup_classification import FollowupClassificationTool
from src.mcp_tools.ocr_validation import OCRValidationTool
from src.mcp_tools.segregation import SegregationTool
from src.mcp_tools.gap_analysis import GapAnalysisTool
from src.mcp_tools.draft_prepare import DraftPrepareTool

settings = get_settings()


class OnboardingAgent:
    """
    Agent that orchestrates the entire HR onboarding workflow.

    Responsibilities:
    - Monitor inbox for candidate replies
    - Process attachments
    - Run OCR validation
    - Perform gap analysis
    - Generate follow-up emails
    - Maintain workflow state
    """

    def __init__(self, db: AsyncSession):
        self.db = db

        # Initialize services
        self.email_service = EmailService()
        self.document_service = DocumentService(db)
        self.llm_service = LLMService()

        # Initialize MCP tools
        self.save_attachment_tool = SaveAttachmentTool(
            email_service=self.email_service,
            document_service=self.document_service
        )
        self.classification_tool = FollowupClassificationTool()
        self.ocr_tool = OCRValidationTool(self.llm_service)
        self.segregation_tool = SegregationTool()
        self.gap_analysis_tool = GapAnalysisTool(db, self.llm_service)
        self.draft_tool = DraftPrepareTool(db, self.llm_service)

    async def process_job(self, job_id: int) -> Dict[str, Any]:
        """
        Process a single job from the job tracker.

        Args:
            job_id: Job tracker ID

        Returns:
            Processing result
        """
        # Get job details
        job = await self._get_job(job_id)
        if not job:
            return {"error": f"Job not found: {job_id}"}

        # Update job status to in_progress
        await self._update_job_status(job, StatusType.IN_PROGRESS)

        try:
            # Route to appropriate handler based on job type
            job_type = JobType.NAMES.get(job.job_type_id, "unknown")

            if job_type == "mail_send":
                result = await self._handle_mail_send(job)
            elif job_type == "followup_mail":
                result = await self._handle_followup(job)
            elif job_type == "read_inbox":
                result = await self._handle_read_inbox(job)
            elif job_type == "save_attachment":
                result = await self._handle_save_attachment(job)
            elif job_type == "ocr_validation":
                result = await self._handle_ocr_validation(job)
            elif job_type == "segregation":
                result = await self._handle_segregation(job)
            elif job_type == "gap_analysis":
                result = await self._handle_gap_analysis(job)
            else:
                result = {"error": f"Unknown job type: {job_type}"}

            # Update job status based on result
            if result.get("error"):
                await self._update_job_status(job, StatusType.FAILED, result["error"])
            else:
                await self._update_job_status(job, StatusType.COMPLETE)

            return result

        except Exception as e:
            logger.error(f"Error processing job {job_id}: {e}")
            await self._update_job_status(job, StatusType.FAILED, str(e))
            return {"error": str(e)}

    async def _handle_mail_send(self, job: JobTracker) -> Dict[str, Any]:
        """Handle initial mail send job."""
        candidate = await self._get_candidate(job.candidate_id)
        if not candidate:
            return {"error": "Candidate not found"}

        # Generate draft if not exists
        if not job.draft_mail:
            draft_result = await self.draft_tool.execute(job.job_id, "initial_request")
            if draft_result.get("error"):
                return draft_result

            job.draft_mail = draft_result["body"]
            await self.db.commit()

        # Check if human action required
        if job.human_action_required and not job.human_action:
            return {
                "status": "waiting_for_approval",
                "draft": job.draft_mail,
                "candidate_email": candidate.personal_email_id
            }

        # Send email if approved
        if job.human_action == HumanAction.ACCEPT:
            sent = await self.email_service.send_email(
                to_address=candidate.personal_email_id,
                subject="Document Submission Required - HR Onboarding",
                body=job.draft_mail
            )

            if sent:
                # Create follow-up job
                await self._create_followup_job(candidate.candidate_id)
                return {"status": "sent", "draft": job.draft_mail}
            else:
                return {"error": "Failed to send email"}

        return {"status": "pending", "draft": job.draft_mail}

    async def _handle_followup(self, job: JobTracker) -> Dict[str, Any]:
        """Handle follow-up email job."""
        candidate = await self._get_candidate(job.candidate_id)
        if not candidate:
            return {"error": "Candidate not found"}

        # Check if action date is today or past
        if job.action_date and job.action_date > datetime.utcnow().date():
            return {"status": "scheduled", "action_date": job.action_date.isoformat()}

        # Generate follow-up draft
        draft_result = await self.draft_tool.execute(job.job_id, "followup_reminder")

        if draft_result.get("error"):
            return draft_result

        # Send follow-up email
        sent = await self.email_service.send_email(
            to_address=candidate.personal_email_id,
            subject=draft_result["subject"],
            body=draft_result["body"]
        )

        if sent:
            # Schedule next follow-up
            await self._create_followup_job(
                candidate.candidate_id,
                days_delay=3  # Next follow-up in 3 days
            )
            return {"status": "sent", "draft": draft_result}

        return {"error": "Failed to send follow-up email"}

    async def _handle_read_inbox(self, job: JobTracker) -> Dict[str, Any]:
        """Handle inbox reading job."""
        emails = await self.email_service.read_inbox(unread_only=True)

        processed = []
        for email_data in emails:
            # Classify email
            classification = await self.classification_tool.execute(
                email_body=email_data["body"],
                email_subject=email_data["subject"]
            )

            # Find candidate by email
            candidate = await self._find_candidate_by_email(email_data["from_address"])

            if candidate:
                # Create save_attachment job for attachments
                if email_data.get("attachments"):
                    await self._create_attachment_job(
                        candidate.candidate_id,
                        email_data["attachments"]
                    )

            processed.append({
                "from": email_data["from_address"],
                "subject": email_data["subject"],
                "classification": classification
            })

        return {
            "status": "processed",
            "emails_read": len(emails),
            "results": processed
        }

    async def _handle_save_attachment(self, job: JobTracker) -> Dict[str, Any]:
        """Handle attachment saving job."""
        candidate = await self._get_candidate(job.candidate_id)
        if not candidate:
            return {"error": "Candidate not found"}

        # Get attachments from job remark (stored as JSON)
        import json
        try:
            attachments = json.loads(job.remark) if job.remark else []
        except json.JSONDecodeError:
            attachments = []

        result = await self.save_attachment_tool.execute(
            cin=candidate.cin,
            attachments=attachments,
            job_id=job.job_id,
            candidate_id=candidate.candidate_id
        )

        # Trigger OCR validation for saved documents
        if result.get("saved_count", 0) > 0:
            await self._create_ocr_job(candidate.candidate_id, result["documents"])

        return result

    async def _handle_ocr_validation(self, job: JobTracker) -> Dict[str, Any]:
        """Handle OCR validation job."""
        import json
        try:
            documents = json.loads(job.remark) if job.remark else []
        except json.JSONDecodeError:
            documents = []

        results = []
        for doc in documents:
            result = await self.ocr_tool.execute(
                document_path=doc["path"],
                expected_type=doc["expected_type"]
            )
            results.append(result)

        # Trigger segregation job
        await self._create_segregation_job(job.candidate_id, documents, results)

        return {
            "status": "validated",
            "documents_processed": len(results),
            "results": results
        }

    async def _handle_segregation(self, job: JobTracker) -> Dict[str, Any]:
        """Handle document segregation job."""
        import json
        try:
            data = json.loads(job.remark) if job.remark else {}
        except json.JSONDecodeError:
            data = {}

        candidate = await self._get_candidate(job.candidate_id)
        if not candidate:
            return {"error": "Candidate not found"}

        result = await self.segregation_tool.execute(
            cin=candidate.cin,
            documents=data.get("documents", []),
            validation_results=data.get("validation_results", [])
        )

        # Trigger gap analysis
        await self._create_gap_analysis_job(candidate.candidate_id)

        return result

    async def _handle_gap_analysis(self, job: JobTracker) -> Dict[str, Any]:
        """Handle gap analysis job."""
        result = await self.gap_analysis_tool.execute(job.candidate_id)

        # If documents are missing, create follow-up job
        if len(result.get("missing_documents", [])) > 0:
            await self._create_followup_job(job.candidate_id)

        return result

    # Helper methods

    async def _get_job(self, job_id: int) -> Optional[JobTracker]:
        """Get job by ID."""
        from sqlalchemy import select
        result = await self.db.execute(
            select(JobTracker).where(JobTracker.job_id == job_id)
        )
        return result.scalar_one_or_none()

    async def _get_candidate(self, candidate_id: int) -> Optional[CandidateInfo]:
        """Get candidate by ID."""
        from sqlalchemy import select
        result = await self.db.execute(
            select(CandidateInfo).where(CandidateInfo.candidate_id == candidate_id)
        )
        return result.scalar_one_or_none()

    async def _find_candidate_by_email(self, email: str) -> Optional[CandidateInfo]:
        """Find candidate by email address."""
        from sqlalchemy import select
        result = await self.db.execute(
            select(CandidateInfo).where(CandidateInfo.personal_email_id == email)
        )
        return result.scalar_one_or_none()

    async def _update_job_status(
        self,
        job: JobTracker,
        status_id: int,
        remark: str = None
    ) -> None:
        """Update job status."""
        job.status_id = status_id
        job.updated_on = datetime.utcnow()
        if remark:
            job.remark = remark
        self.db.add(job)
        await self.db.commit()

    async def _create_followup_job(
        self,
        candidate_id: int,
        days_delay: int = 2
    ) -> JobTracker:
        """Create a follow-up job."""
        from datetime import timedelta
        from sqlalchemy import select

        # Get follow-up job type
        job_type_result = await self.db.execute(
            select(JobTypeMaster).where(JobTypeMaster.job_type == "followup_mail")
        )
        job_type = job_type_result.scalar_one_or_none()

        pending_status = await self._get_status_id("pending")

        job = JobTracker(
            candidate_id=candidate_id,
            job_type_id=job_type.job_type_id if job_type else JobType.FOLLOWUP_MAIL,
            status_id=pending_status,
            action_date=(datetime.utcnow() + timedelta(days=days_delay)).date(),
            human_action_required=True,
            start_time=datetime.utcnow()
        )

        self.db.add(job)
        await self.db.commit()
        return job

    async def _create_attachment_job(
        self,
        candidate_id: int,
        attachments: List[Dict]
    ) -> JobTracker:
        """Create an attachment saving job."""
        import json
        from sqlalchemy import select

        job_type_result = await self.db.execute(
            select(JobTypeMaster).where(JobTypeMaster.job_type == "save_attachment")
        )
        job_type = job_type_result.scalar_one_or_none()

        pending_status = await self._get_status_id("pending")

        job = JobTracker(
            candidate_id=candidate_id,
            job_type_id=job_type.job_type_id if job_type else JobType.SAVE_ATTACHMENT,
            status_id=pending_status,
            remark=json.dumps(attachments),
            start_time=datetime.utcnow()
        )

        self.db.add(job)
        await self.db.commit()
        return job

    async def _create_ocr_job(
        self,
        candidate_id: int,
        documents: List[Dict]
    ) -> JobTracker:
        """Create an OCR validation job."""
        import json
        from sqlalchemy import select

        job_type_result = await self.db.execute(
            select(JobTypeMaster).where(JobTypeMaster.job_type == "ocr_validation")
        )
        job_type = job_type_result.scalar_one_or_none()

        pending_status = await self._get_status_id("pending")

        job = JobTracker(
            candidate_id=candidate_id,
            job_type_id=job_type.job_type_id if job_type else JobType.OCR_VALIDATION,
            status_id=pending_status,
            remark=json.dumps(documents),
            start_time=datetime.utcnow()
        )

        self.db.add(job)
        await self.db.commit()
        return job

    async def _create_segregation_job(
        self,
        candidate_id: int,
        documents: List[Dict],
        validation_results: List[Dict]
    ) -> JobTracker:
        """Create a segregation job."""
        import json
        from sqlalchemy import select

        job_type_result = await self.db.execute(
            select(JobTypeMaster).where(JobTypeMaster.job_type == "segregation")
        )
        job_type = job_type_result.scalar_one_or_none()

        pending_status = await self._get_status_id("pending")

        job = JobTracker(
            candidate_id=candidate_id,
            job_type_id=job_type.job_type_id if job_type else JobType.SEGREGATION,
            status_id=pending_status,
            remark=json.dumps({
                "documents": documents,
                "validation_results": validation_results
            }),
            start_time=datetime.utcnow()
        )

        self.db.add(job)
        await self.db.commit()
        return job

    async def _create_gap_analysis_job(self, candidate_id: int) -> JobTracker:
        """Create a gap analysis job."""
        from sqlalchemy import select

        job_type_result = await self.db.execute(
            select(JobTypeMaster).where(JobTypeMaster.job_type == "gap_analysis")
        )
        job_type = job_type_result.scalar_one_or_none()

        pending_status = await self._get_status_id("pending")

        job = JobTracker(
            candidate_id=candidate_id,
            job_type_id=job_type.job_type_id if job_type else JobType.GAP_ANALYSIS,
            status_id=pending_status,
            start_time=datetime.utcnow()
        )

        self.db.add(job)
        await self.db.commit()
        return job

    async def _get_status_id(self, status_type: str) -> int:
        """Get status ID by type."""
        from sqlalchemy import select
        result = await self.db.execute(
            select(StatusMaster).where(StatusMaster.status_type == status_type)
        )
        status = result.scalar_one_or_none()
        return status.status_id if status else StatusType.PENDING


# For synchronous usage (e.g., in Airflow)
def run_job_sync(job_id: int, db_url: str = None):
    """Synchronous wrapper for running a job."""
    import asyncio
    from src.core.database import async_session_maker

    async def _run():
        async with async_session_maker() as session:
            agent = OnboardingAgent(session)
            return await agent.process_job(job_id)

    return asyncio.run(_run())