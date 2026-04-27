"""MCP Tool: Prepare draft emails for follow-ups."""
from datetime import datetime
from typing import Dict, Any, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from config.logging import logger
from src.models.database import (
    CandidateInfo, JobTracker, JobTypeMaster, MailTypeMaster,
    StatusMaster, DocumentTracker, DocumentTypeMaster
)
from src.constants.constants import StatusType, JobType, MailType
from src.services.llm_service import LLMService


class DraftPrepareTool:
    """Tool for generating email drafts for candidates."""

    def __init__(self, db: AsyncSession, llm_service: LLMService = None):
        self.db = db
        self.llm_service = llm_service or LLMService()
        self.name = "draft_prepare"
        self.description = "Generate follow-up email drafts for candidates"

    async def execute(
        self,
        job_id: int,
        mail_type: str = "followup_reminder"
    ) -> Dict[str, Any]:
        """
        Generate a draft email for a job.

        Args:
            job_id: Job tracker ID
            mail_type: Type of email to generate

        Returns:
            Draft email with subject and body
        """
        # Get job and candidate info
        job = await self._get_job(job_id)
        if not job:
            return {
                "error": f"Job not found: {job_id}",
                "job_id": job_id
            }

        candidate = await self._get_candidate(job.candidate_id)
        if not candidate:
            return {
                "error": f"Candidate not found for job: {job_id}",
                "job_id": job_id
            }

        # Get missing documents
        missing_docs = await self._get_missing_documents(candidate.candidate_id)

        # Get previous communications count
        days_since_last_contact = await self._get_days_since_last_contact(job.candidate_id)

        # Get mail template
        template = await self._get_mail_template(mail_type)

        # Generate draft using LLM
        draft = await self._generate_draft(
            candidate=candidate,
            missing_docs=missing_docs,
            days_since_last_contact=days_since_last_contact,
            template=template
        )

        # Save draft to job tracker
        job.draft_mail = draft["body"]
        await self.db.commit()

        result = {
            "job_id": job_id,
            "candidate_id": candidate.candidate_id,
            "candidate_name": candidate.candidate_name,
            "candidate_email": candidate.personal_email_id,
            "subject": draft["subject"],
            "body": draft["body"],
            "missing_documents": missing_docs,
            "days_since_last_contact": days_since_last_contact,
            "mail_type": mail_type,
            "generated_at": datetime.utcnow().isoformat()
        }

        logger.info(f"Generated draft for job {job_id}: {mail_type}")
        return result

    async def _get_job(self, job_id: int) -> Optional[JobTracker]:
        """Get job by ID."""
        result = await self.db.execute(
            select(JobTracker).where(JobTracker.job_id == job_id)
        )
        return result.scalar_one_or_none()

    async def _get_candidate(self, candidate_id: int) -> Optional[CandidateInfo]:
        """Get candidate by ID."""
        result = await self.db.execute(
            select(CandidateInfo).where(CandidateInfo.candidate_id == candidate_id)
        )
        return result.scalar_one_or_none()

    async def _get_missing_documents(
        self,
        candidate_id: int
    ) -> List[str]:
        """Get list of missing documents for candidate."""
        # Get pending document tracker entries
        pending_status = await self._get_status_id("pending")

        result = await self.db.execute(
            select(DocumentTracker)
            .join(DocumentTypeMaster)
            .where(
                DocumentTracker.candidate_id == candidate_id,
                DocumentTracker.status_id == pending_status,
                DocumentTracker.is_active == True
            )
            .options(selectinload(DocumentTracker.document_type))
        )
        pending_docs = result.scalars().all()

        return [
            doc.document_type.document_name
            for doc in pending_docs
            if doc.document_type
        ]

    async def _get_days_since_last_contact(
        self,
        candidate_id: int
    ) -> int:
        """Calculate days since last email contact."""
        result = await self.db.execute(
            select(JobTracker)
            .where(JobTracker.candidate_id == candidate_id)
            .order_by(JobTracker.updated_on.desc())
            .limit(1)
        )
        last_job = result.scalar_one_or_none()

        if last_job and last_job.updated_on:
            delta = datetime.utcnow() - last_job.updated_on
            return delta.days

        return 0

    async def _get_mail_template(
        self,
        mail_type: str
    ) -> Optional[MailTypeMaster]:
        """Get mail template by type."""
        result = await self.db.execute(
            select(MailTypeMaster).where(
                MailTypeMaster.mail_type == mail_type,
                MailTypeMaster.is_active == True
            )
        )
        return result.scalar_one_or_none()

    async def _generate_draft(
        self,
        candidate: CandidateInfo,
        missing_docs: List[str],
        days_since_last_contact: int,
        template: Optional[MailTypeMaster]
    ) -> Dict[str, str]:
        """Generate email draft using LLM or database templates."""
        candidate_name = candidate.candidate_name or "Candidate"
        candidate_email = candidate.personal_email_id or ""

        # If we have a database template, use it
        if template and template.mail_template:
            return await self._generate_from_template(
                template, candidate, missing_docs, days_since_last_contact
            )

        # Otherwise, use LLM to generate draft
        llm_draft = await self.llm_service.generate_followup_email(
            candidate_name=candidate_name,
            missing_documents=missing_docs,
            days_since_last_contact=days_since_last_contact,
            previous_communications=template.mail_template if template else None
        )

        # Structure the draft
        subject = self._generate_subject(mail_type="followup", missing_docs=missing_docs)
        body = self._format_body(llm_draft, candidate_name)

        return {
            "subject": subject,
            "body": body
        }

    async def _generate_from_template(
        self,
        template: MailTypeMaster,
        candidate: CandidateInfo,
        missing_docs: List[str],
        days_since_last_contact: int
    ) -> Dict[str, str]:
        """Generate email from database template."""
        candidate_name = candidate.candidate_name or "Candidate"
        candidate_email = candidate.personal_email_id or ""

        # Format the document list
        document_list = self._format_document_list(missing_docs)

        # Replace placeholders in template
        body_template = template.mail_template or ""
        body = body_template.format(
            candidate_name=candidate_name,
            candidate_email=candidate_email,
            document_list=document_list,
            missing_documents=document_list,
            days_since_last_contact=days_since_last_contact
        )

        # Generate subject based on template type
        subject = self._generate_subject(template.mail_type, missing_docs)

        return {
            "subject": subject,
            "body": body
        }

    def _generate_subject(
        self,
        mail_type: str,
        missing_docs: List[str]
    ) -> str:
        """Generate email subject line."""
        if mail_type == "initial_request":
            return "Document Submission Required - HR Onboarding"

        elif mail_type == "followup_reminder":
            if len(missing_docs) == 1:
                return f"Reminder: {missing_docs[0]} Submission Required"
            else:
                return f"Reminder: {len(missing_docs)} Documents Pending Submission"

        elif mail_type == "gap_notification":
            return "Document Verification - Action Required"

        else:
            return "HR Onboarding - Document Submission"

    def _format_body(
        self,
        content: str,
        candidate_name: str
    ) -> str:
        """Format email body with greeting and signature."""
        # Add greeting if not present
        if not content.lower().startswith("dear"):
            content = f"Dear {candidate_name},\n\n{content}"

        # Add signature if not present
        signature = """
Best regards,
HR Team
[Company Name]
        """.strip()

        if "regards" not in content.lower():
            content = f"{content}\n\n{signature}"

        return content

    async def generate_initial_email(
        self,
        candidate: CandidateInfo,
        required_docs: List[str]
    ) -> Dict[str, str]:
        """Generate initial document request email."""
        candidate_name = candidate.candidate_name or "Candidate"

        # Try to get template from database
        template = await self._get_mail_template("initial_request")

        if template and template.mail_template:
            # Format the document list
            document_list = self._format_document_list(required_docs)

            # Replace placeholders in template
            body = template.mail_template.format(
                candidate_name=candidate_name,
                document_list=document_list,
                missing_documents=document_list
            )

            subject = "Document Submission Required - HR Onboarding"
            return {
                "subject": subject,
                "body": body
            }

        # Fallback to hardcoded template
        body = f"""Dear {candidate_name},

Welcome to [Company Name]! We're excited to have you join our team.

As part of the onboarding process, we require the following documents:

{self._format_document_list(required_docs)}

Please submit these documents at your earliest convenience by replying to this email with attachments.

If you have any questions, feel free to reach out.

Best regards,
HR Team
[Company Name]
        """.strip()

        subject = "Document Submission Required - HR Onboarding"

        return {
            "subject": subject,
            "body": body
        }

    def _format_document_list(
        self,
        documents: List[str]
    ) -> str:
        """Format document list for email."""
        return "\n".join([f"• {doc}" for doc in documents])

    async def _get_status_id(self, status_type: str) -> int:
        """Get status ID by type."""
        result = await self.db.execute(
            select(StatusMaster).where(StatusMaster.status_type == status_type)
        )
        status = result.scalar_one_or_none()
        return status.status_id if status else StatusType.PENDING

    def get_tool_schema(self) -> Dict[str, Any]:
        """Return the tool schema for MCP."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "integer",
                        "description": "Job tracker ID"
                    },
                    "mail_type": {
                        "type": "string",
                        "description": "Type of email (initial_request, followup_reminder, gap_notification)",
                        "enum": ["initial_request", "followup_reminder", "gap_notification"]
                    }
                },
                "required": ["job_id"]
            }
        }