#!/bin/bash
echo "======================================================================="
echo "   STARTING SMART TRAFFIC OS — REAL-TIME EDGE CONTROLLER PROTOTYPE     "
echo "======================================================================="
python3 -m pip install fastapi uvicorn websockets > /dev/null 2>&1
python3 -m uvicorn server.gateway:app --host 0.0.0.0 --port 8000 &
PID=$!
sleep 2
echo "[SUCCESS] Prototype running live at http://localhost:8000"
open http://localhost:8000 2>/dev/null || xdg-open http://localhost:8000 2>/dev/null
wait $PID
