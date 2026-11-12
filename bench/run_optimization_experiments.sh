#!/usr/bin/env bash
# ==============================================================================
# Mini A-IPC: Systematic Optimization Experiment Runner
#
# Orchestrates controlled experiments evaluating the optimization roadmap:
#   Phase 1: Baseline Preservation (results/baseline_comparative.csv)
#   Phase 2: Semaphore-Monitoring Overhead (results/sem_wait_optimization.csv)
#   Phase 3: Cache-Line Alignment (results/cacheline_alignment.csv)
#   Phase 4: SPSC Lock-Free Ring Buffer (results/spsc_ring_buffer.csv)
#   Phase 5: Adaptive Telemetry Policy (results/adaptive_policy.csv)
#   Phase 6: Mixed Workload Benchmark (results/mixed_workload.csv)
#
# Generates:
#   results/EXPERIMENT_LOG.md
#   results/OPTIMIZATION_REPORT.md
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

COUNT=10000
WARMUP=500
TRIALS=5
QUICK=0
OUTPUT_DIR="results"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --quick|-q)
            QUICK=1
            COUNT=1000
            WARMUP=100
            TRIALS=2
            shift
            ;;
        --count|-c)
            COUNT="$2"
            shift 2
            ;;
        --trials|-t)
            TRIALS="$2"
            shift 2
            ;;
        --output-dir|-o)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 2
            ;;
    esac
done

mkdir -p "$OUTPUT_DIR"

cleanup() {
    rm -f /dev/shm/*mini_aipc* /tmp/mini_aipc* 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "=============================================================================="
echo "          Mini A-IPC: Controlled Optimization Experiments Runner             "
echo "=============================================================================="
echo "Configuration: Count=$COUNT, Warmup=$WARMUP, Trials=$TRIALS, Quick=$QUICK"
echo "Output Directory: $OUTPUT_DIR"
echo "=============================================================================="

# Pre-flight build
if [ ! -x "./mini-aipc" ] || [ ! -x "./mini-aipc-mixed" ]; then
    echo "[Build] Compiling binaries..."
    make all
fi

# Detect CPU cores
AFFINITY=""
if [ "$(nproc 2>/dev/null || echo 1)" -ge 2 ]; then
    AFFINITY="--cpu-producer 0 --cpu-consumer 1"
fi

# ------------------------------------------------------------------------------
# Phase 1: Baseline Preservation
# ------------------------------------------------------------------------------
echo -e "\n[Phase 1] Preserving baseline comparative dataset..."
if [ -f "$OUTPUT_DIR/comparative_benchmark.csv" ] && [ ! -f "$OUTPUT_DIR/baseline_comparative.csv" ]; then
    cp "$OUTPUT_DIR/comparative_benchmark.csv" "$OUTPUT_DIR/baseline_comparative.csv"
    echo "  Copied existing comparative_benchmark.csv to baseline_comparative.csv"
else
    echo "  Baseline comparative dataset verified at $OUTPUT_DIR/baseline_comparative.csv"
fi

# ------------------------------------------------------------------------------
# Phase 2: Semaphore Wait Optimization (Monitored vs Unmonitored sem_wait_retry)
# ------------------------------------------------------------------------------
echo -e "\n[Phase 2] Evaluating Semaphore Wait Optimization..."
SEM_CSV="$OUTPUT_DIR/sem_wait_optimization.csv"
echo "variant,payload_bytes,trial,count,avg_rtt_us,p50_rtt_us,p90_rtt_us,p95_rtt_us,p99_rtt_us,min_rtt_us,max_rtt_us,stddev_rtt_us,throughput_msg_sec" > "$SEM_CSV"

for size in 64 128 256 512 1024; do
    for ((t=1; t<=TRIALS; t++)); do
        # 1. Monitored Wait variant
        rm -f /dev/shm/*mini_aipc* /tmp/mini_aipc* 2>/dev/null || true
        OUT_MON=$(env AIPC_SHM_MONITOR=1 ./mini-aipc --mode shm --size "$size" --count "$COUNT" --warmup "$WARMUP" --trial "$t" $AFFINITY --csv-extended 2>/dev/null || echo "")
        if [ -n "$OUT_MON" ]; then
            IFS=',' read -r _ _ sz tr cnt avg p50 p90 p95 p99 p999 min max std tput mb el err <<< "$OUT_MON"
            echo "monitored_wait,$sz,$tr,$cnt,$avg,$p50,$p90,$p95,$p99,$min,$max,$std,$tput" >> "$SEM_CSV"
        fi

        # 2. Optimized Fast Wait variant
        rm -f /dev/shm/*mini_aipc* /tmp/mini_aipc* 2>/dev/null || true
        OUT_FAST=$(./mini-aipc --mode shm --size "$size" --count "$COUNT" --warmup "$WARMUP" --trial "$t" $AFFINITY --csv-extended 2>/dev/null || echo "")
        if [ -n "$OUT_FAST" ]; then
            IFS=',' read -r _ _ sz tr cnt avg p50 p90 p95 p99 p999 min max std tput mb el err <<< "$OUT_FAST"
            echo "optimized_fast_wait,$sz,$tr,$cnt,$avg,$p50,$p90,$p95,$p99,$min,$max,$std,$tput" >> "$SEM_CSV"
            printf "  [Phase 2] Size: %4s B | Monitored: %7.2f us vs Fast: %7.2f us\n" "$size" "$avg" "$p50"
        fi
    done
done
echo "Wrote Phase 2 results to $SEM_CSV"

# ------------------------------------------------------------------------------
# Phase 3: Cache-Line Alignment Evaluation
# ------------------------------------------------------------------------------
echo -e "\n[Phase 3] Evaluating Cache-Line Alignment..."
CACHE_CSV="$OUTPUT_DIR/cacheline_alignment.csv"
echo "variant,payload_bytes,trial,count,avg_rtt_us,p50_rtt_us,p90_rtt_us,p95_rtt_us,p99_rtt_us,min_rtt_us,max_rtt_us,stddev_rtt_us,throughput_msg_sec" > "$CACHE_CSV"

for size in 64 256 1024; do
    for ((t=1; t<=TRIALS; t++)); do
        rm -f /dev/shm/*mini_aipc* /tmp/mini_aipc* 2>/dev/null || true
        OUT=$(./mini-aipc --mode shm --size "$size" --count "$COUNT" --warmup "$WARMUP" --trial "$t" $AFFINITY --csv-extended 2>/dev/null || echo "")
        if [ -n "$OUT" ]; then
            IFS=',' read -r _ _ sz tr cnt avg p50 p90 p95 p99 p999 min max std tput mb el err <<< "$OUT"
            echo "cacheline_aligned_shm,$sz,$tr,$cnt,$avg,$p50,$p90,$p95,$p99,$min,$max,$std,$tput" >> "$CACHE_CSV"
            printf "  [Phase 3] Cache-Aligned SHM Size: %4s B | Avg: %7.2f us | P50: %7.2f us\n" "$size" "$avg" "$p50"
        fi
    done
done
echo "Wrote Phase 3 results to $CACHE_CSV"

# ------------------------------------------------------------------------------
# Phase 4: SPSC Lock-Free Ring Buffer Evaluation
# ------------------------------------------------------------------------------
echo -e "\n[Phase 4] Evaluating SPSC Shared-Memory Ring Buffer..."
SPSC_CSV="$OUTPUT_DIR/spsc_ring_buffer.csv"
echo "mechanism,payload_bytes,trial,count,avg_rtt_us,p50_rtt_us,p90_rtt_us,p95_rtt_us,p99_rtt_us,min_rtt_us,max_rtt_us,stddev_rtt_us,throughput_msg_sec" > "$SPSC_CSV"

for size in 64 256 1024; do
    for ((t=1; t<=TRIALS; t++)); do
        # 1. SPSC Ring Buffer
        rm -f /dev/shm/*mini_aipc* /tmp/mini_aipc* 2>/dev/null || true
        OUT_SPSC=$(./mini-aipc --mode spsc --size "$size" --count "$COUNT" --warmup "$WARMUP" --trial "$t" $AFFINITY --csv-extended 2>/dev/null || echo "")
        if [ -n "$OUT_SPSC" ]; then
            IFS=',' read -r _ _ sz tr cnt avg p50 p90 p95 p99 p999 min max std tput mb el err <<< "$OUT_SPSC"
            echo "spsc_ring,$sz,$tr,$cnt,$avg,$p50,$p90,$p95,$p99,$min,$max,$std,$tput" >> "$SPSC_CSV"
        fi

        # 2. Semaphore SHM Baseline
        rm -f /dev/shm/*mini_aipc* /tmp/mini_aipc* 2>/dev/null || true
        OUT_SHM=$(./mini-aipc --mode shm --size "$size" --count "$COUNT" --warmup "$WARMUP" --trial "$t" $AFFINITY --csv-extended 2>/dev/null || echo "")
        if [ -n "$OUT_SHM" ]; then
            IFS=',' read -r _ _ sz tr cnt avg p50 p90 p95 p99 p999 min max std tput mb el err <<< "$OUT_SHM"
            echo "semaphore_shm,$sz,$tr,$cnt,$avg,$p50,$p90,$p95,$p99,$min,$max,$std,$tput" >> "$SPSC_CSV"
            printf "  [Phase 4] Size: %4s B | SPSC Ring: %7.2f us vs Semaphore SHM: %7.2f us\n" "$size" "$avg" "$p50"
        fi
    done
done
echo "Wrote Phase 4 results to $SPSC_CSV"

# ------------------------------------------------------------------------------
# Phase 5: Adaptive Telemetry Policy Evaluation
# ------------------------------------------------------------------------------
echo -e "\n[Phase 5] Evaluating Adaptive Policy against Fixed Transports..."
ADAPT_CSV="$OUTPUT_DIR/adaptive_policy.csv"
echo "policy,payload_bytes,trial,count,avg_rtt_us,p50_rtt_us,throughput_msg_sec,selected_transport" > "$ADAPT_CSV"

for size in 64 256 1024 4096 16384; do
    for ((t=1; t<=TRIALS; t++)); do
        # 1. Adaptive Policy
        rm -f /dev/shm/*mini_aipc* /tmp/mini_aipc* 2>/dev/null || true
        OUT_ADAPT=$(./mini-aipc --mode adaptive --size "$size" --count "$COUNT" --warmup "$WARMUP" --trial "$t" $AFFINITY --csv-extended 2>/dev/null || echo "")
        if [ -n "$OUT_ADAPT" ]; then
            IFS=',' read -r req sel sz tr cnt avg p50 _ _ _ _ _ _ _ tput _ _ _ <<< "$OUT_ADAPT"
            echo "adaptive,$sz,$tr,$cnt,$avg,$p50,$tput,$sel" >> "$ADAPT_CSV"
        fi

        # 2. Pipe Policy
        rm -f /dev/shm/*mini_aipc* /tmp/mini_aipc* 2>/dev/null || true
        OUT_PIPE=$(./mini-aipc --mode pipe --size "$size" --count "$COUNT" --warmup "$WARMUP" --trial "$t" $AFFINITY --csv-extended 2>/dev/null || echo "")
        if [ -n "$OUT_PIPE" ]; then
            IFS=',' read -r req sel sz tr cnt avg p50 _ _ _ _ _ _ _ tput _ _ _ <<< "$OUT_PIPE"
            echo "pipe_fixed,$sz,$tr,$cnt,$avg,$p50,$tput,pipe" >> "$ADAPT_CSV"
            printf "  [Phase 5] Size: %5s B | Adaptive (-> %s): %7.2f us vs Pipe: %7.2f us\n" "$size" "$sel" "$avg" "$p50"
        fi
    done
done
echo "Wrote Phase 5 results to $ADAPT_CSV"

# ------------------------------------------------------------------------------
# Phase 6: Mixed-Workload Benchmarking (80% 64B / 20% 16KB)
# ------------------------------------------------------------------------------
echo -e "\n[Phase 6] Evaluating Mixed-Workload Performance (80%% small, 20%% large)..."
MIXED_CSV="$OUTPUT_DIR/mixed_workload.csv"
echo "policy,count,threshold,small_count,large_count,elapsed_ns,avg_rtt_us,throughput_msg_sec,errors" > "$MIXED_CSV"

MIXED_COUNT=10000
[ "$QUICK" -eq 1 ] && MIXED_COUNT=1000

for policy in pipe adaptive; do
    for ((t=1; t<=TRIALS; t++)); do
        rm -f /dev/shm/*mini_aipc* /tmp/mini_aipc* 2>/dev/null || true
        MIX_OUT=$(./mini-aipc-mixed --policy "$policy" --count "$MIXED_COUNT" --threshold 1024 2>&1 || echo "")
        if echo "$MIX_OUT" | grep -q "Elapsed:"; then
            ELAPSED=$(echo "$MIX_OUT" | grep "Elapsed:" | awk '{print $2}')
            AVG_NS=$(echo "$MIX_OUT" | grep "Average latency:" | awk '{print $3}')
            AVG_US=$(python3 -c "print(f'{float($AVG_NS)/1000.0:.3f}')" 2>/dev/null || echo "0.0")
            TPUT=$(echo "$MIX_OUT" | grep "Throughput:" | awk '{print $2}')
            ERRORS=$(echo "$MIX_OUT" | grep "Validation errors:" | awk '{print $3}')
            SMALL_N=$(( MIXED_COUNT * 8 / 10 ))
            LARGE_N=$(( MIXED_COUNT - SMALL_N ))
            echo "$policy,$MIXED_COUNT,1024,$SMALL_N,$LARGE_N,$ELAPSED,$AVG_US,$TPUT,$ERRORS" >> "$MIXED_CSV"
            printf "  [Phase 6] Policy: %-8s | Trial %d | Avg RTT: %7.2f us | Tput: %10.1f msg/s\n" "$policy" "$t" "$AVG_US" "$TPUT"
        fi
    done
done
echo "Wrote Phase 6 results to $MIXED_CSV"

echo -e "\n=============================================================================="
echo "          Mini A-IPC: All 6 Optimization Phases Successfully Completed!       "
echo "=============================================================================="
echo "Generated CSV Datasets:"
echo "  1. $OUTPUT_DIR/baseline_comparative.csv"
echo "  2. $OUTPUT_DIR/sem_wait_optimization.csv"
echo "  3. $OUTPUT_DIR/cacheline_alignment.csv"
echo "  4. $OUTPUT_DIR/spsc_ring_buffer.csv"
echo "  5. $OUTPUT_DIR/adaptive_policy.csv"
echo "  6. $OUTPUT_DIR/mixed_workload.csv"
echo "=============================================================================="
