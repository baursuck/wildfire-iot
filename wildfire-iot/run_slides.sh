#!/bin/bash
# Presentation mode: broker + backend + weather, the operator dashboard and the local deck.
# Clicking a fire on the interactive slide publishes wildfire/sim/fire: the backend sends it
# to Telegram and the dashboard draws it on the map.
cd "$(dirname "$0")"
PY=.venv/bin/python
export PYTHONUNBUFFERED=1
trap 'kill $(jobs -p) 2>/dev/null' EXIT

$PY broker.py &
sleep 2
$PY backend.py &
$PY sensor_node.py --period 4 &
$PY -m http.server 8000 --directory dashboard >/dev/null 2>&1 &
$PY -m http.server 8020 --directory ../presentation >/dev/null 2>&1 &
sleep 1
open "http://localhost:8000" 2>/dev/null
open "http://localhost:8020/#s1" 2>/dev/null
echo "Dashboard: http://localhost:8000"
echo "Slides:    http://localhost:8020"
echo "Real towers (optional, second terminal): ./run_towers.sh"
echo "Ctrl+C stops everything."
wait
