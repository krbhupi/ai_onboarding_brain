#!/usr/bin/env python
"""Sample workflow demonstrating the complete HR onboarding automation."""
import asyncio
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from src.core.database import get_db, init_db
from src.models.database import (
    CandidateInfo, DocumentTracker, JobTracker,
    DocumentTypeMaster, StatusMaster, JobTypeMaster,
    MailTypeMaster, CandidateTypeMaster
)
from src.mcp_tools.gap_analysis import GapAnalysisTool
from src.mcp_tools.draft_prepare import DraftPrepareTool
from src.services.llm_service import LLMService


async def create_seed_data(db):
    """Create seed data for document types, statuses, etc."""
    from src.constants.constants import (
        StatusType, JobType, MailType, CandidateType
    )

    # Create status master entries
    statuses = [
        StatusMaster(status_id=StatusType.PENDING, status_type="pending", status_description="Pending action"),
        StatusMaster(status_id=StatusType.IN_PROGRESS, status_type="in_progress", status_description="In progress"),
        StatusMaster(status_id=StatusType.COMPLETE, status_type="complete", status_description="Complete"),
        StatusMaster(status_id=StatusType.FAILED, status_type="failed", status_description="Failed"),
    ]
    for s in statuses:
        db.add(s)

    # Create job type master entries
    job_types = [
        JobTypeMaster(job_type_id=JobType.DOCUMENTS_REQUIRED, job_type="documents_required", job_description="Request documents"),
        JobTypeMaster(job_type_id=JobType.MAIL_SEND, job_type="mail_send", job_description="Send email"),
        JobTypeMaster(job_type_id=JobType.FOLLOWUP_MAIL, job_type="followup_mail", job_description="Send follow-up email"),
        JobTypeMaster(job_type_id=JobType.READ_INBOX, job_type="read_inbox", job_description="Read email inbox"),
        JobTypeMaster(job_type_id=JobType.SAVE_ATTACHMENT, job_type="save_attachment", job_description="Save email attachment"),
        JobTypeMaster(job_type_id=JobType.OCR_VALIDATION, job_type="ocr_validation", job_description="OCR validate document"),
        JobTypeMaster(job_type_id=JobType.SEGREGATION, job_type="segregation", job_description="Segregate documents"),
        JobTypeMaster(job_type_id=JobType.GAP_ANALYSIS, job_type="gap_analysis", job_description="Analyze document gaps"),
    ]
    for jt in job_types:
        db.add(jt)

    # Create mail type master entries
    mail_types = [
        MailTypeMaster(mail_type_id=MailType.INITIAL_REQUEST, mail_type="initial_request", mail_description="Initial document request"),
        MailTypeMaster(mail_type_id=MailType.FOLLOWUP_REMINDER, mail_type="followup_reminder", mail_description="Follow-up reminder"),
        MailTypeMaster(mail_type_id=MailType.DOCUMENT_RECEIVED, mail_type="document_received", mail_description="Document received confirmation"),
        MailTypeMaster(mail_type_id=MailType.GAP_NOTIFICATION, mail_type="gap_notification", mail_description="Gap notification email"),
    ]
    for mt in mail_types:
        db.add(mt)

    # Create candidate type master entries
    candidate_types = [
        CandidateTypeMaster(candidate_type_id=CandidateType.FRESHER, candidate_type="Fresher", candidate_type_description="Fresh graduate"),
        CandidateTypeMaster(candidate_type_id=CandidateType.EXPERIENCE, candidate_type="Experience", candidate_type_description="Experienced hire"),
        CandidateTypeMaster(candidate_type_id=CandidateType.DEV_PARTNER, candidate_type="Dev Partner", candidate_type_description="Development partner"),
    ]
    for ct in candidate_types:
        db.add(ct)

    # Create document type master entries (matching DOCUMENT_TYPE_MAPPING)
    doc_types = [
        # Common documents for all types
        DocumentTypeMaster(document_name="Aadhaar Card", fresher=True, experience=True, dev_partner=True),
        DocumentTypeMaster(document_name="PAN Card", fresher=True, experience=True, dev_partner=True),
        DocumentTypeMaster(document_name="Passport Photo", fresher=True, experience=True, dev_partner=True),
        DocumentTypeMaster(document_name="Bank Passbook/Cancelled Cheque", fresher=True, experience=True, dev_partner=True),

        # Education documents (fresher + experience)
        DocumentTypeMaster(document_name="10th Marksheet", fresher=True, experience=True, dev_partner=False),
        DocumentTypeMaster(document_name="12th Marksheet", fresher=True, experience=True, dev_partner=False),
        DocumentTypeMaster(document_name="Degree Certificate", fresher=True, experience=True, dev_partner=False),

        # Employment documents (experience only)
        DocumentTypeMaster(document_name="Relieving Letter", fresher=False, experience=True, dev_partner=False),
        DocumentTypeMaster(document_name="Experience Certificate", fresher=False, experience=True, dev_partner=False),
        DocumentTypeMaster(document_name="Salary Slip (Last 3 months)", fresher=False, experience=True, dev_partner=False),
        DocumentTypeMaster(document_name="Form 16", fresher=False, experience=True, dev_partner=False),

        # Dev Partner specific
        DocumentTypeMaster(document_name="Partner Agreement", fresher=False, experience=False, dev_partner=True),
    ]
    for dt in doc_types:
        db.add(dt)

    await db.commit()
    print("✓ Seed data created")


async def create_sample_candidate(db):
    """Create a sample candidate."""
    import hashlib
    from src.constants.constants import CandidateType

    # Check if candidate already exists
    result = await db.execute(
        select(CandidateInfo).where(CandidateInfo.candidate_name == "John Doe")
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    # Create row hash
    row_data = f"John Doe|john.doe@email.com|Software Engineer|TCS"
    row_hash = hashlib.md5(row_data.encode()).hexdigest()

    candidate = CandidateInfo(
        cin="CIN-2026-001",  # Required field
        candidate_name="John Doe",
        personal_email_id="john.doe@email.com",
        contact_number="9876543210",
        designation_to_be_printed_on_the_offer_letter="Software Engineer",
        candidate_type_id=CandidateType.EXPERIENCE,
        current_status="Offer Accepted",
        row_hash=row_hash
    )
    db.add(candidate)
    await db.commit()
    await db.refresh(candidate)
    print(f"✓ Created candidate: {candidate.candidate_name} (ID: {candidate.candidate_id})")
    return candidate


async def create_document_tracker_entries(db, candidate):
    """Create document tracking entries for the candidate."""
    from src.constants.constants import StatusType

    # Get all document types
    result = await db.execute(select(DocumentTypeMaster))
    doc_types = result.scalars().all()

    # For experienced candidate, use experience=True docs
    relevant_docs = [dt for dt in doc_types if dt.experience]

    created_count = 0
    for doc_type in relevant_docs:
        # Check if already exists
        existing = await db.execute(
            select(DocumentTracker).where(
                DocumentTracker.candidate_id == candidate.candidate_id,
                DocumentTracker.document_type_id == doc_type.document_type_id
            )
        )
        if existing.scalar_one_or_none():
            continue

        tracker = DocumentTracker(
            candidate_id=candidate.candidate_id,
            document_type_id=doc_type.document_type_id,
            status_id=StatusType.PENDING
        )
        db.add(tracker)
        created_count += 1

    await db.commit()
    print(f"✓ Created document tracking entries for {created_count} documents")


async def simulate_document_uploads(db, candidate):
    """Simulate some documents being uploaded."""
    from src.constants.constants import StatusType

    # Get document types to find IDs
    result = await db.execute(select(DocumentTypeMaster))
    doc_types = {dt.document_name: dt.document_type_id for dt in result.scalars().all()}

    # Simulate some documents received (matching actual document names)
    received_docs = [
        "Aadhaar Card",
        "PAN Card",
        "Passport Photo",
        "10th Marksheet",
        "Degree Certificate",
        "Relieving Letter",
    ]

    updated_count = 0
    for doc_name in received_docs:
        doc_type_id = doc_types.get(doc_name)
        if not doc_type_id:
            continue

        result = await db.execute(
            select(DocumentTracker).where(
                DocumentTracker.candidate_id == candidate.candidate_id,
                DocumentTracker.document_type_id == doc_type_id
            )
        )
        tracker = result.scalar_one_or_none()
        if tracker:
            tracker.status_id = StatusType.COMPLETE
            tracker.document_store_id = 1  # Simulated storage reference
            tracker.document_received_on = datetime.utcnow().date()
            updated_count += 1

    await db.commit()
    print(f"✓ Simulated {updated_count} documents received")


async def run_gap_analysis(db, candidate):
    """Run gap analysis to find missing documents."""
    tool = GapAnalysisTool(db)
    result = await tool.execute(candidate_id=candidate.candidate_id)

    print("\n" + "="*60)
    print("GAP ANALYSIS REPORT")
    print("="*60)
    print(f"Candidate: {result.get('candidate_name')}")
    print(f"Total Documents: {result.get('total_documents')}")
    print(f"Received: {result.get('received_documents')}")
    print(f"Missing: {result.get('missing_documents')}")
    print(f"Completion: {result.get('completion_percentage')}%")

    if result.get('missing_document_list'):
        print("\nMissing Documents:")
        for doc in result['missing_document_list']:
            print(f"  - {doc}")

    return result


async def generate_followup_email(db, candidate, missing_docs):
    """Generate follow-up email for missing documents."""
    tool = DraftPrepareTool(db)
    result = await tool.execute(
        job_id=None,  # Will be created internally
        mail_type="followup"
    )

    # Override with candidate info
    if result.get("error"):
        # Create a job first
        from src.constants.constants import JobType, StatusType

        job = JobTracker(
            candidate_id=candidate.candidate_id,
            job_type_id=JobType.FOLLOWUP_MAIL,
            status_id=StatusType.PENDING,
            start_time=datetime.utcnow()
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)

        result = await tool.execute(job_id=job.job_id, mail_type="followup")

    print("\n" + "="*60)
    print("FOLLOW-UP EMAIL DRAFT")
    print("="*60)
    print(f"To: {candidate.personal_email_id}")
    print(f"Subject: {result.get('subject', 'Document Submission Reminder')}")
    print(f"\nBody:\n{result.get('body', 'N/A')}")
    print(f"\nMissing Documents: {result.get('missing_documents', [])}")

    return result


async def test_llm_document_validation():
    """Test LLM document validation."""
    llm = LLMService()

    print("\n" + "="*60)
    print("LLM DOCUMENT VALIDATION TEST")
    print("="*60)

    # Test validating a document
    result = await llm.validate_document(
        document_text="This is a PAN Card with number ABCDE1234F issued to John Doe",
        document_type="PAN Card"
    )
    print(f"Document Type: PAN Card")
    print(f"Is Valid: {result.get('is_valid')}")
    print(f"Confidence: {result.get('confidence')}")
    print(f"Extracted Info: {result.get('extracted_info', {})}")


async def main():
    """Run the complete workflow."""
    print("\n" + "="*60)
    print("HR ONBOARDING AUTOMATION - SAMPLE WORKFLOW")
    print("="*60)

    # Initialize database
    await init_db()

    async for db in get_db():
        # Step 1: Create seed data
        print("\n[Step 1] Creating seed data...")
        await create_seed_data(db)

        # Step 2: Create sample candidate
        print("\n[Step 2] Creating sample candidate...")
        candidate = await create_sample_candidate(db)

        # Step 3: Create document tracking entries
        print("\n[Step 3] Creating document tracker entries...")
        await create_document_tracker_entries(db, candidate)

        # Step 4: Simulate document uploads
        print("\n[Step 4] Simulating document uploads...")
        await simulate_document_uploads(db, candidate)

        # Step 5: Run gap analysis
        print("\n[Step 5] Running gap analysis...")
        gap_result = await run_gap_analysis(db, candidate)

        # Step 6: Generate follow-up email
        print("\n[Step 6] Generating follow-up email...")
        await generate_followup_email(db, candidate, gap_result.get('missing_document_list', []))

        # Step 7: Test LLM validation
        print("\n[Step 7] Testing LLM document validation...")
        await test_llm_document_validation()

        print("\n" + "="*60)
        print("WORKFLOW COMPLETED SUCCESSFULLY!")
        print("="*60)
        print("\nNext Steps for User:")
        print("1. Register app in Azure Portal for OAuth2 (see /auth/outlook)")
        print("2. Visit http://localhost:8000/auth/outlook to authorize Outlook")
        print("3. Use API endpoints to manage candidates and documents")
        print("4. Monitor jobs at /api/jobs endpoint")

        break


if __name__ == "__main__":
    asyncio.run(main())