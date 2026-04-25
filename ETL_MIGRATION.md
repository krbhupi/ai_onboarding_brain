# ETL Migration from Apache Airflow to Pure Python

## Overview

This document describes the migration from Apache Airflow to a pure Python implementation for the HR Automation ETL pipeline. This change was made to address reliability issues with Airflow's SQLite database integration and to simplify the deployment and maintenance of the application.

## Issues with Apache Airflow

1. **Disk I/O Errors**: Frequent "disk I/O error" exceptions when accessing the SQLite database
2. **Complexity**: Managing Airflow scheduler, webserver, and database added operational overhead
3. **Resource Usage**: High memory and CPU consumption for a relatively simple workflow
4. **Deployment Challenges**: Difficulties with environment setup and dependency management

## New Implementation

### Architecture

The new implementation uses pure Python scripts that:

1. **Direct Database Access**: Connects directly to SQLite without Airflow intermediaries
2. **Synchronous Job Processing**: Reuses existing job processing logic from `src/agent/orchestrator.py`
3. **Command-Line Interface**: Provides flexible execution options via CLI arguments
4. **Scheduling**: Uses the `schedule` library for periodic execution

### Components

1. **ETL Pipeline Runner**: `scripts/run_etl_pipeline.py` - Main entry point
2. **Scheduler**: `scripts/scheduler.py` - Optional periodic execution
3. **Trigger Scripts**: Updated shell scripts to call Python implementation

### Key Features

- **Full Functionality**: All ETL pipeline features preserved
- **Job Processing**: Same job processing logic as before
- **Email Integration**: Inbox checking and email sending unchanged
- **Logging**: Comprehensive logging maintained
- **Error Handling**: Robust error handling and recovery

## Migration Process

### 1. Code Changes

- Created `scripts/run_etl_pipeline.py` with all ETL functions
- Created `scripts/scheduler.py` for periodic execution
- Updated trigger scripts to call new Python implementation
- Removed Airflow dependencies from requirements.txt

### 2. Testing

- Verified ETL sync functionality
- Tested job processing
- Confirmed email integration works
- Validated database operations

### 3. Deployment

- No database schema changes required
- Existing data preserved
- Backward compatibility maintained

## Usage

### Manual Execution

```bash
# Run full ETL pipeline
python scripts/run_etl_pipeline.py --full

# Run specific components
python scripts/run_etl_pipeline.py --sync
python scripts/run_etl_pipeline.py --jobs
python scripts/run_etl_pipeline.py --inbox
python scripts/run_etl_pipeline.py --cleanup
```

### Scheduled Execution

```bash
# Run scheduler (runs daily at 10 PM and hourly)
python scripts/scheduler.py
```

### Trigger Scripts

```bash
# Use existing trigger scripts
./trigger_etl.sh
./scripts/trigger_etl.sh
```

## Benefits

1. **Improved Reliability**: Eliminated Airflow-related database errors
2. **Reduced Complexity**: Simplified architecture with fewer moving parts
3. **Better Performance**: Lower resource usage and faster execution
4. **Easier Maintenance**: Fewer dependencies and simpler debugging
5. **Flexible Deployment**: No need for complex Airflow setup

## Rollback Plan

If issues arise with the new implementation:

1. Revert requirements.txt to include Airflow dependencies
2. Restore Airflow DAG files from version control
3. Update trigger scripts to call Airflow instead of Python
4. Restart Airflow services

## Future Improvements

1. Add monitoring and alerting for ETL pipeline execution
2. Implement more sophisticated error handling and retry logic
3. Add metrics collection for performance tracking
4. Consider using Celery for distributed job processing if needed