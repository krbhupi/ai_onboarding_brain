"""Email controller endpoints."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.core.database import get_db
from src.models.database import JobTracker, CandidateInfo
from src.schemas.schemas import (
    EmailDraftRequest, EmailDraftResponse,
    EmailSendRequest, EmailSendResponse,
    EmailInboxResponse, BaseResponse
)
from src.services.email_service import EmailService
from src.services.document_service import DocumentService
from src.services.outlook_graph import OutlookGraphService
from src.controller.auth import get_graph_service
from src.mcp_tools.draft_prepare import DraftPrepareTool
from config.settings import get_settings

router = APIRouter()
settings = get_settings()


def get_email_service():
    """Get appropriate email service based on configuration."""
    if settings.USE_OAUTH2:
        return get_graph_service()
    return EmailService()


@router.post("/draft", response_model=EmailDraftResponse)
async def generate_email_draft(
    request: EmailDraftRequest,
    db: AsyncSession = Depends(get_db)
):
    """Generate an email draft for a job."""
    # Get job
    job_result = await db.execute(
        select(JobTracker).where(JobTracker.job_id == request.job_id)
    )
    job = job_result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Generate draft
    draft_tool = DraftPrepareTool(db)
    result = await draft_tool.execute(
        job_id=request.job_id,
        mail_type=request.mail_type
    )

    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])

    return EmailDraftResponse(
        status="success",
        job_id=result["job_id"],
        candidate_id=result["candidate_id"],
        candidate_name=result["candidate_name"],
        candidate_email=result["candidate_email"],
        subject=result["subject"],
        body=result["body"],
        missing_documents=result["missing_documents"]
    )


@router.post("/send", response_model=EmailSendResponse)
async def send_email(
    request: EmailSendRequest,
    db: AsyncSession = Depends(get_db)
):
    """Send an email."""
    from pathlib import Path

    # Get job
    job_result = await db.execute(
        select(JobTracker).where(JobTracker.job_id == request.job_id)
    )
    job = job_result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Get candidate
    candidate_result = await db.execute(
        select(CandidateInfo).where(CandidateInfo.candidate_id == job.candidate_id)
    )
    candidate = candidate_result.scalar_one_or_none()

    # Send email
    email_service = EmailService()

    # Process attachments
    attachment_paths = []
    if request.attachments:
        for path in request.attachments:
            if Path(path).exists():
                attachment_paths.append(Path(path))

    sent = await email_service.send_email(
        to_address=request.to_address,
        subject=request.subject,
        body=request.body,
        attachments=attachment_paths if attachment_paths else None
    )

    if not sent:
        raise HTTPException(status_code=500, detail="Failed to send email")

    # Update job status
    from datetime import datetime
    from src.constants.constants import StatusType

    job.status_id = StatusType.COMPLETE
    job.end_time = datetime.utcnow()
    job.updated_on = datetime.utcnow()
    await db.commit()

    return EmailSendResponse(
        status="success",
        message="Email sent successfully",
        sent_at=datetime.utcnow()
    )


@router.get("/inbox", response_model=EmailInboxResponse)
async def read_inbox(
    unread_only: bool = Query(True),
    limit: int = Query(50, ge=1, le=200)
):
    """Read emails from inbox."""
    email_service = EmailService()
    emails = await email_service.read_inbox(
        unread_only=unread_only,
        limit=limit
    )

    return EmailInboxResponse(
        status="success",
        emails=emails,
        total=len(emails)
    )


@router.post("/process-replies")
async def process_email_replies(
    db: AsyncSession = Depends(get_db)
):
    """Process candidate email replies from inbox."""
    from datetime import datetime
    from src.mcp_tools.followup_classification import FollowupClassificationTool
    from src.models.database import StatusMaster
    from src.constants.constants import StatusType, JobType

    email_service = EmailService()
    classification_tool = FollowupClassificationTool()

    # Read inbox
    emails = await email_service.read_inbox(unread_only=True)

    processed = []
    for email_data in emails:
        try:
            # Classify email
            classification = await classification_tool.execute(
                email_body=email_data.get("body", ""),
                email_subject=email_data.get("subject", "")
            )

            # Find candidate by email
            from_address = email_data.get("from_address", "")

            # Extract email address from "Name <email>" format
            import re
            email_match = re.search(r'[\w\.-]+@[\w\.-]+', from_address)
            sender_email = email_match.group(0) if email_match else from_address

            candidate_result = await db.execute(
                select(CandidateInfo).where(
                    CandidateInfo.personal_email_id == sender_email
                )
            )
            candidate = candidate_result.scalar_one_or_none()

            result = {
                "from": from_address,
                "subject": email_data.get("subject"),
                "category": classification.get("category"),
                "next_action_date": classification.get("next_action_date"),
                "documents_mentioned": classification.get("documents_mentioned", [])
            }

            if candidate:
                result["candidate_id"] = candidate.candidate_id
                result["candidate_name"] = candidate.candidate_name

                # Create job for processing
                pending_status = await db.execute(
                    select(StatusMaster).where(StatusMaster.status_type == "pending")
                )
                pending = pending_status.scalar_one_or_none()

                # Create save_attachment job if attachments present
                if email_data.get("attachments"):
                    from src.mcp_tools.followup_classification import HumanAction
                    job = JobTracker(
                        candidate_id=candidate.candidate_id,
                        job_type_id=JobType.SAVE_ATTACHMENT,
                        status_id=pending.status_id if pending else StatusType.PENDING,
                        human_action_required=False,
                        start_time=datetime.utcnow()
                    )
                    db.add(job)
                    await db.commit()

            processed.append(result)

        except Exception as e:
            processed.append({
                "from": email_data.get("from_address"),
                "error": str(e)
            })

    return {
        "status": "success",
        "processed_count": len(processed),
        "results": processed
    }


@router.post("/{job_id}/approve-draft")
async def approve_draft(
    job_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Approve a draft email for sending."""
    from datetime import datetime

    job_result = await db.execute(
        select(JobTracker).where(JobTracker.job_id == job_id)
    )
    job = job_result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.draft_mail:
        raise HTTPException(status_code=400, detail="No draft email found")

    # Get candidate
    candidate_result = await db.execute(
        select(CandidateInfo).where(CandidateInfo.candidate_id == job.candidate_id)
    )
    candidate = candidate_result.scalar_one_or_none()

    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # Send email
    email_service = EmailService()
    sent = await email_service.send_email(
        to_address=candidate.personal_email_id,
        subject="HR Onboarding - Document Submission",
        body=job.draft_mail
    )

    if not sent:
        raise HTTPException(status_code=500, detail="Failed to send email")

    # Update job
    job.human_action = "accept"
    job.end_time = datetime.utcnow()
    job.updated_on = datetime.utcnow()

    await db.commit()

    return {
        "status": "success",
        "message": "Email sent successfully",
        "job_id": job_id,
        "sent_to": candidate.personal_email_id
    }


@router.post("/{job_id}/modify-draft")
async def modify_draft(
    job_id: int,
    new_body: str,
    db: AsyncSession = Depends(get_db)
):
    """Modify a draft email."""
    from datetime import datetime

    job_result = await db.execute(
        select(JobTracker).where(JobTracker.job_id == job_id)
    )
    job = job_result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job.draft_mail = new_body
    job.updated_on = datetime.utcnow()

    await db.commit()

    return {
        "status": "success",
        "message": "Draft updated",
        "job_id": job_id
    }