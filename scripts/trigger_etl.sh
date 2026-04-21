#!/bin/bash
# =============================================================================
# Trigger HR Onboarding ETL DAG
# =============================================================================
# This script triggers the ETL pipeline manually
# =============================================================================

# Get the project root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
AIRFLOW_HOME="$PROJECT_ROOT/airflow"

# Export environment variables
export AIRFLOW_HOME
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

# Activate virtual environment if exists
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

echo "=================================================="
echo "Triggering HR Onboarding ETL Pipeline"
echo "=================================================="

# Check if DAG exists
echo "Checking DAG..."
airflow dags list | grep hr_onboarding_etl || {
    echo "DAG not found. Make sure Airflow is running."
    exit 1
}

# Trigger the DAG
echo "Triggering DAG..."
airflow dags trigger hr_onboarding_etl

echo ""
echo "=================================================="
echo "ETL Pipeline Triggered"
echo "=================================================="
echo ""
echo "To check status:"
echo "  airflow dags list-runs hr_onboarding_etl"
echo ""
echo "To view logs:"
echo "  airflow tasks logs hr_onboarding_etl run_etl_pipeline <execution_date>"
echo ""
echo "UI: http://localhost:8080"
echo "=================================================="