# Mini A-IPC

A small C/Linux IPC experiment for Ubuntu on WSL. It supports four independent IPC mechanisms:

1. **Anonymous Pipes** (`--mode pipe`)
2. **Named Pipes / FIFOs** (`--mode fifo` and standalone `bin/ipc_fifo`)
3. **POSIX Shared Memory** (`--mode shm`)
4. **Kernel Character Device Mailbox** (`/dev/aipc` + `aipc-client`)

It compares parent-child request/response exchanges using anonymous pipes, named pipes (FIFOs), and a bounded POSIX shared-memory mailbox, with a payload-size selector for pipe and shared memory.

## Build

```bash
make
```

## Run

```bash
# Multi-mode CLI
./mini-aipc --mode pipe --size 64 --count 10000
./mini-aipc --mode fifo --size 64 --count 10000
./mini-aipc --mode shm --size 64 --count 10000
./mini-aipc --mode adaptive --size 16384 --count 10000

# Standalone FIFO executable
./bin/ipc_fifo
./bin/ipc_fifo --size 128 --count 1000
```

The shared-memory mailbox supports payloads up to 1024 bytes. Adaptive mode selects shared memory for payloads up to 1024 bytes and pipes for larger payloads. FIFO operates as an independent transport.

## Architecture

```
                               +-----------------------------+
                               |     Mini A-IPC Suite        |
                               +-----------------------------+
                                              |
                +-----------------------------+-----------------------------+
                |                             |                             |
                v                             v                             v
     +---------------------+       +---------------------+       +---------------------+
     |   Anonymous Pipes   |       |  Named Pipes (FIFO) |       | POSIX Shared Memory |
     |    (ipc_pipe.c)     |       |    (ipc_fifo.c)     |       |     (ipc_shm.c)     |
     +---------------------+       +---------------------+       +---------------------+
                ^                             |                             ^
                |                             v                             |
                |               +---------------------------+               |
                |               |   Standalone Executable   |               |
                |               |       bin/ipc_fifo        |               |
                |               +---------------------------+               |
                |                                                           |
                +----------------------+             +----------------------+
                                       |             |
                                       v             v
                                 +-------------------------+
                                 |  Adaptive IPC Selector  |
                                 |  (size <= threshold)    |
                                 +-------------------------+

                          Independent Kernel Module Transport:
                               +-------------------------+
                               |   Kernel Mailbox LKM    |
                               |  /dev/aipc (char dev)   |
                               +-------------------------+
```

## FIFO (Named Pipe) IPC

### What is a FIFO?
A FIFO (First-In, First-Out) is a unidirectional IPC channel that transfers bytes between processes in sequential order.

### Why is it called a named pipe?
Unlike standard anonymous pipes that exist only in memory without names, a FIFO is associated with a specific file path on the filesystem (e.g. `/tmp/mini_aipc_req_<pid>.fifo`). Any process that knows this filename and possesses appropriate permissions can access it using standard file operations (`open`, `read`, `write`, `close`).

### Difference between anonymous pipes and FIFOs
- **Anonymous Pipes (`pipe`):** Ephemeral and restricted to processes with shared ancestry (e.g. parent and child processes inheriting descriptors through `fork()`). They vanish as soon as descriptors are closed.
- **Named Pipes (`mkfifo`):** Visible in the filesystem directory structure. Any unrelated processes can open them by pathname. They persist in the filesystem until explicitly removed via `unlink()`.

### How `mkfifo()` works
The `mkfifo()` system call creates a filesystem node of type `S_IFIFO` with specified permission bits (e.g. `0666`). It creates the directory entry and inode without consuming data blocks on the disk; message data flows strictly through kernel memory buffers.

### Parent-child communication using two FIFO files
Because a FIFO is unidirectional, bidirectional request-response communication requires two distinct FIFO files to prevent race conditions:
1. `req_fifo`: Parent writes requests; child reads requests.
2. `resp_fifo`: Child writes responses; parent reads responses.

To avoid deadlock, both processes follow a strict rendezvous sequence:
- Child opens `req_fifo` for reading (`O_RDONLY`), then `resp_fifo` for writing (`O_WRONLY`).
- Parent opens `req_fifo` for writing (`O_WRONLY`), then `resp_fifo` for reading (`O_RDONLY`).
- Both rendezvous on `req_fifo` first, then on `resp_fifo` second, eliminating deadlock risk.
- Upon completion or failure, the parent unlinks both FIFO files.

### Advantages and limitations
- **Advantages:** Standard file descriptor semantics, inspectable from shell commands (`cat`, `echo`), accessible across unrelated processes, automatic synchronization via blocking `open()`.
- **Limitations:** Requires filesystem cleanup (`unlink()`), incurs kernel context switching and data copy overhead compared to zero-copy shared memory.
- **Selector status:** FIFO is implemented as an independent IPC mechanism and standalone utility (`bin/ipc_fifo`); the dual-transport adaptive selector focuses on shared memory vs. anonymous pipes. Detailed explanation and viva questions are available in [`docs/FIFO_EXPLANATION.md`](docs/FIFO_EXPLANATION.md).

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
