#!/usr/bin/env python
"""End-to-end HR Automation workflow test."""
import asyncio
import sys
import hashlib
from datetime import datetime, date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from src.core.database import get_db, init_db
from src.models.database import (
    CandidateInfo, DocumentTracker, JobTracker,
    DocumentTypeMaster, StatusMaster, JobTypeMaster,
    MailTypeMaster, CandidateTypeMaster
)
from src.constants.constants import StatusType, JobType, MailType, CandidateType
from src.mcp_tools.gap_analysis import GapAnalysisTool
from src.mcp_tools.draft_prepare import DraftPrepareTool
from src.services.email_service import EmailService
from config.logging import logger


async def run_end_to_end():
    """Run complete end-to-end workflow."""
    print("\n" + "="*70)
    print("HR AUTOMATION - END-TO-END WORKFLOW")
    print("="*70)
    print(f"Candidate Email: kr_bhupi@outlook.com")
    print(f"Joining Date: 20-April-2026")
    print("="*70)

    # Initialize database
    await init_db()

    async for db in get_db():
        # ============================================================
        # STEP 1: SETUP - Create seed data
        # ============================================================
        print("\n[STEP 1] Setting up database...")

        # Check if seed data exists
        result = await db.execute(select(StatusMaster).limit(1))
        if not result.scalar_one_or_none():
            statuses = [
                StatusMaster(status_id=StatusType.PENDING, status_type="pending", status_description="Pending action"),
                StatusMaster(status_id=StatusType.IN_PROGRESS, status_type="in_progress", status_description="In progress"),
                StatusMaster(status_id=StatusType.COMPLETE, status_type="complete", status_description="Complete"),
                StatusMaster(status_id=StatusType.FAILED, status_type="failed", status_description="Failed"),
            ]
            for s in statuses:
                db.add(s)

            job_types = [
                JobTypeMaster(job_type_id=JobType.DOCUMENTS_REQUIRED, job_type="documents_required", job_description="Request documents"),
                JobTypeMaster(job_type_id=JobType.FOLLOWUP_MAIL, job_type="followup_mail", job_description="Send follow-up email"),
            ]
            for jt in job_types:
                db.add(jt)

            mail_types = [
                MailTypeMaster(mail_type_id=MailType.INITIAL_REQUEST, mail_type="initial_request", mail_description="Initial document request"),
                MailTypeMaster(mail_type_id=MailType.FOLLOWUP_REMINDER, mail_type="followup_reminder", mail_description="Follow-up reminder"),
            ]
            for mt in mail_types:
                db.add(mt)

            candidate_types = [
                CandidateTypeMaster(candidate_type_id=CandidateType.FRESHER, candidate_type="Fresher", candidate_type_description="Fresh graduate"),
                CandidateTypeMaster(candidate_type_id=CandidateType.EXPERIENCE, candidate_type="Experience", candidate_type_description="Experienced hire"),
            ]
            for ct in candidate_types:
                db.add(ct)

            doc_types = [
                DocumentTypeMaster(document_name="Aadhaar Card", fresher=True, experience=True, dev_partner=True),
                DocumentTypeMaster(document_name="PAN Card", fresher=True, experience=True, dev_partner=True),
                DocumentTypeMaster(document_name="Passport Photo", fresher=True, experience=True, dev_partner=True),
                DocumentTypeMaster(document_name="Bank Passbook/Cancelled Cheque", fresher=True, experience=True, dev_partner=True),
                DocumentTypeMaster(document_name="10th Marksheet", fresher=True, experience=True, dev_partner=False),
                DocumentTypeMaster(document_name="12th Marksheet", fresher=True, experience=True, dev_partner=False),
                DocumentTypeMaster(document_name="Degree Certificate", fresher=True, experience=True, dev_partner=False),
                DocumentTypeMaster(document_name="Relieving Letter", fresher=False, experience=True, dev_partner=False),
                DocumentTypeMaster(document_name="Experience Certificate", fresher=False, experience=True, dev_partner=False),
                DocumentTypeMaster(document_name="Salary Slip (Last 3 months)", fresher=False, experience=True, dev_partner=False),
                DocumentTypeMaster(document_name="Form 16", fresher=False, experience=True, dev_partner=False),
            ]
            for dt in doc_types:
                db.add(dt)

            await db.commit()
            print("✓ Seed data created")
        else:
            print("✓ Seed data already exists")

        # ============================================================
        # STEP 2: CREATE CANDIDATE
        # ============================================================
        print("\n[STEP 2] Creating candidate...")

        # Check if candidate exists
        result = await db.execute(
            select(CandidateInfo).where(CandidateInfo.personal_email_id == "kr_bhupi@outlook.com")
        )
        candidate = result.scalar_one_or_none()

        if candidate:
            print(f"✓ Candidate exists: {candidate.candidate_name} (ID: {candidate.candidate_id})")
        else:
            row_hash = hashlib.md5(f"KR|kr_bhupi@outlook.com|Software Engineer|TCS".encode()).hexdigest()
            candidate = CandidateInfo(
                cin=f"CIN-2026-NEW",
                candidate_name="KR",
                personal_email_id="kr_bhupi@outlook.com",
                contact_number="9876543210",
                designation_to_be_printed_on_the_offer_letter="Software Engineer",
                candidate_type_id=CandidateType.EXPERIENCE,
                current_status="Offer Accepted",
                month_of_joining="April-2026",
                expected_doj_wrt_to_np="20-April-2026",
                row_hash=row_hash
            )
            db.add(candidate)
            await db.commit()
            await db.refresh(candidate)
            print(f"✓ Created candidate: {candidate.candidate_name} (ID: {candidate.candidate_id})")

        # ============================================================
        # STEP 3: CREATE DOCUMENT TRACKERS
        # ============================================================
        print("\n[STEP 3] Setting up document tracking...")

        result = await db.execute(select(DocumentTypeMaster))
        all_doc_types = result.scalars().all()
        experienced_docs = [dt for dt in all_doc_types if dt.experience]

        # Check existing trackers
        result = await db.execute(
            select(DocumentTracker).where(DocumentTracker.candidate_id == candidate.candidate_id)
        )
        existing_trackers = result.scalars().all()

        if not existing_trackers:
            for doc_type in experienced_docs:
                tracker = DocumentTracker(
                    candidate_id=candidate.candidate_id,
                    document_type_id=doc_type.document_type_id,
                    status_id=StatusType.PENDING
                )
                db.add(tracker)
            await db.commit()
            print(f"✓ Created {len(experienced_docs)} document trackers")
        else:
            print(f"✓ {len(existing_trackers)} document trackers exist")

        # ============================================================
        # STEP 4: SIMULATE DOCUMENT RECEIPT
        # ============================================================
        print("\n[STEP 4] Simulating document receipts...")

        # Simulate some documents received
        received_docs = ["Aadhaar Card", "PAN Card", "Passport Photo", "Degree Certificate"]
        doc_map = {dt.document_name: dt.document_type_id for dt in all_doc_types}

        updated_count = 0
        for doc_name in received_docs:
            doc_type_id = doc_map.get(doc_name)
            if doc_type_id:
                result = await db.execute(
                    select(DocumentTracker).where(
                        DocumentTracker.candidate_id == candidate.candidate_id,
                        DocumentTracker.document_type_id == doc_type_id
                    )
                )
                tracker = result.scalar_one_or_none()
                if tracker and tracker.status_id != StatusType.COMPLETE:
                    tracker.status_id = StatusType.COMPLETE
                    tracker.document_received_on = datetime.utcnow().date()
                    updated_count += 1

        await db.commit()
        print(f"✓ Marked {updated_count} documents as received: {', '.join(received_docs)}")

        # ============================================================
        # STEP 5: RUN GAP ANALYSIS
        # ============================================================
        print("\n[STEP 5] Running gap analysis...")

        gap_tool = GapAnalysisTool(db)
        gap_result = await gap_tool.execute(candidate_id=candidate.candidate_id)

        print("\n" + "-"*50)
        print("GAP ANALYSIS REPORT")
        print("-"*50)
        print(f"Candidate: {gap_result.get('candidate_name', candidate.candidate_name)}")
        print(f"Total Documents: {gap_result.get('total_documents', 'N/A')}")
        print(f"Received: {gap_result.get('received_documents', 'N/A')}")
        print(f"Missing: {gap_result.get('missing_documents', 'N/A')}")
        print(f"Completion: {gap_result.get('completion_percentage', 0):.1f}%")

        missing_docs = gap_result.get('missing_document_list', [])
        if missing_docs:
            print("\nMissing Documents:")
            for doc in missing_docs:
                print(f"  - {doc}")

        # ============================================================
        # STEP 6: GENERATE FOLLOW-UP EMAIL
        # ============================================================
        print("\n[STEP 6] Generating follow-up email draft...")

        # Create a job for follow-up
        job = JobTracker(
            candidate_id=candidate.candidate_id,
            job_type_id=JobType.FOLLOWUP_MAIL,
            status_id=StatusType.PENDING,
            start_time=datetime.utcnow()
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)

        draft_tool = DraftPrepareTool(db)
        draft_result = await draft_tool.execute(job_id=job.job_id, mail_type="followup")

        print("\n" + "-"*50)
        print("EMAIL DRAFT")
        print("-"*50)
        print(f"To: {candidate.personal_email_id}")
        print(f"Subject: {draft_result.get('subject', 'Document Submission Reminder')}")
        print(f"\nBody:\n{draft_result.get('body', 'No body generated')}")

        # Update job with draft
        job.draft_mail = draft_result.get('body', '')
        await db.commit()

        # ============================================================
        # STEP 7: SEND EMAIL
        # ============================================================
        print("\n[STEP 7] Sending email via Gmail SMTP...")

        email_service = EmailService()

        email_sent = await email_service.send_email(
            to_address=candidate.personal_email_id,
            subject=draft_result.get('subject', 'HR Onboarding - Document Submission Reminder'),
            body=draft_result.get('body', '')
        )

        if email_sent:
            print(f"✓ Email sent successfully to {candidate.personal_email_id}")

            # Update job status
            job.status_id = StatusType.COMPLETE
            job.end_time = datetime.utcnow()
            await db.commit()
        else:
            print("✗ Failed to send email")

        # ============================================================
        # SUMMARY
        # ============================================================
        print("\n" + "="*70)
        print("END-TO-END WORKFLOW SUMMARY")
        print("="*70)
        print(f"Candidate: {candidate.candidate_name}")
        print(f"Email: {candidate.personal_email_id}")
        print(f"Joining Date: {candidate.expected_doj_wrt_to_np or '20-April-2026'}")
        print(f"Document Completion: {gap_result.get('completion_percentage', 0):.1f}%")
        print(f"Documents Received: {gap_result.get('received_documents', 0)}")
        print(f"Documents Pending: {gap_result.get('missing_documents', 0)}")
        print(f"Email Sent: {'✓ Yes' if email_sent else '✗ No'}")
        print("="*70)
        print("\n✓ END-TO-END WORKFLOW COMPLETED!")

        break


if __name__ == "__main__":
    asyncio.run(run_end_to_end())