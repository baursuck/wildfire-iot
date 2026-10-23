#!/bin/bash
# Download HPWREN FIgLib image sequences (one frame per minute, offset from ignition in the filename).
# The legacy host has an expired certificate, hence -k.
B=https://legacy-www.hpwren.ucsd.edu/FIgLib/HPWREN-FIgLib-Data
for SEQ in "$@"; do
  mkdir -p "data/figlib/$SEQ"
  for F in $(curl -skL "$B/$SEQ/" | grep -o 'href=[^>]*jpg' | sed 's/href=//'); do
    OUT="data/figlib/$SEQ/$(echo "$F" | sed 's/%2B/+/')"
    [ -f "$OUT" ] || curl -skL -o "$OUT" "$B/$SEQ/$F" &
    [ "$(jobs -r | wc -l)" -ge 8 ] && wait
  done
  wait
  echo "$SEQ: $(ls data/figlib/$SEQ | wc -l) frames"
done
