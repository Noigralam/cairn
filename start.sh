#!/bin/bash
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    echo "Virtual environment not found. Run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
    exit 1
fi

ENGINE_PID="data/cairn.pid"
FUTURES_PID="data/cairn_futures.pid"
DASHBOARD_PID="data/dashboard.pid"

mkdir -p data

TARGET="${1:-all}"

start_engine() {
    if [ -f "$ENGINE_PID" ] && kill -0 "$(cat "$ENGINE_PID")" 2>/dev/null; then
        echo "Spot engine already running (PID $(cat "$ENGINE_PID"))"
    else
        .venv/bin/python main.py > /dev/null 2>&1 &
        echo $! > "$ENGINE_PID"
        echo "Spot engine started (PID $(cat "$ENGINE_PID"))"
    fi
}

start_futures() {
    if [ -f "$FUTURES_PID" ] && kill -0 "$(cat "$FUTURES_PID")" 2>/dev/null; then
        echo "Futures engine already running (PID $(cat "$FUTURES_PID"))"
    else
        .venv/bin/python main_futures.py > /dev/null 2>&1 &
        echo $! > "$FUTURES_PID"
        echo "Futures engine started (PID $(cat "$FUTURES_PID"))"
    fi
}

start_dashboard() {
    if [ -f "$DASHBOARD_PID" ] && kill -0 "$(cat "$DASHBOARD_PID")" 2>/dev/null; then
        echo "Dashboard already running (PID $(cat "$DASHBOARD_PID"))"
    else
        .venv/bin/python dashboard.py > /dev/null 2>&1 &
        echo $! > "$DASHBOARD_PID"
        echo "Dashboard started (PID $(cat "$DASHBOARD_PID"))"
    fi
}

case "$TARGET" in
    engine)    start_engine ;;
    futures)   start_futures ;;
    dashboard) start_dashboard ;;
    both)      start_engine; start_futures ;;
    all)       start_engine; start_futures; start_dashboard ;;
    *)
        echo "Usage: $0 [engine|futures|dashboard|both|all]"
        echo "  engine    — start spot engine only"
        echo "  futures   — start futures engine only"
        echo "  dashboard — start web dashboard only"
        echo "  both      — start spot + futures engines"
        echo "  all       — start everything (default)"
        exit 1
        ;;
esac

if [ "$TARGET" = "all" ] || [ "$TARGET" = "dashboard" ]; then
    echo "Dashboard: http://$(hostname -I | awk '{print $1}'):$(grep WEB_PORT .env | cut -d= -f2)"
fi
echo "Engine log:    tail -f data/cairn.log"
echo "Dashboard log: tail -f data/dashboard.log"
echo "Stop:          ./stop.sh"
