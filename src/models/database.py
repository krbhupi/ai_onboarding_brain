"""SQLAlchemy database models for HR Automation."""
from datetime import datetime, date
from typing import Optional
from sqlalchemy import (
    Column, Integer, String, Date, DateTime, Boolean, Numeric, Text,
    ForeignKey, CheckConstraint, Index
)
from sqlalchemy.orm import relationship
from src.core.database import Base


class CandidateInfo(Base):
    """Main candidate information table."""
    __tablename__ = "candidate_info"

    candidate_id = Column(Integer, primary_key=True, autoincrement=True)
    cin = Column(String(50), unique=True, nullable=False, index=True)
    recruiter_name = Column(String(100))
    cv_sourced_date = Column(Date)
    jd_published_date = Column(Date)
    prefix = Column(String(20))
    vertical = Column(String(50))
    bu = Column(String(50))
    source_base = Column(String(50))
    source = Column(String(100))
    consultant_name = Column(String(100))
    designation_to_be_printed_on_the_offer_letter = Column(String(50))
    previous_experience = Column(String(20))
    grade = Column(String(100))
    technology = Column(String(50))
    ref_no = Column(Date)
    offer_release_date = Column(Date)
    expected_doj_wrt_to_np = Column(String(20))
    month_of_joining = Column(String(50))
    current_status = Column(String(100))
    personal_email_id = Column(String(100))
    contact_number = Column(String(200))
    current_residential_address = Column(String(255))
    current_place_of_stay = Column(String(100))
    reporting_location = Column(String(100))
    work_base_location = Column(String(100))
    np = Column(String(30))
    employment_tenure = Column(Integer)
    total_tat = Column(Integer)
    tat_jd_published_to_offer_release = Column(Integer)
    tat_offer_released_to_doj_of_the_candidate = Column(Integer)
    reason_for_drop_out = Column(String(500))
    po_name = Column(String(100))
    manager_name = Column(String(100))
    birthday = Column(String(100))
    buddy = Column(String(100))
    conversion_comments = Column(String(500))
    rate_card_k_pm = Column(Numeric(10, 2))
    df = Column(String(50))
    row_hash = Column(String(100), unique=True, nullable=False, index=True)
    created_on = Column(DateTime, default=datetime.utcnow)
    updated_on = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    candidate_type_id = Column(Integer, ForeignKey("candidate_type_master.candidate_type_id"))
    candidate_name = Column(String(100))
    end_date = Column(Date)
    grad_pg = Column(String(50))
    emp_term = Column(String(50))
    employee_id = Column(String(30))
    project = Column(String(30))

    # Relationships
    candidate_type = relationship("CandidateTypeMaster", back_populates="candidates")
    documents = relationship("DocumentTracker", back_populates="candidate", cascade="all, delete-orphan")
    jobs = relationship("JobTracker", back_populates="candidate", cascade="all, delete-orphan")


class CandidateTypeMaster(Base):
    """Candidate type master table (Fresher, Experience, Dev Partner)."""
    __tablename__ = "candidate_type_master"

    candidate_type_id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_type = Column(String(100), nullable=False)
    candidate_type_description = Column(String(255))
    created_on = Column(DateTime, default=datetime.utcnow)
    updated_on = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    # Relationships
    candidates = relationship("CandidateInfo", back_populates="candidate_type")


class DocumentTracker(Base):
    """Document tracking table for each candidate."""
    __tablename__ = "document_tracker"

    document_tracker_id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, ForeignKey("candidate_info.candidate_id"), nullable=False)
    document_type_id = Column(Integer, ForeignKey("document_type_master.document_type_id"), nullable=False)
    document_store_id = Column(Integer)  # Reference to file storage
    document_received_on = Column(Date)
    comments = Column(String(500))
    status_id = Column(Integer, ForeignKey("status_master.status_id"))
    job_id = Column(Integer, ForeignKey("job_tracker.job_id"))
    created_on = Column(DateTime, default=datetime.utcnow)
    updated_on = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    # Relationships
    candidate = relationship("CandidateInfo", back_populates="documents")
    document_type = relationship("DocumentTypeMaster", back_populates="documents")
    status = relationship("StatusMaster", back_populates="documents")
    job = relationship("JobTracker", back_populates="documents")


class DocumentTypeMaster(Base):
    """Document type master table (Aadhaar, PAN, Marksheet, etc.)."""
    __tablename__ = "document_type_master"

    document_type_id = Column(Integer, primary_key=True, autoincrement=True)
    document_name = Column(String(100), nullable=False)
    fresher = Column(Boolean, default=True)
    experience = Column(Boolean, default=True)
    dev_partner = Column(Boolean, default=True)
    created_on = Column(DateTime, default=datetime.utcnow)
    updated_on = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    # Relationships
    documents = relationship("DocumentTracker", back_populates="document_type")


class JobTracker(Base):
    """Job tracking table for workflow management."""
    __tablename__ = "job_tracker"

    job_id = Column(Integer, primary_key=True, autoincrement=True)
    job_type_id = Column(Integer, ForeignKey("job_type_master.job_type_id"), nullable=False)
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    human_action_required = Column(Boolean, default=False)
    action_date = Column(Date)
    draft_mail = Column(Text)
    remark = Column(String(500))
    candidate_id = Column(Integer, ForeignKey("candidate_info.candidate_id"), nullable=False)
    status_id = Column(Integer, ForeignKey("status_master.status_id"))
    human_action = Column(String(255))
    updated_on = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    candidate = relationship("CandidateInfo", back_populates="jobs")
    job_type = relationship("JobTypeMaster", back_populates="jobs")
    status = relationship("StatusMaster", back_populates="jobs")
    documents = relationship("DocumentTracker", back_populates="job")


class JobTypeMaster(Base):
    """Job type master table."""
    __tablename__ = "job_type_master"

    job_type_id = Column(Integer, primary_key=True, autoincrement=True)
    job_type = Column(String(100), nullable=False)
    job_subtype = Column(String(100))
    job_description = Column(String(255))
    created_on = Column(DateTime, default=datetime.utcnow)
    updated_on = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    # Relationships
    jobs = relationship("JobTracker", back_populates="job_type")
    mail_types = relationship("MailTypeMaster", back_populates="job_type")


class MailTypeMaster(Base):
    """Mail type master table with templates."""
    __tablename__ = "mail_type_master"

    mail_type_id = Column(Integer, primary_key=True, autoincrement=True)
    mail_type = Column(String(100), nullable=False)
    mail_description = Column(String(255))
    mail_template = Column(Text)
    job_type_id = Column(Integer, ForeignKey("job_type_master.job_type_id"))
    created_on = Column(DateTime, default=datetime.utcnow)
    updated_on = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    # Relationships
    job_type = relationship("JobTypeMaster", back_populates="mail_types")


class StatusMaster(Base):
    """Status master table for workflow states."""
    __tablename__ = "status_master"

    status_id = Column(Integer, primary_key=True, autoincrement=True)
    status_type = Column(String(100), nullable=False)
    status_description = Column(String(255))
    created_on = Column(DateTime, default=datetime.utcnow)
    updated_on = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    # Relationships
    documents = relationship("DocumentTracker", back_populates="status")
    jobs = relationship("JobTracker", back_populates="status")


# Create indexes for frequently queried columns
Index("ix_document_tracker_candidate_id", DocumentTracker.candidate_id)
Index("ix_job_tracker_candidate_id", JobTracker.candidate_id)
Index("ix_job_tracker_action_date", JobTracker.action_date)