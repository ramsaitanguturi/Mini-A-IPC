# Experimental Methodology and Comparative IPC Analysis

## 1. Source Paper Overview

**Reference**: Danyliuk, I. M., *"Classical Interprocess Communication Mechanisms in Linux OS: Review and Latency Analysis for HPC Scenarios"*, SWorldJournal, Issue 37 / Part 2 (2026), DOI: 10.30888/2663-5712.2026-37-02-028.

### Scope and Paper Methodology
The paper reviews and evaluates classical Linux IPC mechanisms for high-performance computing (HPC) environments where process-to-process message passing latency is a primary bottleneck. It assesses six primary mechanisms across small payload sizes (64 to 1024 bytes):
1. Anonymous Pipes (`pipe`)
2. Named Pipes (`FIFO`)
3. System V Message Queues (`msgget`, `msgsnd`, `msgrcv`)
4. POSIX Message Queues (`mq_open`, `mq_send`, `mq_receive`)
5. POSIX Shared Memory with Synchronization (`shm_open`, `mmap`, semaphores/futex)
6. Unix Domain Sockets (`AF_UNIX`, `SOCK_STREAM`)

The paper highlights the following key experimental requirements for high-performance IPC benchmarking:
- **Producer-Consumer Workload**: Request-response communication pattern (ping-pong) measuring round-trip exchange latency.
- **Latency Distribution**: Recording not just average latency, but tail latency percentiles (P99, P99.9) and minimum/maximum bounds.
- **System Call Overhead**: Quantifying the number and cost of kernel transitions per message exchange.
- **Processor Affinity**: Binding communicating processes to dedicated CPU cores to minimize cache invalidation and migration overhead.
- **Cache Warm-up**: Pre-populating cache and branch predictors before measurement.

> [!IMPORTANT]
> **Literature Citations vs. Local Experimental Measurements**:
> Table 1 in the paper summarizes published values from literature (e.g. ~2 µs for pipes and Unix sockets, ~0.5–1 µs for uncontended shared memory) on bare-metal Linux servers with speculative-execution mitigations disabled.
> Mini A-IPC **does not copy or fabricate** these values. All results in `results/comparative_benchmark.csv` and `results/syscall_benchmark.csv` represent genuinely measured, empirical performance on the user's specific Linux / WSL2 environment with standard kernel mitigations active.

---

## 2. Experimental Methodology in Mini A-IPC

### A. Measurement Protocol
1. **Separation of Setup from Steady-State Communication**:
   Process creation (`fork()`), file descriptor opening, shared memory allocation (`ftruncate`/`mmap`), and socket binding/connecting are performed **before** the measurement loop. Only the iterative request-response exchanges are timed.
2. **Monotonic High-Resolution Timing**:
   Timestamps are obtained using `clock_gettime(CLOCK_MONOTONIC, &ts)`, which provides nanosecond-precision wall-clock time unaffected by system clock adjustments (`NTP`).
3. **Round-Trip Time (RTT)**:
   The primary metric measured is request-response round-trip latency (`\text{RTT}`). One-way latency can be approximated as `\text{RTT} / 2` under symmetric send/receive cost assumptions.
4. **Individual Sample Recording**:
   For every exchange `i \in [0, N-1]`, the duration `\Delta t_i = t_{end,i} - t_{start,i}` is recorded into a dynamically allocated array. Percentile calculations are derived from sorted empirical samples, not averages of trial averages.
5. **Warm-up Phase**:
   An initial untimed batch (e.g., 500 exchanges) is executed immediately prior to measurement to warm CPU caches, page tables, and branch predictors.
6. **Processor Affinity**:
   Producer and consumer processes are pinned to CPU cores 0 and 1 respectively using `sched_setaffinity()`.
7. **System Security**:
   Kernel security mitigations (Spectre, Meltdown, Retpolines) remain active, reflecting real-world production deployments.

---

## 3. Metric Definitions

| Metric | Formula / Calculation | Significance in HPC Scenarios |
|---|---|---|
| **Average Latency (RTT)** | `\frac{\sum_{i=1}^N \Delta t_i}{N}` | Overall baseline communication delay. |
| **Median Latency (P50)** | Sample at rank `\lfloor 0.50 \times N \rfloor` | Typical latency unaffected by infrequent extreme spikes. |
| **99th Percentile (P99)** | Sample at rank `\lfloor 0.99 \times N \rfloor` | Tail latency experienced by 1 in 100 messages; critical for SLA guarantees. |
| **99.9th Percentile (P99.9)**| Sample at rank `\lfloor 0.999 \times N \rfloor` | Extreme tail latency, reflecting scheduler preemption or interrupt interference. |
| **Minimum Latency (Min)** | `\min_i (\Delta t_i)` | Hardware limit when caches are warm and no context switches intervene. |
| **Maximum Latency (Max)** | `\max_i (\Delta t_i)` | Worst-case round-trip delay observed during the trial. |
| **Throughput** | `\frac{N}{\text{Total Elapsed Time}}` (msg/s) | Message-processing capacity under continuous load. |

---

## 4. System-Call Profiling Methodology

System-call overhead is profiled using Linux `strace -f -c`:
```bash
strace -f -c -o /tmp/strace_<mode>.log ./mini-aipc --mode <mode> --size 64 --count 100
```

### Distinguishing Communication vs. Lifecycle System Calls
Mini A-IPC explicitly separates system calls into two categories:
1. **Communication-Path System Calls**:
   System calls invoked iteratively inside the exchange loop to transfer data or synchronize:
   - **Pipes & FIFOs**: `read` (1 per process = 2 per RTT), `write` (1 per process = 2 per RTT) `\rightarrow` **4 system calls per exchange**.
   - **System V Message Queues**: `msgsnd` (2 per RTT), `msgrcv` (2 per RTT) `\rightarrow` **4 system calls per exchange**.
   - **POSIX Message Queues**: `mq_timedsend` (2 per RTT), `mq_timedreceive` (2 per RTT) `\rightarrow` **4 system calls per exchange**.
   - **Unix Domain Sockets**: `sendto`/`send` (2 per RTT), `recvfrom`/`recv` (2 per RTT) `\rightarrow` **4 system calls per exchange**.
   - **Shared Memory**: Synchronization via POSIX semaphores invokes the `futex` system call **only on lock contention or blocking**. Zero kernel calls are required for the memory data copy itself.
2. **Setup and Cleanup System Calls**:
   Process creation (`clone`), descriptor setup (`pipe2`, `mknodat`, `msgget`, `mq_open`, `socket`, `bind`, `listen`, `connect`, `accept`), memory mapping (`mmap`, `ftruncate`), child reaping (`wait4`), and resource destruction (`unlink`, `msgctl`, `mq_unlink`, `close`).

These are tracked in `results/syscall_benchmark.csv`:
- `comm_syscalls_per_exchange`: Communication-path syscalls per exchange (typically 4.0 for stream/queue mechanisms).
- `total_syscalls_per_exchange`: Total process syscall count (including setup, teardown, and dynamic linker calls) divided by count.

> [!NOTE]
> `strace` introduces substantial ptrace interception overhead. Consequently, system-call counts are measured separately in dedicated profiling runs and are never combined with uncontended native latency benchmarks.

---

## 5. CSV Output Schema

### `results/comparative_benchmark.csv`
Records raw latency and throughput metrics across all mechanisms, payload sizes, and trials:
- `mechanism`: Name of the IPC mechanism (`pipe`, `fifo`, `sysv`, `posix`, `shm`, `uds`).
- `payload_bytes`: Message payload size in bytes (64, 128, 256, 512, 1024).
- `trial`: Trial index (1 to `TRIALS`).
- `count`: Number of message exchanges per trial (e.g. 10000).
- `avg_rtt_us`: Arithmetic mean round-trip latency in microseconds.
- `p50_rtt_us`: Median (50th percentile) round-trip latency in microseconds.
- `p99_rtt_us`: 99th percentile round-trip latency in microseconds.
- `p999_rtt_us`: 99.9th percentile round-trip latency in microseconds.
- `min_rtt_us`: Minimum observed round-trip latency in microseconds.
- `max_rtt_us`: Maximum observed round-trip latency in microseconds.
- `throughput_msg_sec`: Throughput in round-trip exchanges per second.

### `results/syscall_benchmark.csv`
Records system-call counts and categorization:
- `mechanism`: IPC transport name.
- `payload_bytes`: Payload size used (64 bytes).
- `exchanges`: Number of exchanges profiled (100).
- `total_syscalls`: Total system calls intercepted during the process lifecycle.
- `total_syscalls_per_exchange`: `total_syscalls / exchanges`.
- `comm_syscalls`: System calls executed directly in the communication path.
- `comm_syscalls_per_exchange`: `comm_syscalls / exchanges` (e.g. 4.00).
- `setup_cleanup_syscalls`: Non-communication system calls (`total - comm`).
- `relevant_syscall_details`: Breakdown string listing specific system call counts.

---

## 6. How to Run the Experiments

```bash
# 1. Clean and compile
make clean && make

# 2. Run automated correctness tests
make test

# 3. Capture system and hardware environment
bash ./bench/capture_environment.sh

# 4. Run the full comparative benchmark
# (Configurable via COUNT, TRIALS, WARMUP, CPU_PRODUCER, CPU_CONSUMER)
COUNT=10000 TRIALS=5 WARMUP=500 bash ./bench/run_comparative.sh
```
