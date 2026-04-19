"""Candidate controller endpoints."""
import hashlib
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from src.core.database import get_db
from src.models.database import CandidateInfo, CandidateTypeMaster
from src.schemas.schemas import (
    CandidateCreate, CandidateUpdate, CandidateResponse,
    CandidateListResponse, BaseResponse
)

router = APIRouter()


def generate_row_hash(data: dict) -> str:
    """Generate a unique hash for candidate data."""
    hash_string = "|".join(str(v) for v in data.values() if v is not None)
    return hashlib.sha256(hash_string.encode()).hexdigest()


@router.post("/", response_model=CandidateResponse, status_code=201)
async def create_candidate(
    candidate: CandidateCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new candidate."""
    # Check if CIN already exists
    existing = await db.execute(
        select(CandidateInfo).where(CandidateInfo.cin == candidate.cin)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="CIN already exists")

    # Create candidate with auto-generated row_hash
    candidate_data = candidate.model_dump()
    candidate_data["row_hash"] = generate_row_hash(candidate_data)

    db_candidate = CandidateInfo(**candidate_data)
    db.add(db_candidate)
    await db.commit()
    await db.refresh(db_candidate)

    return db_candidate


@router.get("/", response_model=CandidateListResponse)
async def list_candidates(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    candidate_type_id: Optional[int] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """List candidates with pagination and filters."""
    query = select(CandidateInfo)

    # Apply filters
    if status:
        query = query.where(CandidateInfo.current_status == status)
    if candidate_type_id:
        query = query.where(CandidateInfo.candidate_type_id == candidate_type_id)
    if search:
        search_term = f"%{search}%"
        query = query.where(
            (CandidateInfo.candidate_name.ilike(search_term)) |
            (CandidateInfo.cin.ilike(search_term)) |
            (CandidateInfo.personal_email_id.ilike(search_term))
        )

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    # Apply pagination
    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(CandidateInfo.created_on.desc())

    result = await db.execute(query)
    candidates = result.scalars().all()

    return CandidateListResponse(
        candidates=[CandidateResponse.model_validate(c) for c in candidates],
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/{candidate_id}", response_model=CandidateResponse)
async def get_candidate(
    candidate_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get candidate by ID."""
    result = await db.execute(
        select(CandidateInfo).where(CandidateInfo.candidate_id == candidate_id)
    )
    candidate = result.scalar_one_or_none()

    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    return candidate


@router.get("/cin/{cin}", response_model=CandidateResponse)
async def get_candidate_by_cin(
    cin: str,
    db: AsyncSession = Depends(get_db)
):
    """Get candidate by CIN."""
    result = await db.execute(
        select(CandidateInfo).where(CandidateInfo.cin == cin)
    )
    candidate = result.scalar_one_or_none()

    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    return candidate


@router.put("/{candidate_id}", response_model=CandidateResponse)
async def update_candidate(
    candidate_id: int,
    candidate: CandidateUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update candidate details."""
    result = await db.execute(
        select(CandidateInfo).where(CandidateInfo.candidate_id == candidate_id)
    )
    db_candidate = result.scalar_one_or_none()

    if not db_candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # Update fields
    for key, value in candidate.model_dump(exclude_unset=True).items():
        setattr(db_candidate, key, value)

    await db.commit()
    await db.refresh(db_candidate)

    return db_candidate


@router.delete("/{candidate_id}", response_model=BaseResponse)
async def delete_candidate(
    candidate_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Delete a candidate."""
    result = await db.execute(
        select(CandidateInfo).where(CandidateInfo.candidate_id == candidate_id)
    )
    candidate = result.scalar_one_or_none()

    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    await db.delete(candidate)
    await db.commit()

    return BaseResponse(message="Candidate deleted successfully")


@router.get("/{candidate_id}/documents")
async def get_candidate_documents(
    candidate_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get all documents for a candidate."""
    from src.models.database import DocumentTracker

    # Check candidate exists
    candidate = await db.execute(
        select(CandidateInfo).where(CandidateInfo.candidate_id == candidate_id)
    )
    if not candidate.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Candidate not found")

    # Get documents
    result = await db.execute(
        select(DocumentTracker).where(
            DocumentTracker.candidate_id == candidate_id
        )
    )
    documents = result.scalars().all()

    return {
        "status": "success",
        "candidate_id": candidate_id,
        "documents": [
            {
                "document_tracker_id": d.document_tracker_id,
                "document_type_id": d.document_type_id,
                "status_id": d.status_id,
                "received_on": d.document_received_on.isoformat() if d.document_received_on else None,
                "comments": d.comments
            }
            for d in documents
        ]
    }


@router.get("/{candidate_id}/jobs")
async def get_candidate_jobs(
    candidate_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get all jobs for a candidate."""
    from src.models.database import JobTracker

    # Check candidate exists
    candidate = await db.execute(
        select(CandidateInfo).where(CandidateInfo.candidate_id == candidate_id)
    )
    if not candidate.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Candidate not found")

    # Get jobs
    result = await db.execute(
        select(JobTracker).where(
            JobTracker.candidate_id == candidate_id
        ).order_by(JobTracker.created_on.desc())
    )
    jobs = result.scalars().all()

    return {
        "status": "success",
        "candidate_id": candidate_id,
        "jobs": [
            {
                "job_id": j.job_id,
                "job_type_id": j.job_type_id,
                "status_id": j.status_id,
                "action_date": j.action_date.isoformat() if j.action_date else None,
                "human_action_required": j.human_action_required,
                "human_action": j.human_action
            }
            for j in jobs
        ]
    }