"""Tests for database models."""
import pytest
from datetime import datetime, date
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.database import (
    Base, CandidateInfo, CandidateTypeMaster, DocumentTracker,
    DocumentTypeMaster, JobTracker, JobTypeMaster, MailTypeMaster, StatusMaster
)


@pytest.fixture
async def db_session():
    """Create a test database session."""
    # This would be replaced with actual test database setup
    pass


class TestCandidateInfo:
    """Tests for CandidateInfo model."""

    def test_create_candidate(self):
        """Test creating a candidate."""
        candidate = CandidateInfo(
            cin="20240101_REF123",
            candidate_name="John Doe",
            personal_email_id="john@example.com",
            row_hash="test_hash_123"
        )

        assert candidate.cin == "20240101_REF123"
        assert candidate.candidate_name == "John Doe"
        assert candidate.personal_email_id == "john@example.com"

    def test_candidate_defaults(self):
        """Test default values for candidate."""
        candidate = CandidateInfo(
            cin="test_cin",
            row_hash="test_hash"
        )

        assert candidate.created_on is not None
        assert candidate.updated_on is not None


class TestDocumentTracker:
    """Tests for DocumentTracker model."""

    def test_create_document_tracker(self):
        """Test creating a document tracker entry."""
        tracker = DocumentTracker(
            candidate_id=1,
            document_type_id=1,
            status_id=1,
            job_id=1
        )

        assert tracker.candidate_id == 1
        assert tracker.is_active is True


class TestJobTracker:
    """Tests for JobTracker model."""

    def test_create_job(self):
        """Test creating a job tracker entry."""
        job = JobTracker(
            candidate_id=1,
            job_type_id=1,
            status_id=1,
            human_action_required=True
        )

        assert job.candidate_id == 1
        assert job.human_action_required is True


class TestStatusMaster:
    """Tests for StatusMaster model."""

    def test_status_types(self):
        """Test status master entries."""
        statuses = [
            ("pending", "Document/job pending processing"),
            ("in_progress", "Document/job currently being processed"),
            ("complete", "Document/job completed successfully"),
            ("failed", "Document/job failed to process"),
        ]

        for status_type, description in statuses:
            status = StatusMaster(
                status_type=status_type,
                status_description=description
            )
            assert status.status_type == status_type


class TestJobTypeMaster:
    """Tests for JobTypeMaster model."""

    def test_job_types(self):
        """Test job type master entries."""
        job_types = [
            ("documents_required", "Initial document request"),
            ("mail_send", "Send email"),
            ("followup_mail", "Follow-up email"),
            ("read_inbox", "Read inbox for replies"),
            ("save_attachment", "Save email attachments"),
            ("ocr_validation", "Validate documents with OCR"),
            ("segregation", "Segregate documents into categories"),
            ("gap_analysis", "Analyze document gaps"),
        ]

        for job_type, description in job_types:
            job = JobTypeMaster(
                job_type=job_type,
                job_description=description
            )
            assert job.job_type == job_type