#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p results
OUT="results/environment.txt"
{
  echo "Mini A-IPC experiment environment"
  echo "Captured at: $(date --iso-8601=seconds 2>/dev/null || date)"
  echo
  echo "[OS release]"
  cat /etc/os-release 2>/dev/null || true
  echo
  echo "[WSL version]"
  if grep -qi microsoft /proc/version 2>/dev/null; then
    grep -i microsoft /proc/version || true
    if command -v wslinfo >/dev/null 2>&1; then
      wslinfo --version 2>&1 || true
    else
      echo "wslinfo not installed; see /proc/version and uname output."
    fi
  else
    echo "No Microsoft/WSL marker detected in /proc/version."
  fi
  echo
  echo "[Kernel]"
  uname -a
  echo
  echo "[CPU]"
  lscpu 2>/dev/null || grep -m1 'model name' /proc/cpuinfo || true
  echo
  echo "[Compiler]"
  gcc --version 2>&1 | head -n 1
  echo
  echo "[Build flags]"
  grep -E '^CFLAGS|^LDFLAGS' Makefile || true
  echo
  echo "[CPU Affinity Configuration]"
  echo "CPU_PRODUCER=${CPU_PRODUCER:-0}"
  echo "CPU_CONSUMER=${CPU_CONSUMER:-1}"
  if taskset -c "${CPU_PRODUCER:-0}" true 2>/dev/null; then
    echo "sched_setaffinity / taskset status: SUPPORTED and ACTIVE"
  else
    echo "sched_setaffinity / taskset status: NOT SUPPORTED in current environment"
  fi
  echo
  echo "[Experiment settings]"
  echo "COUNT=${COUNT:-10000}"
  echo "TRIALS=${TRIALS:-5}"
  echo "WARMUP=${WARMUP:-500}"
  echo "Comparative benchmark payload sizes: 64, 128, 256, 512, 1024 bytes"
  echo "Comparative benchmark mechanisms: pipe, fifo, sysv, posix, shm, uds"
  echo "Calibration payload sizes: 64, 128, 256, 512, 1024 bytes"
  echo "Baseline extra payload size: 16384 bytes"
  echo "Mixed evaluation payload sizes: 64 and 16384 bytes"
  echo "Mixed workload: 80% small, 20% large; deterministic shuffled sequence"
} > "$OUT"
echo "Wrote $OUT"
cat "$OUT"
