"""Airflow DAG for HR Onboarding ETL pipeline."""
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.empty import EmptyOperator
from airflow.providers.postgres.operators.postgres import PostgresOperator

from config.settings import get_settings

settings = get_settings()

default_args = {
    'owner': 'hr_automation',
    'depends_on_past': False,
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 3,
    'retry_delay': timedelta(minutes=5),
    'email': ['hr@example.com']
}


def run_etl_pipeline(**context):
    """Run the ETL pipeline to sync Excel data to database."""
    import asyncio
    import sys
    import os

    # Add project path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from src.services.etl_service import ETLService
    from src.core.database import async_session_maker

    async def _run():
        async with async_session_maker() as session:
            etl = ETLService(session)
            return await etl.sync_candidates()

    return asyncio.run(_run())


def check_pending_jobs(**context):
    """Check for pending jobs that need processing."""
    import asyncio
    import sys
    import os

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from sqlalchemy import select
    from src.models.database import JobTracker, StatusMaster
    from src.core.database import async_session_maker
    from src.constants.constants import StatusType

    async def _check():
        async with async_session_maker() as session:
            # Get pending status
            status_result = await session.execute(
                select(StatusMaster).where(StatusMaster.status_type == "pending")
            )
            pending_status = status_result.scalar_one_or_none()

            if not pending_status:
                return []

            # Get pending jobs
            result = await session.execute(
                select(JobTracker).where(
                    JobTracker.status_id == pending_status.status_id,
                    JobTracker.action_date <= datetime.utcnow().date()
                )
            )
            jobs = result.scalars().all()

            return [job.job_id for job in jobs]

    job_ids = asyncio.run(_check())
    context['ti'].xcom_push(key='pending_job_ids', value=job_ids)
    return len(job_ids)


def process_job(**context):
    """Process a single job from the queue."""
    import asyncio
    import sys
    import os

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from src.agent.orchestrator import run_job_sync

    job_ids = context['ti'].xcom_pull(key='pending_job_ids', task_ids='check_pending_jobs')

    if not job_ids:
        return "No jobs to process"

    processed = []
    for job_id in job_ids[:10]:  # Process up to 10 jobs per run
        try:
            result = run_job_sync(job_id)
            processed.append({'job_id': job_id, 'status': 'success', 'result': str(result)})
        except Exception as e:
            processed.append({'job_id': job_id, 'status': 'error', 'error': str(e)})

    return processed


def check_inbox(**context):
    """Check inbox for new candidate emails."""
    import asyncio
    import sys
    import os

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from src.services.email_service import EmailService

    async def _check():
        email_service = EmailService()
        emails = await email_service.read_inbox(unread_only=True)
        return len(emails)

    return asyncio.run(_check())


def create_daily_jobs(**context):
    """Create daily read_inbox and gap_analysis jobs for active candidates."""
    import asyncio
    import sys
    import os
    from datetime import date

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from sqlalchemy import select
    from src.models.database import CandidateInfo, JobTracker, JobTypeMaster, StatusMaster
    from src.core.database import async_session_maker

    async def _create():
        async with async_session_maker() as session:
            # Get active candidates (status = 'offer_accepted' or similar)
            result = await session.execute(
                select(CandidateInfo).where(
                    CandidateInfo.current_status.in_(['offer_accepted', 'onboarding', 'documents_pending'])
                )
            )
            candidates = result.scalars().all()

            # Get job types
            read_inbox_type = await session.execute(
                select(JobTypeMaster).where(JobTypeMaster.job_type == "read_inbox")
            )
            read_inbox = read_inbox_type.scalar_one_or_none()

            # Get pending status
            pending_status = await session.execute(
                select(StatusMaster).where(StatusMaster.status_type == "pending")
            )
            pending = pending_status.scalar_one_or_none()

            jobs_created = 0
            for candidate in candidates:
                # Create read_inbox job
                job = JobTracker(
                    candidate_id=candidate.candidate_id,
                    job_type_id=read_inbox.job_type_id if read_inbox else 4,
                    status_id=pending.status_id if pending else 1,
                    action_date=date.today(),
                    human_action_required=False,
                    start_time=datetime.utcnow()
                )
                session.add(job)
                jobs_created += 1

            await session.commit()
            return jobs_created

    return asyncio.run(_create())


def cleanup_old_jobs(**context):
    """Cleanup completed jobs older than 30 days."""
    import asyncio
    import sys
    import os
    from datetime import timedelta

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from sqlalchemy import delete
    from src.models.database import JobTracker, StatusMaster
    from src.core.database import async_session_maker

    async def _cleanup():
        async with async_session_maker() as session:
            # Get complete status
            status_result = await session.execute(
                select(StatusMaster).where(StatusMaster.status_type == "complete")
            )
            complete_status = status_result.scalar_one_or_none()

            if complete_status:
                cutoff_date = datetime.utcnow() - timedelta(days=30)
                result = await session.execute(
                    delete(JobTracker).where(
                        JobTracker.status_id == complete_status.status_id,
                        JobTracker.updated_on < cutoff_date
                    )
                )
                await session.commit()
                return result.rowcount

            return 0

    return asyncio.run(_cleanup())


# Define the DAG
dag = DAG(
    'hr_onboarding_etl',
    default_args=default_args,
    description='HR Onboarding ETL Pipeline - Daily sync and job processing',
    schedule_interval='0 22 * * *',  # Daily at 10 PM IST
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=['hr', 'onboarding', 'etl']
)

# Task definitions
start_task = EmptyOperator(
    task_id='start',
    dag=dag
)

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

end_task = EmptyOperator(
    task_id='end',
    dag=dag
)

# Define task dependencies
start_task >> etl_task >> create_jobs_task >> [check_jobs_task, check_inbox_task]
check_jobs_task >> process_jobs_task
[process_jobs_task, check_inbox_task] >> cleanup_task >> end_task