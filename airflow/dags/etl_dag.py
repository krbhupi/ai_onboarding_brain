"""Airflow DAG for HR Onboarding ETL pipeline.

This DAG implements the HR onboarding document collection workflow:
1. Sync candidate data from Excel to database
2. Create follow-up jobs for active candidates
3. Check inbox for new emails and attachments
4. Process pending jobs (validation, gap analysis)
5. Cleanup old completed jobs

Compatible with Apache Airflow >= 2.10.0
Uses TaskFlow API for cleaner code.
"""
import os
import sys
from datetime import datetime, timedelta, date
from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from airflow.providers.standard.operators.empty import EmptyOperator
from airflow.decorators import task

# Dynamically resolve project root path
AIRFLOW_HOME = os.environ.get('AIRFLOW_HOME', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROJECT_ROOT = os.path.dirname(AIRFLOW_HOME)

# Add project root to Python path
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Default arguments for the DAG
default_args = {
    'owner': 'hr_automation',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
}


# =============================================================================
# Task Functions using TaskFlow API (Airflow 2.10+)
# =============================================================================

@task(task_id='run_etl_pipeline')
def run_etl_pipeline(**context):
    """Run the ETL pipeline to sync Excel data to database.

    Reads the offer tracker Excel file and syncs candidate data to SQLite database.
    Creates new candidates and updates existing ones based on row hash comparison.

    Returns:
        dict: Summary of synced candidates (new, updated, total)
    """
    import asyncio

    from src.services.etl_service import ETLService
    from src.core.database import get_db, init_db

    async def _run():
        await init_db()
        async for session in get_db():
            etl = ETLService(session)
            result = await etl.sync_candidates()
            return result

    result = asyncio.run(_run())
    print(f"ETL Pipeline Result: {result}")
    return result


@task(task_id='check_pending_jobs')
def check_pending_jobs(**context):
    """Check for pending jobs that need processing.

    Queries the job_tracker table for jobs with:
    - status = PENDING
    - action_date <= today

    Returns:
        list: List of job IDs that need processing
    """
    import asyncio

    from sqlalchemy import select
    from src.models.database import JobTracker
    from src.core.database import get_db, init_db
    from src.constants.constants import StatusType

    async def _check():
        await init_db()
        async for session in get_db():
            result = await session.execute(
                select(JobTracker).where(
                    JobTracker.status_id == StatusType.PENDING,
                    JobTracker.action_date <= date.today()
                )
            )
            jobs = result.scalars().all()
            return [job.job_id for job in jobs]

    job_ids = asyncio.run(_check())
    print(f"Found {len(job_ids)} pending jobs: {job_ids}")
    return job_ids


@task(task_id='process_jobs')
def process_jobs(pending_job_ids, **context):
    """Process pending jobs from the queue.

    Handles different job types:
    - documents_required: Run gap analysis for candidate
    - followup_mail: Generate and send follow-up email
    - document_validation: Validate submitted documents

    Args:
        pending_job_ids: List of job IDs from check_pending_jobs task

    Returns:
        list: Processing results for each job
    """
    import asyncio

    from src.mcp_tools.gap_analysis import GapAnalysisTool
    from src.mcp_tools.draft_prepare import DraftPrepareTool
    from src.mcp_tools.document_validator import DocumentValidator
    from src.core.database import get_db, init_db
    from src.models.database import JobTracker, CandidateInfo
    from src.constants.constants import StatusType
    from sqlalchemy import select
    import os

    if not pending_job_ids:
        print("No jobs to process")
        return []

    async def _process():
        await init_db()
        async for session in get_db():
            processed = []
            for job_id in pending_job_ids[:5]:  # Process up to 5 jobs per run
                try:
                    # Get job details
                    result = await session.execute(
                        select(JobTracker).where(JobTracker.job_id == job_id)
                    )
                    job = result.scalar_one_or_none()

                    if not job:
                        processed.append({'job_id': job_id, 'status': 'error', 'error': 'Job not found'})
                        continue

                    # Get candidate info
                    result = await session.execute(
                        select(CandidateInfo).where(CandidateInfo.candidate_id == job.candidate_id)
                    )
                    candidate = result.scalar_one_or_none()

                    # Update status to in progress
                    job.status_id = StatusType.IN_PROGRESS
                    await session.commit()

                    # Process based on job type
                    if job.job_type_id == 1:  # documents_required
                        # Run gap analysis
                        gap_tool = GapAnalysisTool(session)
                        await gap_tool.execute(candidate_id=job.candidate_id)

                    elif job.job_type_id == 2:  # document_validation
                        # Validate documents with name check
                        doc_folder = f"data/documents/{candidate.candidate_name}"
                        if os.path.exists(doc_folder):
                            validator = DocumentValidator(session)
                            await validator.validate_all_documents(
                                candidate_id=job.candidate_id,
                                documents_folder=doc_folder,
                                candidate_name=candidate.candidate_name
                            )

                    elif job.job_type_id == 3:  # followup_mail
                        # Generate follow-up email draft
                        draft_tool = DraftPrepareTool(session)
                        await draft_tool.execute(candidate_id=job.candidate_id)

                    # Mark complete
                    job.status_id = StatusType.COMPLETE
                    await session.commit()
                    processed.append({'job_id': job_id, 'status': 'success'})

                except Exception as e:
                    processed.append({'job_id': job_id, 'status': 'error', 'error': str(e)})
                    print(f"Error processing job {job_id}: {e}")

            return processed

    results = asyncio.run(_process())
    print(f"Processed {len(results)} jobs: {results}")
    return results


@task(task_id='check_inbox')
def check_inbox(**context):
    """Check inbox for new candidate emails.

    Reads unread emails from configured IMAP inbox,
    processes attachments, and creates jobs for new candidates.

    Returns:
        str: Summary of processed emails
    """
    import asyncio

    from src.services.email_service import EmailService

    async def _check():
        email_service = EmailService()
        emails = await email_service.read_inbox(unread_only=True, limit=50)
        return f"Processed {len(emails)} new emails"

    result = asyncio.run(_check())
    print(result)
    return result


@task(task_id='create_daily_jobs')
def create_daily_jobs(**context):
    """Create daily follow-up jobs for active candidates.

    Creates follow-up jobs for candidates with status:
    - offer_accepted
    - onboarding
    - documents_pending

    Returns:
        str: Summary of jobs created
    """
    import asyncio

    from sqlalchemy import select
    from src.models.database import CandidateInfo, JobTracker, JobTypeMaster
    from src.core.database import get_db, init_db
    from src.constants.constants import StatusType

    async def _create():
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
            return f"Created {jobs_created} follow-up jobs for {len(candidates)} active candidates"

    result = asyncio.run(_create())
    print(result)
    return result


@task(task_id='cleanup_old_jobs')
def cleanup_old_jobs(**context):
    """Cleanup completed jobs older than 30 days.

    Removes job_tracker entries that are:
    - status = COMPLETE
    - updated_on > 30 days ago

    Returns:
        str: Summary of cleaned jobs
    """
    import asyncio

    from sqlalchemy import delete
    from src.models.database import JobTracker
    from src.core.database import get_db, init_db
    from src.constants.constants import StatusType

    async def _cleanup():
        await init_db()
        async for session in get_db():
            cutoff_date = datetime.utcnow() - timedelta(days=30)
            result = await session.execute(
                delete(JobTracker).where(
                    JobTracker.status_id == StatusType.COMPLETE,
                    JobTracker.updated_on < cutoff_date
                )
            )
            await session.commit()
            return f"Cleaned up {result.rowcount} old jobs"

    result = asyncio.run(_cleanup())
    print(result)
    return result


# =============================================================================
# DAG Definition
# =============================================================================

with DAG(
    'hr_onboarding_etl',
    default_args=default_args,
    description='HR Onboarding ETL Pipeline - Daily sync and job processing',
    schedule='0 22 * * *',  # Daily at 10 PM IST
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=['hr', 'onboarding', 'etl', 'automation'],
    doc_md="""
    ## HR Onboarding ETL Pipeline

    This DAG automates the HR onboarding document collection workflow.

    ### Tasks
    1. **run_etl_pipeline** - Sync candidate data from Excel to database
    2. **create_daily_jobs** - Create follow-up jobs for active candidates
    3. **check_pending_jobs** - Find jobs that need processing
    4. **process_jobs** - Execute pending jobs (validation, gap analysis)
    5. **check_inbox** - Monitor email for new documents
    6. **cleanup_old_jobs** - Remove old completed jobs

    ### Configuration
    - Excel file: `data/input/offer_tracker.xlsx`
    - Database: `hr_onboarding.db` (SQLite)
    - Email: Gmail SMTP/IMAP (configured in .env)
    - LLM: Ollama Cloud for document validation

    ### Manual Trigger
    ```bash
    airflow dags trigger hr_onboarding_etl
    ```

    ### Requirements
    - Apache Airflow >= 2.10.0
    - Python >= 3.8
    - All dependencies from requirements.txt
    """,
    ) as dag:

    # Task definitions
    start_task = EmptyOperator(task_id='start')

    etl_task = run_etl_pipeline()

    create_jobs_task = create_daily_jobs()

    check_jobs_task = check_pending_jobs()

    process_jobs_task = process_jobs(check_jobs_task)

    inbox_task = check_inbox()

    cleanup_task = cleanup_old_jobs()

    end_task = EmptyOperator(task_id='end')

    # Define task dependencies
    # Flow: start >> etl >> create_jobs >> [check_jobs, inbox] >> process >> cleanup >> end
    start_task >> etl_task >> create_jobs_task >> [check_jobs_task, inbox_task]
    check_jobs_task >> process_jobs_task
    [process_jobs_task, inbox_task] >> cleanup_task >> end_task