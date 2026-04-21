#!/bin/bash
# =============================================================================
# Stop Apache Airflow Services
# =============================================================================

# Get the project root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
AIRFLOW_HOME="$PROJECT_ROOT/airflow"

echo "=================================================="
echo "Stopping Apache Airflow"
echo "=================================================="

# Kill scheduler
if [ -f "$AIRFLOW_HOME/pids/scheduler.pid" ]; then
    SCHEDULER_PID=$(cat "$AIRFLOW_HOME/pids/scheduler.pid")
    if kill -0 "$SCHEDULER_PID" 2>/dev/null; then
        echo "Stopping scheduler (PID: $SCHEDULER_PID)..."
        kill "$SCHEDULER_PID"
    fi
    rm -f "$AIRFLOW_HOME/pids/scheduler.pid"
else
    echo "Stopping scheduler..."
    pkill -f "airflow scheduler" 2>/dev/null || true
fi

# Kill webserver
if [ -f "$AIRFLOW_HOME/pids/webserver.pid" ]; then
    WEBSERVER_PID=$(cat "$AIRFLOW_HOME/pids/webserver.pid")
    if kill -0 "$WEBSERVER_PID" 2>/dev/null; then
        echo "Stopping webserver (PID: $WEBSERVER_PID)..."
        kill "$WEBSERVER_PID"
    fi
    rm -f "$AIRFLOW_HOME/pids/webserver.pid"
else
    echo "Stopping webserver..."
    pkill -f "airflow webserver" 2>/dev/null || true
fi

echo ""
echo "=================================================="
echo "AIRFLOW STOPPED"
echo "=================================================="