#!/usr/bin/env python
"""Simple scheduler for HR Onboarding ETL pipeline."""

import schedule
import time
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.logging import logger


def run_etl_pipeline():
    """Run the ETL pipeline script."""
    try:
        logger.info("Starting scheduled ETL pipeline execution...")

        # Run the ETL pipeline script
        result = subprocess.run([
            sys.executable,
            str(Path(__file__).parent / "run_etl_pipeline.py"),
            "--full"
        ], capture_output=True, text=True, cwd=Path(__file__).parent.parent)

        if result.returncode == 0:
            logger.info("ETL pipeline executed successfully")
            logger.debug(f"Output: {result.stdout}")
        else:
            logger.error(f"ETL pipeline failed with return code {result.returncode}")
            logger.error(f"Error: {result.stderr}")

    except Exception as e:
        logger.error(f"Error running ETL pipeline: {e}")


def main():
    """Main scheduler function."""
    logger.info("Starting HR Onboarding ETL Scheduler...")

    # Schedule the ETL pipeline to run daily at 10 PM (matching original Airflow schedule)
    schedule.every().day.at("22:00").do(run_etl_pipeline)

    # Also run every hour for more frequent processing
    schedule.every().hour.do(run_etl_pipeline)

    logger.info("Scheduler started. ETL pipeline will run:")
    logger.info("- Daily at 10:00 PM")
    logger.info("- Every hour")
    logger.info("Press Ctrl+C to stop the scheduler.")

    try:
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
    except KeyboardInterrupt:
        logger.info("Scheduler stopped by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()