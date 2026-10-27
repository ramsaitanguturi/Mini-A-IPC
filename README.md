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
./bench/run_benchmarks.sh
```

Optional settings: `COUNT=20000 TRIALS=7 ./bench/run_benchmarks.sh`. The script records actual measurements in `results/benchmark.csv`. It skips shared-memory tests above the mailbox capacity.
