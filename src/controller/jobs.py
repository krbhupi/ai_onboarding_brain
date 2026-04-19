"""Job controller endpoints."""
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.core.database import get_db
from src.models.database import JobTracker, JobTypeMaster, StatusMaster, CandidateInfo
from src.schemas.schemas import (
    JobCreate, JobUpdate, JobResponse, JobListResponse, BaseResponse
)
from src.constants.constants import StatusType

router = APIRouter()


@router.get("/types")
async def list_job_types(db: AsyncSession = Depends(get_db)):
    """List all job types."""
    result = await db.execute(
        select(JobTypeMaster).where(JobTypeMaster.is_active == True)
    )
    types = result.scalars().all()

    return {
        "status": "success",
        "job_types": [
            {
                "job_type_id": t.job_type_id,
                "job_type": t.job_type,
                "job_subtype": t.job_subtype,
                "job_description": t.job_description
            }
            for t in types
        ]
    }


@router.get("/statuses")
async def list_statuses(db: AsyncSession = Depends(get_db)):
    """List all statuses."""
    result = await db.execute(
        select(StatusMaster).where(StatusMaster.is_active == True)
    )
    statuses = result.scalars().all()

    return {
        "status": "success",
        "statuses": [
            {
                "status_id": s.status_id,
                "status_type": s.status_type,
                "status_description": s.status_description
            }
            for s in statuses
        ]
    }


@router.get("/pending/action")
async def get_pending_actions(
    action_date: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get jobs that require human action today."""
    from datetime import date

    target_date = date.fromisoformat(action_date) if action_date else date.today()

    # Get pending status
    pending_status = await db.execute(
        select(StatusMaster).where(StatusMaster.status_type == "pending")
    )
    pending = pending_status.scalar_one_or_none()

    query = select(JobTracker).where(
        JobTracker.status_id == pending.status_id if pending else StatusType.PENDING,
        JobTracker.human_action_required == True,
        JobTracker.human_action == None,  # Not yet acted upon
        JobTracker.action_date <= target_date
    )

    result = await db.execute(query)
    jobs = result.scalars().all()

    return {
        "status": "success",
        "action_date": target_date.isoformat(),
        "pending_actions": [
            {
                "job_id": j.job_id,
                "candidate_id": j.candidate_id,
                "job_type_id": j.job_type_id,
                "action_date": j.action_date.isoformat() if j.action_date else None,
                "draft_mail": j.draft_mail
            }
            for j in jobs
        ],
        "total": len(jobs)
    }


@router.post("/", response_model=JobResponse, status_code=201)
async def create_job(
    job: JobCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new job in the tracker."""
    # Verify candidate exists
    candidate_result = await db.execute(
        select(CandidateInfo).where(CandidateInfo.candidate_id == job.candidate_id)
    )
    if not candidate_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Candidate not found")

    # Verify job type exists
    job_type_result = await db.execute(
        select(JobTypeMaster).where(JobTypeMaster.job_type_id == job.job_type_id)
    )
    if not job_type_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Job type not found")

    # Get pending status
    pending_status = await db.execute(
        select(StatusMaster).where(StatusMaster.status_type == "pending")
    )
    pending = pending_status.scalar_one_or_none()

    # Create job
    db_job = JobTracker(
        candidate_id=job.candidate_id,
        job_type_id=job.job_type_id,
        status_id=pending.status_id if pending else StatusType.PENDING,
        action_date=job.action_date,
        human_action_required=job.human_action_required,
        remark=job.remark,
        start_time=datetime.utcnow()
    )

    db.add(db_job)
    await db.commit()
    await db.refresh(db_job)

    return db_job


@router.get("/", response_model=JobListResponse)
async def list_jobs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    candidate_id: Optional[int] = None,
    job_type_id: Optional[int] = None,
    status_id: Optional[int] = None,
    action_date: Optional[str] = None,
    human_action_required: Optional[bool] = None,
    db: AsyncSession = Depends(get_db)
):
    """List jobs with pagination and filters."""
    query = select(JobTracker)

    # Apply filters
    if candidate_id:
        query = query.where(JobTracker.candidate_id == candidate_id)
    if job_type_id:
        query = query.where(JobTracker.job_type_id == job_type_id)
    if status_id:
        query = query.where(JobTracker.status_id == status_id)
    if action_date:
        from datetime import date
        query = query.where(JobTracker.action_date == date.fromisoformat(action_date))
    if human_action_required is not None:
        query = query.where(JobTracker.human_action_required == human_action_required)

    # Order by created date desc
    query = query.order_by(JobTracker.created_on.desc())

    # Apply pagination
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    jobs = result.scalars().all()

    # Get total count (simplified)
    count_query = select(JobTracker)
    if candidate_id:
        count_query = count_query.where(JobTracker.candidate_id == candidate_id)

    total_result = await db.execute(count_query)
    total = len(total_result.scalars().all())

    return JobListResponse(
        jobs=[JobResponse.model_validate(j) for j in jobs],
        total=total
    )


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get job by ID."""
    result = await db.execute(
        select(JobTracker).where(JobTracker.job_id == job_id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return job


@router.put("/{job_id}", response_model=JobResponse)
async def update_job(
    job_id: int,
    job: JobUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update job status or human action."""
    result = await db.execute(
        select(JobTracker).where(JobTracker.job_id == job_id)
    )
    db_job = result.scalar_one_or_none()

    if not db_job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Update fields
    if job.status_id:
        db_job.status_id = job.status_id
    if job.human_action:
        db_job.human_action = job.human_action
    if job.draft_mail:
        db_job.draft_mail = job.draft_mail
    if job.remark:
        db_job.remark = job.remark

    db_job.updated_on = datetime.utcnow()

    await db.commit()
    await db.refresh(db_job)

    return db_job


@router.post("/{job_id}/approve")
async def approve_job(
    job_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Approve a job (set human action to accept)."""
    result = await db.execute(
        select(JobTracker).where(JobTracker.job_id == job_id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job.human_action = "accept"
    job.updated_on = datetime.utcnow()

    await db.commit()
    await db.refresh(job)

    return {
        "status": "success",
        "message": "Job approved",
        "job_id": job_id,
        "human_action": job.human_action
    }


@router.post("/{job_id}/reject")
async def reject_job(
    job_id: int,
    reason: str = None,
    db: AsyncSession = Depends(get_db)
):
    """Reject a job (set human action to reject)."""
    result = await db.execute(
        select(JobTracker).where(JobTracker.job_id == job_id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job.human_action = "reject"
    if reason:
        job.remark = reason
    job.updated_on = datetime.utcnow()

    await db.commit()

    return {
        "status": "success",
        "message": "Job rejected",
        "job_id": job_id
    }