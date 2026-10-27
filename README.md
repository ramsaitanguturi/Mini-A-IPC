# Mini A-IPC

A small C/Linux IPC experiment for Ubuntu on WSL. It compares parent-child request/response exchanges using anonymous pipes and a bounded POSIX shared-memory mailbox, then adds a payload-size selector.

## Build

```bash
make
```

## Run

```bash
./mini-aipc --mode pipe --size 64 --count 10000
./mini-aipc --mode shm --size 64 --count 10000
./mini-aipc --mode adaptive --size 16384 --count 10000
```

The shared-memory mailbox supports payloads up to 1024 bytes. Adaptive mode selects shared memory for payloads up to 1024 bytes and pipes for larger payloads.

## Important limitation

This is a teaching implementation, not a full reproduction of the A-IPC paper. The paper's SPSC ring buffer, atomic memory-ordering design, adaptive spin/park controller, UNIX-domain socket transport, and full experimental procedure are not implemented here. Measurements are local to the user's WSL environment and must not be presented as the paper's results.

## Repeatable benchmark CSV

```bash
bash ./bench/run_benchmarks.sh
```

Optional settings: `COUNT=20000 TRIALS=7 bash ./bench/run_benchmarks.sh`. The script records actual measurements in `results/benchmark.csv`. It skips shared-memory tests above the mailbox capacity.


## Automated correctness tests

```bash
make test
```

Tests cover pipe and shared-memory round trips, adaptive routing, oversized payloads, invalid arguments, unexpected child exits, and independent shared-memory payload validation in the mixed benchmark.

## Calibration and interleaved mixed-workload experiment

```bash
COUNT=10000 TRIALS=5 bash ./bench/run_experiments.sh
```

The script creates `results/benchmark.csv`, `results/calibration.csv`, `results/threshold.txt`, and `results/mixed_workload.csv`. Calibration uses fixed pipe and shared-memory runs to choose a threshold; default-threshold adaptive rows are labeled as baselines and are excluded from calibration. Evaluation then runs a single deterministic, shuffled sequence containing 80% 64-byte messages and 20% 16-KiB messages through fixed-pipe and adaptive policies. Both policies use the same sequence order.

The mixed shared-memory consumer independently validates each request payload against the expected sequence bytes before acknowledging it, and the parent validates the returned response.

Capture the actual target environment before final runs:

```bash
bash ./bench/capture_environment.sh
```

## Paper methodology note

See `docs/experiment.md` for a source-grounded account of the attached Danyliuk (2026) paper's methodology and the exact reproduction boundaries. This implementation does not pin CPU cores or collect P99/system-call counts.

