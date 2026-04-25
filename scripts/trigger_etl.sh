#!/bin/bash
# =============================================================================
# Trigger HR Onboarding ETL Pipeline (Python Implementation)
# =============================================================================
# This script triggers the ETL pipeline manually using pure Python
# =============================================================================

# Get the project root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Activate virtual environment if exists
if [ -f "$PROJECT_ROOT/venv/bin/activate" ]; then
    source "$PROJECT_ROOT/venv/bin/activate"
fi

echo "=================================================="
echo "Triggering HR Onboarding ETL Pipeline (Python)"
echo "=================================================="

# Run the ETL pipeline script
echo "Running ETL pipeline..."
python "$PROJECT_ROOT/scripts/run_etl_pipeline.py" --full

if [ $? -eq 0 ]; then
    echo ""
    echo "=================================================="
    echo "ETL Pipeline Completed Successfully"
    echo "=================================================="
else
    echo ""
    echo "=================================================="
    echo "ETL Pipeline Failed"
    echo "=================================================="
    exit 1
fi

echo ""
echo "To view logs, check the application logs in the logs directory"
echo "=================================================="