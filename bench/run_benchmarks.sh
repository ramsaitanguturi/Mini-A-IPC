#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p results
OUT="results/benchmark.csv"
COUNT="${COUNT:-10000}"
TRIALS="${TRIALS:-5}"

make
printf 'trial,requested_mode,selected_transport,payload_bytes,exchanges,elapsed_ns,avg_latency_ns,throughput_exchanges_s,validation_errors\n' > "$OUT"

for size in 64 1024 16384; do
  for mode in pipe shm adaptive; do
    # The mailbox intentionally rejects payloads larger than 1024 bytes.
    if [[ "$mode" == "shm" && "$size" -gt 1024 ]]; then continue; fi
    for ((trial=1; trial<=TRIALS; trial++)); do
      output="$(./mini-aipc --mode "$mode" --size "$size" --count "$COUNT")"
      selected="$(printf '%s\n' "$output" | awk -F': ' '/Selected transport:/ {print $2}')"
      elapsed="$(printf '%s\n' "$output" | awk -F': ' '/^Elapsed:/ {print $2}' | awk '{print $1}')"
      latency="$(printf '%s\n' "$output" | awk -F': ' '/Average round-trip latency:/ {print $2}' | awk '{print $1}')"
      throughput="$(printf '%s\n' "$output" | awk -F': ' '/^Throughput:/ {print $2}' | awk '{print $1}')"
      errors="$(printf '%s\n' "$output" | awk -F': ' '/Validation errors:/ {print $2}')"
      printf '%s,%s,%s,%s,%s,%s,%s,%s,%s\n' "$trial" "$mode" "$selected" "$size" "$COUNT" "$elapsed" "$latency" "$throughput" "$errors" >> "$OUT"
    done
  done
done

echo "Wrote actual measurements to $OUT"
