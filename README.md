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


## Kernel-module implementation (new)

A separate loadable kernel module is now included at `kernel/aipc_module.c`. It exposes a bounded shared ring buffer as `/dev/aipc` with blocking `read`/`write`, wait queues, a mutex, and `poll`. Build the client and module with:

```bash
make
make kernel-module
```

Then load/test/unload on Linux with matching kernel headers:

```bash
sudo insmod kernel/aipc_module.ko
make kernel-test
sudo ITERATIONS=10 ./tests/kernel/test_load_unload.sh
python3 ./bench/benchmark_kernel_mailbox.py --trials 7 --messages 1000
sudo rmmod aipc_module
```

See [`docs/kernel-module.md`](docs/kernel-module.md) for architecture, setup, limitations, and validation steps. The `aipc_read()` copy-fault data-loss issue is addressed by committing ring-buffer consumption only after `copy_to_user()` succeeds. The kernel tests now cover independent producer/consumer processes and full/empty nonblocking behavior, and `tests/kernel/test_load_unload.sh` checks repeated load/unload cycles. `bench/benchmark_kernel_mailbox.py` records exploratory throughput CSVs, not a matched comparison. The module is a separate kernel transport prototype; it does not yet replace the existing user-space adaptive selector or implement kernel-space adaptive selection.
