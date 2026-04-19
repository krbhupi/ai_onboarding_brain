"""Initialize database with tables and seed data."""
import asyncio
from datetime import datetime

from src.core.database import init_db, async_session_maker
from src.models.database import (
    Base, CandidateInfo, CandidateTypeMaster, DocumentTypeMaster,
    JobTypeMaster, MailTypeMaster, StatusMaster, DocumentTracker, JobTracker
)


async def seed_master_data(session):
    """Seed master tables with initial data."""

    # Status Master
    statuses = [
        StatusMaster(status_id=1, status_type="pending", status_description="Waiting to be processed"),
        StatusMaster(status_id=2, status_type="in_progress", status_description="Currently being processed"),
        StatusMaster(status_id=3, status_type="complete", status_description="Successfully completed"),
        StatusMaster(status_id=4, status_type="failed", status_description="Processing failed"),
        StatusMaster(status_id=5, status_type="on_hold", status_description="On hold pending review"),
    ]
    session.add_all(statuses)

    # Candidate Type Master
    candidate_types = [
        CandidateTypeMaster(candidate_type_id=1, candidate_type="Fresher", candidate_type_description="Entry level candidate"),
        CandidateTypeMaster(candidate_type_id=2, candidate_type="Experience", candidate_type_description="Experienced hire"),
        CandidateTypeMaster(candidate_type_id=3, candidate_type="Dev Partner", candidate_type_description="Development partner hire"),
    ]
    session.add_all(candidate_types)

    # Document Type Master
    doc_types = [
        DocumentTypeMaster(document_type_id=1, document_name="Aadhaar Card", fresher=True, experience=True, dev_partner=True),
        DocumentTypeMaster(document_type_id=2, document_name="PAN Card", fresher=True, experience=True, dev_partner=True),
        DocumentTypeMaster(document_type_id=3, document_name="10th Marksheet", fresher=True, experience=True, dev_partner=False),
        DocumentTypeMaster(document_type_id=4, document_name="12th Marksheet", fresher=True, experience=True, dev_partner=False),
        DocumentTypeMaster(document_type_id=5, document_name="Degree Certificate", fresher=True, experience=True, dev_partner=False),
        DocumentTypeMaster(document_type_id=6, document_name="Passport Photo", fresher=True, experience=True, dev_partner=True),
        DocumentTypeMaster(document_type_id=7, document_name="Bank Passbook/Cancelled Cheque", fresher=True, experience=True, dev_partner=True),
        DocumentTypeMaster(document_type_id=8, document_name="Relieving Letter", fresher=False, experience=True, dev_partner=False),
        DocumentTypeMaster(document_type_id=9, document_name="Experience Certificate", fresher=False, experience=True, dev_partner=False),
        DocumentTypeMaster(document_type_id=10, document_name="Salary Slip (Last 3 months)", fresher=False, experience=True, dev_partner=False),
        DocumentTypeMaster(document_type_id=11, document_name="Form 16", fresher=False, experience=True, dev_partner=False),
        DocumentTypeMaster(document_type_id=12, document_name="Partner Agreement", fresher=False, experience=False, dev_partner=True),
    ]
    session.add_all(doc_types)

    # Job Type Master
    job_types = [
        JobTypeMaster(job_type_id=1, job_type="documents_required", job_description="Initial document request"),
        JobTypeMaster(job_type_id=2, job_type="mail_send", job_description="Send email to candidate"),
        JobTypeMaster(job_type_id=3, job_type="followup_mail", job_description="Follow-up email"),
        JobTypeMaster(job_type_id=4, job_type="read_inbox", job_description="Read inbox for replies"),
        JobTypeMaster(job_type_id=5, job_type="save_attachment", job_description="Save email attachments"),
        JobTypeMaster(job_type_id=6, job_type="ocr_validation", job_description="Validate documents with OCR"),
        JobTypeMaster(job_type_id=7, job_type="segregation", job_description="Segregate documents into categories"),
        JobTypeMaster(job_type_id=8, job_type="gap_analysis", job_description="Analyze document gaps"),
    ]
    session.add_all(job_types)

    # Mail Type Master
    mail_types = [
        MailTypeMaster(
            mail_type_id=1,
            mail_type="initial_request",
            mail_description="Initial document request email",
            mail_template="Dear {candidate_name},\n\nWelcome to our team! Please submit the following documents:\n\n{document_list}\n\nBest regards,\nHR Team",
            job_type_id=1
        ),
        MailTypeMaster(
            mail_type_id=2,
            mail_type="followup_reminder",
            mail_description="Follow-up reminder email",
            mail_template="Dear {candidate_name},\n\nThis is a reminder to submit the following pending documents:\n\n{document_list}\n\nPlease submit at your earliest convenience.\n\nBest regards,\nHR Team",
            job_type_id=3
        ),
        MailTypeMaster(
            mail_type_id=3,
            mail_type="document_received",
            mail_description="Document received confirmation",
            mail_template="Dear {candidate_name},\n\nWe have received your documents. Thank you for your submission.\n\nBest regards,\nHR Team",
            job_type_id=2
        ),
        MailTypeMaster(
            mail_type_id=4,
            mail_type="gap_notification",
            mail_description="Missing document notification",
            mail_template="Dear {candidate_name},\n\nThe following documents are still required:\n\n{document_list}\n\nPlease submit these documents to complete your onboarding.\n\nBest regards,\nHR Team",
            job_type_id=3
        ),
    ]
    session.add_all(mail_types)

    await session.commit()
    print("Master data seeded successfully!")


async def main():
    """Initialize database and seed data."""
    print("Creating database tables...")

    # Import all models to ensure they're registered
    from src.models import database
    from src.core.database import engine
    from sqlalchemy import text

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Verify tables were created
        result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        tables = result.fetchall()
        print(f"Tables created: {[t[0] for t in tables]}")

    print("\nSeeding master data...")
    async with async_session_maker() as session:
        await seed_master_data(session)

    print("\nDatabase initialization complete!")


if __name__ == "__main__":
    asyncio.run(main())