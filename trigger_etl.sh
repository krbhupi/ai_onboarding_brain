#!/usr/bin/env bash
# Trigger the HR onboarding ETL Pipeline (Python Implementation)

# Determine project root relative to this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
SCRIPTS_DIR="$PROJECT_ROOT/scripts"

# Activate virtual environment if present
if [ -f "$PROJECT_ROOT/venv/bin/activate" ]; then
  source "$PROJECT_ROOT/venv/bin/activate"
fi

# Run the ETL pipeline script
python "$SCRIPTS_DIR/run_etl_pipeline.py" --full
