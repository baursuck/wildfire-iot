#!/bin/bash
# Full demo: broker, backend, weather stations, dashboard, then two tower edge nodes replaying FIgLib fires.
# Usage: ./run_demo.sh [tower-01 source] [tower-02 source]
#   sources default to FIgLib sequences; pass rtmp://localhost:1935/live/drone to use the drone stream.
cd "$(dirname "$0")"
PY=.venv/bin/python
export PYTHONUNBUFFERED=1
SRC1=${1:-data/figlib/20200911_FIRE_pi-s-mobo-c}
SRC2=${2:-data/figlib/20190610_FIRE_bh-w-mobo-c}
FPS=${FPS:-3}
mkdir -p out

trap 'kill $(jobs -p) 2>/dev/null' EXIT

$PY broker.py &
sleep 2
$PY backend.py &
$PY sensor_node.py --period 4 &
$PY -m http.server 8000 --directory dashboard >/dev/null 2>&1 &
sleep 1
open "http://localhost:8000" 2>/dev/null
echo "Dashboard: http://localhost:8000   (press Enter to start the towers)"
read -r

$PY edge_node.py --tower tower-01 --source "$SRC1" --fps "$FPS" --show &
sleep 4
$PY edge_node.py --tower tower-02 --source "$SRC2" --fps "$FPS" --show &
wait
