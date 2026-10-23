"""Replay every FIgLib sequence through the detector + temporal filter and report time to alarm
and false alarms before ignition (the same logic the edge node runs)."""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ultralytics import YOLO

import config
from edge_node import figlib_offset_min

model = YOLO(config.MODEL_PATH)
rows = []
for seq in sorted(glob.glob("data/figlib/*")):
    files = sorted(glob.glob(f"{seq}/*.jpg"), key=figlib_offset_min)
    streak, first_alarm, false_alarms, first_hit = 0, None, 0, None
    for f in files:
        off = figlib_offset_min(f)
        r = model.predict(f, imgsz=config.IMG_SIZE, conf=config.CONF_THRESHOLD, iou=0.01, device="mps", verbose=False)[0]
        hit = len(r.boxes) > 0
        if hit and off >= 0 and first_hit is None:
            first_hit = off
        streak = streak + 1 if hit else 0
        if streak == config.CONSECUTIVE_FRAMES:
            if off < 0:
                false_alarms += 1
            elif first_alarm is None:
                first_alarm = off
    rows.append((os.path.basename(seq), first_hit, first_alarm, false_alarms))

print(f"{'sequence':34} {'first hit':>9} {'alarm':>6} {'false before ignition':>22}")
for name, hit, alarm, fa in rows:
    print(f"{name:34} {('+%d' % hit) if hit is not None else '-':>9} {('+%d' % alarm) if alarm is not None else 'missed':>6} {fa:>22}")
detected = [a for _, _, a, _ in rows if a is not None]
print(f"\ndetected {len(detected)}/{len(rows)}, median time to alarm "
      f"{sorted(detected)[len(detected) // 2] if detected else '-'} min, false alarms {sum(r[3] for r in rows)}")
