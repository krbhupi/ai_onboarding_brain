#!/usr/bin/env python
"""Simple workflow test without LLM calls."""
import asyncio
import sys
from pathlib import Path
from datetime import datetime
import hashlib

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from src.core.database import get_db, init_db
from src.models.database import (
    CandidateInfo, DocumentTracker, JobTracker,
    DocumentTypeMaster, StatusMaster, JobTypeMaster,
    MailTypeMaster, CandidateTypeMaster
)
from src.constants.constants import StatusType, JobType, MailType, CandidateType


async def main():
    """Run the complete workflow."""
    print("\n" + "="*60)
    print("HR ONBOARDING AUTOMATION - WORKFLOW TEST")
    print("="*60)

    # Initialize database
    await init_db()

    async for db in get_db():
        # Step 1: Create seed data
        print("\n[Step 1] Creating seed data...")

        # Status types
        statuses = [
            StatusMaster(status_id=StatusType.PENDING, status_type="pending", status_description="Pending action"),
            StatusMaster(status_id=StatusType.IN_PROGRESS, status_type="in_progress", status_description="In progress"),
            StatusMaster(status_id=StatusType.COMPLETE, status_type="complete", status_description="Complete"),
            StatusMaster(status_id=StatusType.FAILED, status_type="failed", status_description="Failed"),
        ]
        for s in statuses:
            db.add(s)

        # Job types
        job_types = [
            JobTypeMaster(job_type_id=JobType.DOCUMENTS_REQUIRED, job_type="documents_required", job_description="Request documents"),
            JobTypeMaster(job_type_id=JobType.FOLLOWUP_MAIL, job_type="followup_mail", job_description="Send follow-up email"),
        ]
        for jt in job_types:
            db.add(jt)

        # Mail types
        mail_types = [
            MailTypeMaster(mail_type_id=MailType.INITIAL_REQUEST, mail_type="initial_request", mail_description="Initial document request"),
            MailTypeMaster(mail_type_id=MailType.FOLLOWUP_REMINDER, mail_type="followup_reminder", mail_description="Follow-up reminder"),
        ]
        for mt in mail_types:
            db.add(mt)

        # Candidate types
        candidate_types = [
            CandidateTypeMaster(candidate_type_id=CandidateType.FRESHER, candidate_type="Fresher", candidate_type_description="Fresh graduate"),
            CandidateTypeMaster(candidate_type_id=CandidateType.EXPERIENCE, candidate_type="Experience", candidate_type_description="Experienced hire"),
        ]
        for ct in candidate_types:
            db.add(ct)

        # Document types
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

        # Step 2: Create sample candidate
        print("\n[Step 2] Creating sample candidate...")
        row_hash = hashlib.md5(f"John Doe|john.doe@email.com|Software Engineer|TCS".encode()).hexdigest()
        candidate = CandidateInfo(
            cin="CIN-2026-001",
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

        # Step 3: Create document tracking entries
        print("\n[Step 3] Creating document tracker entries...")
        result = await db.execute(select(DocumentTypeMaster))
        all_doc_types = result.scalars().all()
        relevant_docs = [dt for dt in all_doc_types if dt.experience]

        for doc_type in relevant_docs:
            tracker = DocumentTracker(
                candidate_id=candidate.candidate_id,
                document_type_id=doc_type.document_type_id,
                status_id=StatusType.PENDING
            )
            db.add(tracker)
        await db.commit()
        print(f"✓ Created document tracking entries for {len(relevant_docs)} documents")

        # Step 4: Simulate document uploads
        print("\n[Step 4] Simulating document uploads...")
        received_docs = ["Aadhaar Card", "PAN Card", "Passport Photo", "10th Marksheet", "Degree Certificate", "Relieving Letter"]
        doc_map = {dt.document_name: dt.document_type_id for dt in all_doc_types}

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
                if tracker:
                    tracker.status_id = StatusType.COMPLETE
                    tracker.document_received_on = datetime.utcnow().date()

        await db.commit()
        print(f"✓ Simulated {len(received_docs)} documents received")

        # Step 5: Gap analysis
        print("\n[Step 5] Running gap analysis...")
        result = await db.execute(
            select(DocumentTracker).where(DocumentTracker.candidate_id == candidate.candidate_id)
        )
        trackers = result.scalars().all()

        total = len(trackers)
        received = sum(1 for t in trackers if t.status_id == StatusType.COMPLETE)
        missing = total - received

        print("\n" + "="*60)
        print("GAP ANALYSIS REPORT")
        print("="*60)
        print(f"Candidate: {candidate.candidate_name}")
        print(f"Total Documents: {total}")
        print(f"Received: {received}")
        print(f"Missing: {missing}")
        print(f"Completion: {round(received/total*100, 2)}%")

        # List missing documents
        missing_docs = []
        for t in trackers:
            if t.status_id != StatusType.COMPLETE:
                result = await db.execute(
                    select(DocumentTypeMaster).where(DocumentTypeMaster.document_type_id == t.document_type_id)
                )
                doc_type = result.scalar_one_or_none()
                if doc_type:
                    missing_docs.append(doc_type.document_name)

        if missing_docs:
            print("\nMissing Documents:")
            for doc in missing_docs:
                print(f"  - {doc}")

        print("\n" + "="*60)
        print("WORKFLOW COMPLETED SUCCESSFULLY!")
        print("="*60)
        print("\n✓ Database tables created and seeded")
        print("✓ Candidate created")
        print("✓ Document tracking initialized")
        print("✓ Documents status tracked")
        print("✓ Gap analysis performed")
        print("\nNext Steps:")
        print("1. Register app in Azure Portal for OAuth2")
        print("2. Visit http://localhost:8000/auth/outlook to authorize")
        print("3. Start the API server: python main.py")
        print("4. Access API at http://localhost:8000/docs")

        break


if __name__ == "__main__":
    asyncio.run(main())