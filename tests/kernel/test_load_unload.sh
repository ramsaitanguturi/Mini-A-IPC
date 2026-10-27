#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
MODULE="$ROOT/kernel/aipc_module.ko"
ITERATIONS="${ITERATIONS:-10}"
if [[ $EUID -ne 0 ]]; then echo "Run with sudo: sudo ITERATIONS=$ITERATIONS $0" >&2; exit 2; fi
[[ -f "$MODULE" ]] || { echo "Missing $MODULE; run make kernel-module first" >&2; exit 2; }
for ((i=1; i<=ITERATIONS; i++)); do
  insmod "$MODULE"
  [[ -c /dev/aipc ]] || { echo "FAIL: /dev/aipc missing on iteration $i" >&2; exit 1; }
  rmmod aipc_module
  [[ ! -e /sys/class/aipc/aipc ]] || { echo "FAIL: sysfs device remains after unload" >&2; exit 1; }
  echo "PASS: load/unload iteration $i/$ITERATIONS"
done
dmesg | tail -n 100 > "$ROOT/results/kernel-load-unload-dmesg.txt"
echo "Saved recent kernel log to results/kernel-load-unload-dmesg.txt; review for warnings."
