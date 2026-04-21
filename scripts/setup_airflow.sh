#!/bin/bash
# =============================================================================
# Apache Airflow Setup Script for HR Onboarding Automation
# =============================================================================
# This script sets up Apache Airflow with dynamic paths based on the project root
# Installs the latest stable version of Apache Airflow
# =============================================================================

set -e

# Get the project root directory (parent of airflow folder)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
AIRFLOW_HOME="$PROJECT_ROOT/airflow"

echo "=================================================="
echo "HR Onboarding - Apache Airflow Setup"
echo "=================================================="
echo "Project Root: $PROJECT_ROOT"
echo "Airflow Home: $AIRFLOW_HOME"
echo "Airflow Version: Latest (>=2.10.0)"
echo "=================================================="

# Export environment variables
export AIRFLOW_HOME
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

# Check Python version (Airflow 2.10+ requires Python 3.8+)
PYTHON_VERSION=$(python --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
echo "Python Version: $PYTHON_VERSION"

# Create necessary directories
echo "[1/7] Creating directories..."
mkdir -p "$AIRFLOW_HOME/dags"
mkdir -p "$AIRFLOW_HOME/logs"
mkdir -p "$AIRFLOW_HOME/plugins"

# Copy DAG file if it doesn't exist
if [ ! -f "$AIRFLOW_HOME/dags/etl_dag.py" ]; then
    echo "[2/7] Copying DAG file..."
    cp "$PROJECT_ROOT/airflow/dags/etl_dag.py" "$AIRFLOW_HOME/dags/"
fi

# Create virtual environment if not exists
if [ ! -d "$PROJECT_ROOT/venv" ]; then
    echo "[3/7] Creating virtual environment..."
    python -m venv "$PROJECT_ROOT/venv"
fi

# Activate virtual environment
echo "[4/7] Activating virtual environment..."
source "$PROJECT_ROOT/venv/bin/activate"

# Install dependencies including latest Airflow
echo "[5/7] Installing dependencies (including latest Apache Airflow)..."
pip install --upgrade pip
pip install -r "$PROJECT_ROOT/requirements.txt"

# Create dynamic airflow.cfg
echo "[6/7] Creating airflow.cfg..."
cat > "$AIRFLOW_HOME/airflow.cfg" << EOF
[core]
dags_folder = $AIRFLOW_HOME/dags
sql_alchemy_conn = sqlite:///$AIRFLOW_HOME/airflow.db
executor = LocalExecutor
parallelism = 4
dag_concurrency = 2
max_active_tasks_per_dag = 2
load_examples = False

[webserver]
web_server_host = 0.0.0.0
web_server_port = 8080
secret_key = hr_automation_secret_key_change_in_production
rbac = True

[scheduler]
scheduler_heartbeat_sec = 5
min_file_process_interval = 30
catchup_by_default = False

[logging]
base_log_folder = $AIRFLOW_HOME/logs
log_format = [%(asctime)s] {%(filename)s:%(lineno)d} %(levelname)s - %(message)s
simple_log_format = %(asctime)s %(levelname)s - %(message)s
EOF

# Initialize database
echo "[7/7] Initializing Airflow database..."
cd "$PROJECT_ROOT"
airflow db init

# Show installed Airflow version
AIRFLOW_VERSION=$(airflow version 2>/dev/null || echo "unknown")
echo ""
echo "Installed Apache Airflow version: $AIRFLOW_VERSION"

# Create admin user
echo "Creating admin user..."
airflow users create \
    --username admin \
    --password admin123 \
    --firstname Admin \
    --lastname User \
    --role Admin \
    --email admin@example.com 2>/dev/null || echo "User 'admin' already exists"

echo ""
echo "=================================================="
echo "SETUP COMPLETE"
echo "=================================================="
echo "Apache Airflow Version: $AIRFLOW_VERSION"
echo ""
echo "To start Airflow, run:"
echo ""
echo "  ./scripts/start_airflow.sh"
echo ""
echo "Or manually:"
echo ""
echo "  export AIRFLOW_HOME=$AIRFLOW_HOME"
echo "  airflow scheduler &"
echo "  airflow webserver --port 8080 &"
echo ""
echo "UI: http://localhost:8080"
echo "Login: admin / admin123"
echo "=================================================="