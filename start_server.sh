#!/bin/bash
# Start script for LLM HL-Constraints Solver with multi-process support

# Default configuration
HOST=${HOST:-"0.0.0.0"}
PORT=${PORT:-8000}
WORKERS=${WORKERS:-1}
LOG_LEVEL=${LOG_LEVEL:-"info"}

# Get CPU count for default worker calculation
CPU_COUNT=$(python3 -c "import multiprocessing; print(multiprocessing.cpu_count())")

# If WORKERS is set to "auto", use CPU count
if [ "$WORKERS" = "auto" ]; then
    WORKERS=$CPU_COUNT
fi

echo "Starting LLM HL-Constraints Solver..."
echo "  Host: $HOST"
echo "  Port: $PORT"
echo "  Workers: $WORKERS"
echo "  CPU Count: $CPU_COUNT"
echo "  Log Level: $LOG_LEVEL"

# Check if running with multiple workers
if [ "$WORKERS" -gt 1 ]; then
    echo "  Mode: Multi-process (workers=$WORKERS)"
    uvicorn app:app \
        --host "$HOST" \
        --port "$PORT" \
        --workers "$WORKERS" \
        --log-level "$LOG_LEVEL" \
        --access-log
else
    echo "  Mode: Single-process (async)"
    uvicorn app:app \
        --host "$HOST" \
        --port "$PORT" \
        --log-level "$LOG_LEVEL" \
        --access-log
fi

