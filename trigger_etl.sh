#!/usr/bin/env bash
# Trigger the HR onboarding ETL DAG

# Determine project root relative to this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
export AIRFLOW_HOME="$PROJECT_ROOT/airflow"

# Activate virtual environment if present
if [ -f "$PROJECT_ROOT/venv/bin/activate" ]; then
  source "$PROJECT_ROOT/venv/bin/activate"
fi

# Trigger the DAG
airflow dags trigger hr_onboarding_etl
