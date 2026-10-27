#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
make
mkdir -p results
COUNT="${COUNT:-10000}"
TRIALS="${TRIALS:-5}"
RAW="results/benchmark.csv"
SUMMARY="results/calibration.csv"
MIXED="results/mixed_workload.csv"

printf 'trial,mode,selected_transport,payload_bytes,exchanges,elapsed_ns,avg_latency_ns,throughput_exchanges_s,validation_errors\n' > "$RAW"
for size in 64 128 256 512 1024 16384; do
  for mode in pipe shm adaptive; do
    if [[ "$mode" == "shm" && "$size" -gt 1024 ]]; then continue; fi
    for ((trial=1; trial<=TRIALS; trial++)); do
      output="$(./mini-aipc --mode "$mode" --size "$size" --count "$COUNT")"
      selected="$(printf '%s\n' "$output" | awk -F': ' '/Selected transport:/ {print $2}')"
      elapsed="$(printf '%s\n' "$output" | awk -F': ' '/^Elapsed:/ {print $2}' | awk '{print $1}')"
      latency="$(printf '%s\n' "$output" | awk -F': ' '/Average round-trip latency:/ {print $2}' | awk '{print $1}')"
      throughput="$(printf '%s\n' "$output" | awk -F': ' '/^Throughput:/ {print $2}' | awk '{print $1}')"
      errors="$(printf '%s\n' "$output" | awk -F': ' '/Validation errors:/ {print $2}')"
      printf '%s,%s,%s,%s,%s,%s,%s,%s,%s\n' "$trial" "$mode" "$selected" "$size" "$COUNT" "$elapsed" "$latency" "$throughput" "$errors" >> "$RAW"
    done
  done
done

# Calibrate threshold from median latency for each tested size.
# Choose the largest size <= 1024 where SHM median is lower than pipe median.
python3 - "$RAW" "$SUMMARY" <<'PY'
import csv, statistics, sys
raw, out = sys.argv[1:]
rows = list(csv.DictReader(open(raw, newline="")))
sizes = sorted({int(r["payload_bytes"]) for r in rows if int(r["payload_bytes"]) <= 1024})
medians = {}
for size in sizes:
    for mode in ("pipe", "shm"):
        vals = [float(r["avg_latency_ns"]) for r in rows
                if int(r["payload_bytes"]) == size and r["mode"] == mode]
        if vals:
            medians[(size, mode)] = statistics.median(vals)
threshold = 0
for s in sizes:
    if (s, "pipe") not in medians or (s, "shm") not in medians:
        break
    if medians[(s, "shm")] < medians[(s, "pipe")]:
        threshold = s
    else:
        break
with open(out, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["payload_bytes","pipe_median_avg_latency_ns","shm_median_avg_latency_ns","shm_faster","calibrated_threshold_bytes"])
    for s in sizes:
        p, h = medians.get((s,"pipe"), float("nan")), medians.get((s,"shm"), float("nan"))
        w.writerow([s, f"{p:.2f}", f"{h:.2f}", str(h < p).lower(), threshold])
with open("results/threshold.txt","w") as f:
    f.write(str(threshold) + "\n")
print(f"Calibrated threshold: {threshold} bytes (0 means SHM was not faster at tested sizes)")
PY

THRESHOLD="$(cat results/threshold.txt)"
printf 'trial,policy,workload,payload_mix,exchanges,elapsed_ns,avg_latency_ns,throughput_exchanges_s,validation_errors,threshold_bytes\n' > "$MIXED"
SMALL_COUNT=$((COUNT * 80 / 100))
LARGE_COUNT=$((COUNT - SMALL_COUNT))
if (( SMALL_COUNT < 1 )); then SMALL_COUNT=1; fi
if (( LARGE_COUNT < 1 )); then LARGE_COUNT=1; fi

# Mixed workload is run as two measured batches (small and bulk) because this
# teaching implementation launches one persistent child per transport run.
# Startup time is outside each measured interval; batch times are summed.
for policy in pipe adaptive; do
  for ((trial=1; trial<=TRIALS; trial++)); do
    if [[ "$policy" == "pipe" ]]; then
      small="$(./mini-aipc --mode pipe --size 64 --count "$SMALL_COUNT")"
      large="$(./mini-aipc --mode pipe --size 16384 --count "$LARGE_COUNT")"
    else
      small="$(AIPC_THRESHOLD="$THRESHOLD" ./mini-aipc --mode adaptive --size 64 --count "$SMALL_COUNT")"
      large="$(AIPC_THRESHOLD="$THRESHOLD" ./mini-aipc --mode adaptive --size 16384 --count "$LARGE_COUNT")"
    fi
    s_elapsed="$(printf '%s\n' "$small" | awk -F': ' '/^Elapsed:/ {print $2}' | awk '{print $1}')"
    l_elapsed="$(printf '%s\n' "$large" | awk -F': ' '/^Elapsed:/ {print $2}' | awk '{print $1}')"
    total=$((s_elapsed + l_elapsed))
    exchanges=$((SMALL_COUNT + LARGE_COUNT))
    avg="$(awk -v t="$total" -v n="$exchanges" 'BEGIN {printf "%.2f", t/n}')"
    thr="$(awk -v t="$total" -v n="$exchanges" 'BEGIN {if(t>0) printf "%.2f", n*1000000000/t; else print "0"}')"
    errs="$(printf '%s\n%s\n' "$small" "$large" | awk -F': ' '/Validation errors:/ {sum += $2} END {print sum+0}')"
    printf '%s,%s,80small_20bulk,64B:80%%+16384B:20%%,%s,%s,%s,%s,%s,%s,%s\n' \
      "$trial" "$policy" "$exchanges" "$total" "$avg" "$thr" "$errs" "$THRESHOLD" >> "$MIXED"
  done
done

echo "Wrote raw measurements: $RAW"
echo "Wrote calibration summary: $SUMMARY"
echo "Wrote mixed-workload batches: $MIXED"
echo "Threshold is written to results/threshold.txt"
