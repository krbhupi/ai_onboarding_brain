"""Airflow DAG for HR Onboarding ETL pipeline."""
import os
import sys
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.empty import EmptyOperator

# Dynamically resolve project root path
# Get AIRFLOW_HOME or use this file's parent parent directory
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


def run_etl_pipeline(**context):
    """Run the ETL pipeline to sync Excel data to database."""
    import asyncio

    from src.services.etl_service import ETLService
    from src.core.database import get_db, init_db

    async def _run():
        await init_db()
        async for session in get_db():
            etl = ETLService(session)
            result = await etl.sync_candidates()
            return result

    return asyncio.run(_run())


def check_pending_jobs(**context):
    """Check for pending jobs that need processing."""
    import asyncio
    from datetime import date

    from sqlalchemy import select
    from src.models.database import JobTracker, StatusMaster
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

    return asyncio.run(_check())


def process_job(**context):
    """Process a single job from the queue."""
    import asyncio

    from src.mcp_tools.gap_analysis import GapAnalysisTool
    from src.mcp_tools.draft_prepare import DraftPrepareTool
    from src.core.database import get_db, init_db
    from src.models.database import JobTracker
    from src.constants.constants import StatusType
    from sqlalchemy import select
    from datetime import date

    job_ids = context['ti'].xcom_pull(task_ids='check_pending_jobs')

    if not job_ids:
        return "No jobs to process"

    async def _process():
        await init_db()
        async for session in get_db():
            processed = []
            for job_id in job_ids[:5]:  # Process up to 5 jobs per run
                try:
                    # Get job
                    result = await session.execute(
                        select(JobTracker).where(JobTracker.job_id == job_id)
                    )
                    job = result.scalar_one_or_none()

                    if job:
                        # Update status to in progress
                        job.status_id = StatusType.IN_PROGRESS
                        await session.commit()

                        # Process based on job type
                        if job.job_type_id == 1:  # documents_required
                            # Run gap analysis
                            gap_tool = GapAnalysisTool(session)
                            await gap_tool.execute(candidate_id=job.candidate_id)

                        # Mark complete
                        job.status_id = StatusType.COMPLETE
                        await session.commit()
                        processed.append({'job_id': job_id, 'status': 'success'})

                except Exception as e:
                    processed.append({'job_id': job_id, 'status': 'error', 'error': str(e)})

            return processed

    return asyncio.run(_process())


def check_inbox(**context):
    """Check inbox for new candidate emails."""
    import asyncio

    from src.services.email_service import EmailService

    async def _check():
        email_service = EmailService()
        emails = await email_service.read_inbox(unread_only=True, limit=50)
        return f"Processed {len(emails)} new emails"

    return asyncio.run(_check())


def create_daily_jobs(**context):
    """Create daily follow-up jobs for active candidates."""
    import asyncio
    from datetime import date

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
            return f"Created {jobs_created} follow-up jobs"

    return asyncio.run(_create())


def cleanup_old_jobs(**context):
    """Cleanup completed jobs older than 30 days."""
    import asyncio
    from datetime import timedelta

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

    return asyncio.run(_cleanup())


# Define the DAG
dag = DAG(
    'hr_onboarding_etl',
    default_args=default_args,
    description='HR Onboarding ETL Pipeline - Daily sync and job processing',
    schedule_interval='0 22 * * *',  # Daily at 10 PM IST
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=['hr', 'onboarding', 'etl'],
    doc_md="""
    ## HR Onboarding ETL Pipeline

    This DAG performs the following tasks daily:
    1. Syncs candidate data from Excel to database
    2. Creates follow-up jobs for active candidates
    3. Checks inbox for new emails
    4. Processes pending jobs
    5. Cleans up old completed jobs

    ### Configuration
    - Uses dynamic paths from AIRFLOW_HOME environment variable
    - Excel file: data/input/offer_tracker.xlsx (relative to project root)
    - Database: hr_onboarding.db (SQLite)
    - Email: Gmail SMTP/IMAP
    """
)

# Task definitions
start_task = EmptyOperator(task_id='start', dag=dag)

etl_task = PythonOperator(
    task_id='run_etl_pipeline',
    python_callable=run_etl_pipeline,
    dag=dag
)

create_jobs_task = PythonOperator(
    task_id='create_daily_jobs',
    python_callable=create_daily_jobs,
    dag=dag
)

check_jobs_task = PythonOperator(
    task_id='check_pending_jobs',
    python_callable=check_pending_jobs,
    dag=dag
)

process_jobs_task = PythonOperator(
    task_id='process_jobs',
    python_callable=process_job,
    dag=dag
)

check_inbox_task = PythonOperator(
    task_id='check_inbox',
    python_callable=check_inbox,
    dag=dag
)

cleanup_task = PythonOperator(
    task_id='cleanup_old_jobs',
    python_callable=cleanup_old_jobs,
    dag=dag
)

end_task = EmptyOperator(task_id='end', dag=dag)

# Define task dependencies
# start >> etl >> create_jobs >> [check_jobs, check_inbox] >> process >> cleanup >> end
start_task >> etl_task >> create_jobs_task >> [check_jobs_task, check_inbox_task]
check_jobs_task >> process_jobs_task
[process_jobs_task, check_inbox_task] >> cleanup_task >> end_task