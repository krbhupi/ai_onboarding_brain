"""Document controller endpoints."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.core.database import get_db
from src.models.database import DocumentTracker, DocumentTypeMaster, CandidateInfo
from src.schemas.schemas import (
    DocumentCreate, DocumentUpdate, DocumentResponse,
    DocumentListResponse, DocumentUploadResponse, BaseResponse
)
from src.services.document_service import DocumentService
from src.mcp_tools.ocr_validation import OCRValidationTool
from src.mcp_tools.segregation import SegregationTool
from src.constants.constants import StatusType

router = APIRouter()


@router.get("/types")
async def list_document_types(db: AsyncSession = Depends(get_db)):
    """List all document types."""
    result = await db.execute(
        select(DocumentTypeMaster).where(DocumentTypeMaster.is_active == True)
    )
    types = result.scalars().all()

    return {
        "status": "success",
        "document_types": [
            {
                "document_type_id": t.document_type_id,
                "document_name": t.document_name,
                "fresher": t.fresher,
                "experience": t.experience,
                "dev_partner": t.dev_partner
            }
            for t in types
        ]
    }


@router.post("/", response_model=DocumentResponse, status_code=201)
async def create_document_tracker(
    document: DocumentCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new document tracker entry."""
    # Verify candidate exists
    candidate = await db.execute(
        select(CandidateInfo).where(CandidateInfo.candidate_id == document.candidate_id)
    )
    if not candidate.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Candidate not found")

    # Verify document type exists
    doc_type = await db.execute(
        select(DocumentTypeMaster).where(
            DocumentTypeMaster.document_type_id == document.document_type_id
        )
    )
    if not doc_type.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Document type not found")

    # Create tracker entry
    doc_service = DocumentService(db)
    tracker = await doc_service.create_document_tracker(
        candidate_id=document.candidate_id,
        document_type_id=document.document_type_id,
        job_id=document.job_id,
        comments=document.comments
    )

    return tracker


@router.get("/", response_model=DocumentListResponse)
async def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    candidate_id: Optional[int] = None,
    status_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    """List document trackers with pagination."""
    query = select(DocumentTracker)

    if candidate_id:
        query = query.where(DocumentTracker.candidate_id == candidate_id)
    if status_id:
        query = query.where(DocumentTracker.status_id == status_id)

    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(DocumentTracker.created_on.desc())

    result = await db.execute(query)
    documents = result.scalars().all()

    # Get total count
    count_query = select(DocumentTracker)
    if candidate_id:
        count_query = count_query.where(DocumentTracker.candidate_id == candidate_id)
    if status_id:
        count_query = count_query.where(DocumentTracker.status_id == status_id)

    total = len((await db.execute(count_query)).scalars().all())

    return DocumentListResponse(
        documents=[DocumentResponse.model_validate(d) for d in documents],
        total=total
    )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get document tracker by ID."""
    result = await db.execute(
        select(DocumentTracker).where(
            DocumentTracker.document_tracker_id == document_id
        )
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    return document


@router.put("/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: int,
    document: DocumentUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update document tracker status."""
    result = await db.execute(
        select(DocumentTracker).where(
            DocumentTracker.document_tracker_id == document_id
        )
    )
    db_document = result.scalar_one_or_none()

    if not db_document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Update fields
    if document.status_id:
        db_document.status_id = document.status_id
    if document.comments:
        db_document.comments = document.comments

    await db.commit()
    await db.refresh(db_document)

    return db_document


@router.post("/{document_id}/validate")
async def validate_document(
    document_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Validate a document using OCR."""
    result = await db.execute(
        select(DocumentTracker).where(
            DocumentTracker.document_tracker_id == document_id
        )
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Get candidate for CIN
    candidate_result = await db.execute(
        select(CandidateInfo).where(
            CandidateInfo.candidate_id == document.candidate_id
        )
    )
    candidate = candidate_result.scalar_one_or_none()

    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # Get document type
    doc_type_result = await db.execute(
        select(DocumentTypeMaster).where(
            DocumentTypeMaster.document_type_id == document.document_type_id
        )
    )
    doc_type = doc_type_result.scalar_one_or_none()

    if not doc_type:
        raise HTTPException(status_code=404, detail="Document type not found")

    # Get document path (would be stored in document_store_id)
    # For now, assume path is stored in comments or a separate table
    doc_path = document.comments  # This should be replaced with actual path lookup

    # Run OCR validation
    ocr_tool = OCRValidationTool()
    validation_result = await ocr_tool.execute(
        document_path=doc_path,
        expected_type=doc_type.document_name,
        cin=candidate.cin
    )

    # Update document status based on validation
    doc_service = DocumentService(db)
    status_id = StatusType.COMPLETE if validation_result.get("is_valid") else StatusType.FAILED
    await doc_service.update_document_status(
        document_tracker_id=document_id,
        status_id=status_id,
        comments=f"OCR Validation: {validation_result.get('reason', 'Unknown')}"
    )

    return {
        "status": "success",
        "document_id": document_id,
        "validation_result": validation_result
    }


@router.post("/upload")
async def upload_document(
    candidate_id: int,
    file: UploadFile = File(...),
    document_type_id: int = None,
    db: AsyncSession = Depends(get_db)
):
    """Upload a document for a candidate."""
    from pathlib import Path
    import aiofiles

    # Verify candidate exists
    candidate_result = await db.execute(
        select(CandidateInfo).where(CandidateInfo.candidate_id == candidate_id)
    )
    candidate = candidate_result.scalar_one_or_none()

    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # Save file
    doc_service = DocumentService(db)
    content = await file.read()

    result = await doc_service.save_document(
        cin=candidate.cin,
        filename=file.filename,
        content=content,
        category=None  # Will be determined after validation
    )

    # Create document tracker entry if document_type_id provided
    if document_type_id:
        # Get pending job for this candidate
        from src.models.database import JobTracker, JobTypeMaster, StatusMaster
        from src.constants.constants import JobType

        # Get or create a job
        job_type_result = await db.execute(
            select(JobTypeMaster).where(JobTypeMaster.job_type == "save_attachment")
        )
        job_type = job_type_result.scalar_one_or_none()

        pending_status = await db.execute(
            select(StatusMaster).where(StatusMaster.status_type == "pending")
        )
        pending = pending_status.scalar_one_or_none()

        tracker = await doc_service.create_document_tracker(
            candidate_id=candidate_id,
            document_type_id=document_type_id,
            job_id=None,  # Will be associated later
            comments=f"Uploaded: {file.filename}"
        )

        return DocumentUploadResponse(
            document_tracker_id=tracker.document_tracker_id,
            filename=file.filename,
            path=result["path"],
            status="uploaded"
        )

    return DocumentUploadResponse(
        document_tracker_id=0,
        filename=file.filename,
        path=result["path"],
        status="uploaded_pending_classification"
    )


@router.post("/segregate/{candidate_id}")
async def segregate_documents(
    candidate_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Segregate documents for a candidate into categories."""
    # Verify candidate
    candidate_result = await db.execute(
        select(CandidateInfo).where(CandidateInfo.candidate_id == candidate_id)
    )
    candidate = candidate_result.scalar_one_or_none()

    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # Get all documents for candidate
    doc_result = await db.execute(
        select(DocumentTracker).where(
            DocumentTracker.candidate_id == candidate_id
        )
    )
    documents = doc_result.scalars().all()

    # Get validation results (would come from OCR validation)
    validation_results = []
    for doc in documents:
        # Placeholder - in real implementation, get from previous validation
        validation_results.append({
            "path": doc.comments or "",
            "expected_type": "Document",
            "is_valid": True
        })

    # Run segregation
    segregation_tool = SegregationTool()
    result = await segregation_tool.execute(
        cin=candidate.cin,
        documents=[{"path": d.comments or "", "type": "document"} for d in documents],
        validation_results=validation_results
    )

    return {
        "status": "success",
        "candidate_id": candidate_id,
        "segregation_result": result
    }