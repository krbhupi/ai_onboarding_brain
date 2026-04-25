#!/usr/bin/env python
"""Pure Python ETL pipeline runner - replacement for Airflow DAG."""

import asyncio
import argparse
import sys
from datetime import datetime, date
from pathlib import Path

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from src.core.database import get_db, init_db
from src.models.database import (
    CandidateInfo, JobTracker, JobTypeMaster,
    StatusMaster, DocumentTracker, DocumentTypeMaster
)
from src.services.etl_service import ETLService
from src.services.email_service import EmailService
from src.agent.orchestrator import OnboardingAgent
from src.constants.constants import StatusType, JobType
from config.settings import get_settings
from config.logging import logger

settings = get_settings()


async def run_etl_pipeline():
    """Run the ETL pipeline to sync Excel data to database.

    Reads the offer tracker Excel file and syncs candidate data to database.
    Creates new candidates and updates existing ones based on row hash comparison.

    Returns:
        dict: Summary of synced candidates (new, updated, total)
    """
    logger.info("Starting ETL pipeline...")

    await init_db()
    async for session in get_db():
        etl = ETLService(session)
        result = await etl.sync_candidates()
        logger.info(f"ETL Pipeline completed: {result}")
        return result


async def create_daily_jobs():
    """Create daily follow-up jobs for active candidates.

    Creates follow-up jobs for candidates with status:
    - offer_accepted
    - onboarding
    - documents_pending

    Returns:
        str: Summary of jobs created
    """
    logger.info("Creating daily follow-up jobs...")

    await init_db()
    async for session in get_db():
        # Get all active candidates
        result = await session.execute(
            select(CandidateInfo).where(
                CandidateInfo.current_status.in_(['offer_accepted', 'onboarding', 'documents_pending'])
            )
        )
        candidates = result.scalars().all()

        # Get followup job type
        result = await session.execute(
            select(JobTypeMaster).where(JobTypeMaster.job_type == "followup_mail")
        )
        followup_type = result.scalar_one_or_none()

        if not followup_type:
            return "Follow-up job type not found"

        jobs_created = 0
        for candidate in candidates:
            # Check if job already exists for today
            result = await session.execute(
                select(JobTracker).where(
                    JobTracker.candidate_id == candidate.candidate_id,
                    JobTracker.job_type_id == followup_type.job_type_id,
                    JobTracker.action_date == date.today()
                )
            )
            existing = result.scalar_one_or_none()

            if not existing:
                job = JobTracker(
                    candidate_id=candidate.candidate_id,
                    job_type_id=followup_type.job_type_id,
                    status_id=StatusType.PENDING,
                    action_date=date.today(),
                    human_action_required=True
                )
                session.add(job)
                jobs_created += 1

        await session.commit()
        result_msg = f"Created {jobs_created} follow-up jobs for {len(candidates)} active candidates"
        logger.info(result_msg)
        return result_msg


async def check_pending_jobs(limit: int = 5):
    """Check for pending jobs that need processing.

    Queries the job_tracker table for jobs with:
    - status = PENDING
    - action_date <= today

    Args:
        limit: Maximum number of jobs to return

    Returns:
        list: List of job IDs that need processing
    """
    logger.info("Checking for pending jobs...")

    await init_db()
    async for session in get_db():
        result = await session.execute(
            select(JobTracker).where(
                JobTracker.status_id == StatusType.PENDING,
                JobTracker.action_date <= date.today()
            ).limit(limit)
        )
        jobs = result.scalars().all()
        job_ids = [job.job_id for job in jobs]
        logger.info(f"Found {len(job_ids)} pending jobs: {job_ids}")
        return job_ids


async def process_jobs(pending_job_ids):
    """Process pending jobs from the queue.

    Handles different job types:
    - documents_required: Run gap analysis for candidate
    - followup_mail: Generate and send follow-up email
    - document_validation: Validate submitted documents

    Args:
        pending_job_ids: List of job IDs from check_pending_jobs

    Returns:
        list: Processing results for each job
    """
    if not pending_job_ids:
        logger.info("No jobs to process")
        return []

    logger.info(f"Processing {len(pending_job_ids)} jobs...")

    await init_db()
    async for session in get_db():
        agent = OnboardingAgent(session)
        processed = []

        for job_id in pending_job_ids:
            try:
                result = await agent.process_job(job_id)
                processed.append({'job_id': job_id, 'result': result})
                logger.info(f"Processed job {job_id}: {result}")
            except Exception as e:
                error_result = {'job_id': job_id, 'error': str(e)}
                processed.append(error_result)
                logger.error(f"Error processing job {job_id}: {e}")

        return processed


async def check_inbox(limit: int = 50):
    """Check inbox for new candidate emails.

    Reads unread emails from configured IMAP inbox,
    processes attachments, and creates jobs for new candidates.

    Args:
        limit: Maximum number of emails to process

    Returns:
        str: Summary of processed emails
    """
    logger.info("Checking inbox for new emails...")

    email_service = EmailService()
    emails = await email_service.read_inbox(unread_only=True, limit=limit)

    result_msg = f"Processed {len(emails)} new emails"
    logger.info(result_msg)
    return result_msg


async def cleanup_old_jobs(days_old: int = 30):
    """Cleanup completed jobs older than specified days.

    Removes job_tracker entries that are:
    - status = COMPLETE
    - updated_on > specified days ago

    Args:
        days_old: Number of days after which to delete completed jobs

    Returns:
        str: Summary of cleaned jobs
    """
    logger.info(f"Cleaning up jobs older than {days_old} days...")

    from datetime import timedelta

    await init_db()
    async for session in get_db():
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)
        result = await session.execute(
            select(JobTracker).where(
                JobTracker.status_id == StatusType.COMPLETE,
                JobTracker.updated_on < cutoff_date
            )
        )
        old_jobs = result.scalars().all()

        deleted_count = 0
        for job in old_jobs:
            await session.delete(job)
            deleted_count += 1

        await session.commit()
        result_msg = f"Cleaned up {deleted_count} old jobs"
        logger.info(result_msg)
        return result_msg


async def run_full_pipeline():
    """Run the complete ETL pipeline."""
    logger.info("=" * 60)
    logger.info("STARTING HR ONBOARDING ETL PIPELINE")
    logger.info("=" * 60)

    start_time = datetime.now()

    try:
        # Step 1: Run ETL sync
        etl_result = await run_etl_pipeline()

        # Step 2: Create daily jobs
        jobs_result = await create_daily_jobs()

        # Step 3: Check inbox
        inbox_result = await check_inbox()

        # Step 4: Check and process pending jobs
        pending_jobs = await check_pending_jobs()
        if pending_jobs:
            process_result = await process_jobs(pending_jobs)
        else:
            process_result = "No pending jobs to process"

        # Step 5: Cleanup old jobs
        cleanup_result = await cleanup_old_jobs()

        # Log completion
        end_time = datetime.now()
        duration = end_time - start_time

        logger.info("=" * 60)
        logger.info("ETL PIPELINE COMPLETED SUCCESSFULLY")
        logger.info(f"Duration: {duration}")
        logger.info("=" * 60)
        logger.info(f"ETL Result: {etl_result}")
        logger.info(f"Jobs Created: {jobs_result}")
        logger.info(f"Inbox Check: {inbox_result}")
        logger.info(f"Jobs Processed: {process_result}")
        logger.info(f"Cleanup Result: {cleanup_result}")
        logger.info("=" * 60)

        return {
            "etl_result": etl_result,
            "jobs_result": jobs_result,
            "inbox_result": inbox_result,
            "process_result": process_result,
            "cleanup_result": cleanup_result,
            "duration": str(duration)
        }

    except Exception as e:
        logger.error(f"ETL Pipeline failed: {e}")
        raise


def main():
    """Main entry point for the ETL pipeline."""
    parser = argparse.ArgumentParser(description="HR Onboarding ETL Pipeline")
    parser.add_argument("--full", action="store_true", help="Run full ETL pipeline")
    parser.add_argument("--sync", action="store_true", help="Run only ETL sync")
    parser.add_argument("--jobs", action="store_true", help="Process pending jobs")
    parser.add_argument("--inbox", action="store_true", help="Check inbox for new emails")
    parser.add_argument("--cleanup", action="store_true", help="Cleanup old jobs")
    parser.add_argument("--create-jobs", action="store_true", help="Create daily follow-up jobs")
    parser.add_argument("--job-limit", type=int, default=5, help="Limit for job processing (default: 5)")

    args = parser.parse_args()

    # Run the appropriate function based on arguments
    if args.full:
        result = asyncio.run(run_full_pipeline())
        return result
    elif args.sync:
        result = asyncio.run(run_etl_pipeline())
        return result
    elif args.jobs:
        pending_jobs = asyncio.run(check_pending_jobs(args.job_limit))
        if pending_jobs:
            result = asyncio.run(process_jobs(pending_jobs))
            return result
        else:
            print("No pending jobs to process")
            return []
    elif args.inbox:
        result = asyncio.run(check_inbox())
        return result
    elif args.cleanup:
        result = asyncio.run(cleanup_old_jobs())
        return result
    elif args.create_jobs:
        result = asyncio.run(create_daily_jobs())
        return result
    else:
        # Default to full pipeline
        result = asyncio.run(run_full_pipeline())
        return result


if __name__ == "__main__":
    main()