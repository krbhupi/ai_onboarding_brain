"""Pydantic schemas for API request/response models."""
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, EmailStr, Field


# Base schemas
class BaseResponse(BaseModel):
    """Base response schema."""
    status: str = "success"
    message: Optional[str] = None


# Candidate schemas
class CandidateBase(BaseModel):
    """Base candidate schema."""
    cin: str = Field(..., description="Candidate Identification Number")
    candidate_name: Optional[str] = None
    personal_email_id: Optional[EmailStr] = None
    contact_number: Optional[str] = None
    recruiter_name: Optional[str] = None
    designation_to_be_printed_on_the_offer_letter: Optional[str] = None
    technology: Optional[str] = None
    vertical: Optional[str] = None
    bu: Optional[str] = None
    source: Optional[str] = None
    current_status: Optional[str] = None
    candidate_type_id: Optional[int] = None


class CandidateCreate(CandidateBase):
    """Schema for creating a candidate."""
    pass


class CandidateUpdate(BaseModel):
    """Schema for updating a candidate."""
    candidate_name: Optional[str] = None
    personal_email_id: Optional[EmailStr] = None
    contact_number: Optional[str] = None
    current_status: Optional[str] = None
    candidate_type_id: Optional[int] = None


class CandidateResponse(CandidateBase):
    """Schema for candidate response."""
    candidate_id: int
    row_hash: str
    created_on: Optional[datetime] = None
    updated_on: Optional[datetime] = None

    class Config:
        from_attributes = True


class CandidateListResponse(BaseResponse):
    """Schema for candidate list response."""
    candidates: List[CandidateResponse]
    total: int
    page: int
    page_size: int


# Document schemas
class DocumentBase(BaseModel):
    """Base document schema."""
    document_name: str
    document_type_id: int
    document_received_on: Optional[date] = None
    comments: Optional[str] = None


class DocumentCreate(DocumentBase):
    """Schema for creating a document tracker entry."""
    candidate_id: int
    job_id: Optional[int] = None


class DocumentUpdate(BaseModel):
    """Schema for updating a document."""
    status_id: Optional[int] = None
    comments: Optional[str] = None


class DocumentResponse(DocumentBase):
    """Schema for document response."""
    document_tracker_id: int
    candidate_id: int
    document_store_id: Optional[int] = None
    status_id: int
    job_id: Optional[int] = None
    created_on: Optional[datetime] = None
    updated_on: Optional[datetime] = None

    class Config:
        from_attributes = True


class DocumentListResponse(BaseResponse):
    """Schema for document list response."""
    documents: List[DocumentResponse]
    total: int


class DocumentUploadResponse(BaseResponse):
    """Schema for document upload response."""
    document_tracker_id: int
    filename: str
    path: str
    status: str


# Job schemas
class JobBase(BaseModel):
    """Base job schema."""
    job_type_id: int
    candidate_id: int
    action_date: Optional[date] = None
    human_action_required: bool = False


class JobCreate(JobBase):
    """Schema for creating a job."""
    remark: Optional[str] = None


class JobUpdate(BaseModel):
    """Schema for updating a job."""
    status_id: Optional[int] = None
    human_action: Optional[str] = None
    draft_mail: Optional[str] = None
    remark: Optional[str] = None


class JobResponse(JobBase):
    """Schema for job response."""
    job_id: int
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    action_date: Optional[date] = None
    human_action_required: bool
    draft_mail: Optional[str] = None
    remark: Optional[str] = None
    status_id: int
    human_action: Optional[str] = None
    updated_on: Optional[datetime] = None

    class Config:
        from_attributes = True


class JobListResponse(BaseResponse):
    """Schema for job list response."""
    jobs: List[JobResponse]
    total: int


# Email schemas
class EmailDraftRequest(BaseModel):
    """Schema for email draft request."""
    job_id: int
    mail_type: str = "followup_reminder"


class EmailDraftResponse(BaseResponse):
    """Schema for email draft response."""
    job_id: int
    candidate_id: int
    candidate_name: str
    candidate_email: str
    subject: str
    body: str
    missing_documents: List[str]


class EmailSendRequest(BaseModel):
    """Schema for email send request."""
    job_id: int
    to_address: EmailStr
    subject: str
    body: str
    attachments: Optional[List[str]] = None


class EmailSendResponse(BaseResponse):
    """Schema for email send response."""
    message_id: Optional[str] = None
    sent_at: datetime


class EmailInboxResponse(BaseResponse):
    """Schema for inbox response."""
    emails: List[Dict[str, Any]]
    total: int


# Gap analysis schemas
class GapAnalysisRequest(BaseModel):
    """Schema for gap analysis request."""
    candidate_id: int


class GapAnalysisResponse(BaseResponse):
    """Schema for gap analysis response."""
    candidate_id: int
    cin: str
    required_documents: List[str]
    completed_documents: List[str]
    pending_documents: List[str]
    missing_documents: List[str]
    invalid_documents: List[Dict[str, Any]]
    completion_percentage: float
    next_steps: List[str]


# Document validation schemas
class DocumentValidationRequest(BaseModel):
    """Schema for document validation request."""
    document_path: str
    expected_type: str
    cin: str


class DocumentValidationResponse(BaseResponse):
    """Schema for document validation response."""
    is_valid: bool
    confidence: float
    document_path: str
    expected_type: str
    extracted_info: Dict[str, Any]
    category: str


# Status schemas
class StatusResponse(BaseModel):
    """Schema for status response."""
    status_id: int
    status_type: str
    status_description: Optional[str] = None

    class Config:
        from_attributes = True


# Health check
class HealthResponse(BaseModel):
    """Schema for health check response."""
    status: str
    app: str
    version: str
    database: Optional[str] = None
    llm: Optional[str] = None