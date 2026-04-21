#!/bin/bash
# =============================================================================
# Start Apache Airflow Services
# =============================================================================
# This script starts both Airflow scheduler and webserver
# =============================================================================

# Get the project root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
AIRFLOW_HOME="$PROJECT_ROOT/airflow"

# Export environment variables
export AIRFLOW_HOME
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

# Change to project root
cd "$PROJECT_ROOT"

# Activate virtual environment if exists
if [ -f "venv/bin/activate" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
fi

# Create PID files directory
mkdir -p "$AIRFLOW_HOME/pids"

echo "=================================================="
echo "Starting Apache Airflow"
echo "=================================================="
echo "Project Root: $PROJECT_ROOT"
echo "Airflow Home: $AIRFLOW_HOME"
echo "=================================================="

# Stop any existing instances
echo "Stopping existing instances..."
pkill -f "airflow scheduler" 2>/dev/null || true
pkill -f "airflow webserver" 2>/dev/null || true
sleep 2

# Start scheduler
echo "Starting scheduler..."
nohup airflow scheduler > "$AIRFLOW_HOME/logs/scheduler.log" 2>&1 &
SCHEDULER_PID=$!
echo "$SCHEDULER_PID" > "$AIRFLOW_HOME/pids/scheduler.pid"
echo "Scheduler PID: $SCHEDULER_PID"

# Start webserver
echo "Starting webserver..."
nohup airflow webserver --port 8080 > "$AIRFLOW_HOME/logs/webserver.log" 2>&1 &
WEBSERVER_PID=$!
echo "$WEBSERVER_PID" > "$AIRFLOW_HOME/pids/webserver.pid"
echo "Webserver PID: $WEBSERVER_PID"

echo ""
echo "=================================================="
echo "AIRFLOW STARTED"
echo "=================================================="
echo ""
echo "UI: http://localhost:8080"
echo "Login: admin / admin123"
echo ""
echo "Logs:"
echo "  Scheduler: $AIRFLOW_HOME/logs/scheduler.log"
echo "  Webserver: $AIRFLOW_HOME/logs/webserver.log"
echo ""
echo "To stop:"
echo "  ./scripts/stop_airflow.sh"
echo "  or"
echo "  kill $SCHEDULER_PID $WEBSERVER_PID"
echo "=================================================="