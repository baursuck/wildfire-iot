#!/bin/bash
# Two tower edge nodes replaying FIgLib fires into an already running broker (start run_slides.sh first).
cd "$(dirname "$0")"
PY=.venv/bin/python
export PYTHONUNBUFFERED=1
trap 'kill $(jobs -p) 2>/dev/null' EXIT
FPS=${FPS:-3}
$PY edge_node.py --tower tower-01 --source data/figlib/20200911_FIRE_pi-s-mobo-c --fps "$FPS" --show &
sleep 4
$PY edge_node.py --tower tower-02 --source data/figlib/20190610_FIRE_bh-w-mobo-c --fps "$FPS" --show &
wait
