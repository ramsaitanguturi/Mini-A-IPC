# Experimental methodology and paper alignment

## Source paper reviewed

Danyliuk, I. M., "Classical Interprocess Communication Mechanisms in Linux OS: Review and Latency Analysis for HPC Scenarios", SWorldJournal, Issue 37 / Part 2 (2026), DOI: 10.30888/2663-5712.2026-37-02-028.

The attached paper's scope is a review and latency analysis of five classical Linux IPC mechanisms: anonymous pipes, FIFOs, System V and POSIX message queues, shared memory with semaphores, and Unix domain sockets. Its reported small-message range is 64–1024 bytes.

## Methodology reported by the paper

On pages 3–4, the paper describes a producer-consumer pattern: one process writes a fixed-size message and the other reads it and returns an acknowledgement. It identifies average latency, P99/tail latency, and system-call overhead as important metrics. It also states that accurate measurements should pin processes to CPU cores and warm caches; the discussion mentions disabling speculative-execution mitigations where applicable. Table 1 reports approximate 64-byte latencies and syscall counts, including pipe ~2 µs, Unix domain socket ~2 µs, and shared memory ~0.5–1 µs, with a footnote that the shared-memory syscall count excludes futex/semaphore synchronization cost.

Those table values are literature summaries cited by the paper, not values produced by this project and not guaranteed targets for WSL.

## What this project measures

The implementation uses one parent and one child per run and request/response exchanges:
- Pipe mode uses two anonymous pipes.
- Shared-memory mode uses POSIX shared memory and process-shared semaphores, with a 1024-byte mailbox.
- Adaptive mode uses a payload-size threshold; calibration measures pipe and shared-memory average round-trip latency at 64, 128, 256, 512 and 1024 bytes.
- Mixed-workload experiment generates one deterministic shuffled sequence of 80% 64-byte messages and 20% 16384-byte messages. The fixed-pipe and adaptive policies each process the same sequence order.

## Reproducibility commands

```bash
make clean && make
make test
COUNT=10000 TRIALS=5 bash ./bench/run_experiments.sh
```

Outputs:
- `results/benchmark.csv`: per-trial raw measurements.
- `results/calibration.csv`: median latency by payload size and the selected threshold.
- `results/threshold.txt`: calibrated threshold in bytes.
- `results/mixed_workload.csv`: fixed-pipe versus adaptive interleaved-sequence evaluation.

## Reproduction boundary

Reproduced at a conceptual level:
1. Parent/child producer-consumer exchange with acknowledgement.
2. Small-message latency comparison between pipe and shared-memory synchronization.
3. Repeated measurements over the 64–1024-byte range.
4. An additional workload-aware policy experiment.

Not reproduced:
1. FIFO, System V/POSIX message queues, or Unix domain sockets.
2. CPU affinity/pinning, explicit mitigation control, P99/P99.9 tail-latency collection, or syscall counting.
3. The paper's hardware/software configuration and its cited published values.
4. P99/P99.9 tail-latency collection, CPU affinity/pinning, or syscall counting.
5. Futex synchronization specifically; this implementation uses POSIX semaphores.

The attached paper is a classical IPC review, not the separate A-IPC adaptive-ring-buffer paper. Do not cite its reported values as results from the A-IPC paper. Record the exact WSL kernel, CPU, compiler, and run settings in the final report. Measurements must be collected on the user's Ubuntu WSL installation; measurements from another environment must be labeled separately.


## Calibration versus evaluation

`results/benchmark.csv` includes a `phase` column:
- `calibration`: fixed pipe and fixed shared-memory measurements at 64, 128, 256, 512 and 1024 bytes. Only these rows determine the threshold.
- `baseline_default_threshold`: adaptive runs made with the default threshold, recorded for reference but excluded from calibration.

`results/mixed_workload.csv` is a separate evaluation phase. The C benchmark creates one deterministic shuffled sequence containing 80% 64-byte messages and 20% 16384-byte messages. It uses the same seed and count for the fixed-pipe and adaptive policy runs. The adaptive policy selects a transport separately for each message using the calibrated threshold. This is an interleaved sequence, not two batches summed together.

## Failure-path tests

`make test` includes fault injection through `AIPC_TEST_CHILD_EXIT=pipe` and `AIPC_TEST_CHILD_EXIT=shm`. It verifies that the parent returns an error rather than being killed by `SIGPIPE` or waiting indefinitely on an unposted semaphore. These tests cover selected child-exit paths, not every possible failure mode.

## Environment capture

Run:

```bash
bash ./bench/capture_environment.sh
```

This writes `results/environment.txt` with OS release, WSL marker/version where available, kernel, CPU, GCC version, compiler flags, and experiment settings. Run it on the target Ubuntu WSL environment before collecting final measurements. Do not substitute environment details from another machine or container.
