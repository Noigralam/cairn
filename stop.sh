#!/bin/bash
cd "$(dirname "$0")"

ENGINE_PID="data/cairn.pid"
FUTURES_PID="data/cairn_futures.pid"
DASHBOARD_PID="data/dashboard.pid"

TARGET="${1:-all}"

stop_engine() {
    if [ -f "$ENGINE_PID" ]; then
        PID=$(cat "$ENGINE_PID")
        if kill -0 "$PID" 2>/dev/null; then
            kill "$PID"
            echo "Spot engine stopped (PID $PID)"
        else
            echo "Stale spot engine PID $PID"
        fi
        rm "$ENGINE_PID"
    fi
    LEFTOVER=$(pgrep -f "python.*main\.py" 2>/dev/null)
    if [ -n "$LEFTOVER" ]; then
        echo "Killing leftover spot engine process(es): $LEFTOVER"
        pkill -f "python.*main\.py"
    fi
}

stop_futures() {
    if [ -f "$FUTURES_PID" ]; then
        PID=$(cat "$FUTURES_PID")
        if kill -0 "$PID" 2>/dev/null; then
            kill "$PID"
            echo "Futures engine stopped (PID $PID)"
        else
            echo "Stale futures engine PID $PID"
        fi
        rm "$FUTURES_PID"
    fi
    LEFTOVER=$(pgrep -f "python.*main_futures\.py" 2>/dev/null)
    if [ -n "$LEFTOVER" ]; then
        echo "Killing leftover futures engine process(es): $LEFTOVER"
        pkill -f "python.*main_futures\.py"
    fi
}

stop_dashboard() {
    if [ -f "$DASHBOARD_PID" ]; then
        PID=$(cat "$DASHBOARD_PID")
        if kill -0 "$PID" 2>/dev/null; then
            kill "$PID"
            echo "Dashboard stopped (PID $PID)"
        else
            echo "Stale dashboard PID $PID"
        fi
        rm "$DASHBOARD_PID"
    fi
    LEFTOVER=$(pgrep -f "python.*dashboard\.py" 2>/dev/null)
    if [ -n "$LEFTOVER" ]; then
        echo "Killing leftover dashboard process(es): $LEFTOVER"
        pkill -f "python.*dashboard\.py"
    fi
}

case "$TARGET" in
    engine)    stop_engine ;;
    futures)   stop_futures ;;
    dashboard) stop_dashboard ;;
    both)      stop_engine; stop_futures ;;
    all)       stop_engine; stop_futures; stop_dashboard ;;
    *)
        echo "Usage: $0 [engine|futures|dashboard|both|all]"
        echo "  engine    — stop spot engine only"
        echo "  futures   — stop futures engine only"
        echo "  dashboard — stop web dashboard only"
        echo "  both      — stop spot + futures engines"
        echo "  all       — stop everything (default)"
        exit 1
        ;;
esac
