#!/bin/bash
# =============================================================================
# Apache Airflow Setup Script for HR Onboarding Automation
# =============================================================================
# This script sets up Apache Airflow with dynamic paths based on the project root
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
echo "=================================================="

# Export environment variables
export AIRFLOW_HOME
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

# Create necessary directories
echo "[1/6] Creating directories..."
mkdir -p "$AIRFLOW_HOME/dags"
mkdir -p "$AIRFLOW_HOME/logs"
mkdir -p "$AIRFLOW_HOME/plugins"

# Copy DAG file if it doesn't exist
if [ ! -f "$AIRFLOW_HOME/dags/etl_dag.py" ]; then
    echo "[2/6] Copying DAG file..."
    cp "$PROJECT_ROOT/airflow/dags/etl_dag.py" "$AIRFLOW_HOME/dags/"
fi

# Create dynamic airflow.cfg
echo "[3/6] Creating airflow.cfg..."
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
echo "[4/6] Initializing Airflow database..."
cd "$PROJECT_ROOT"
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

airflow db init

# Create admin user
echo "[5/6] Creating admin user..."
airflow users create \
    --username admin \
    --password admin123 \
    --firstname Admin \
    --lastname User \
    --role Admin \
    --email admin@example.com 2>/dev/null || echo "User 'admin' already exists"

echo "[6/6] Setup complete!"
echo ""
echo "=================================================="
echo "SETUP COMPLETE"
echo "=================================================="
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