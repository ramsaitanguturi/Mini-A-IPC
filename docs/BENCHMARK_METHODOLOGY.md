# Mini-A-IPC: Unified Benchmarking Methodology and Environment Specification

## 1. Experimental Methodology

The Mini-A-IPC benchmark suite implements a rigorous, scientifically controlled evaluation protocol designed to measure inter-process communication performance under realistic operating system workloads.

### 1.1 Trial Protocol
- **Trials per Configuration:** 7 independent trials per mechanism and payload size.
- **Measured Exchanges:** 10,000 request-response round-trips per trial (70,000 measured transactions per data point).
- **Warm-Up Phase:** 500 untimed round-trips executed immediately prior to timing to populate page tables, warm CPU caches, and eliminate cold-start overhead.
- **Payload Sizes:** 64 B, 256 B, 1024 B (1 KB), 4096 B (4 KB), 16384 B (16 KB), 65536 B (64 KB), and 262144 B (256 KB).

### 1.2 Mitigation of Experimental Bias
1. **Randomized Trial Execution:**
   - To eliminate thermal throttling bias and cache retention artifacts, the execution order of IPC mechanisms is dynamically shuffled prior to each of the 7 trial blocks using a Fisher-Yates shuffle.
2. **Deterministic CPU Affinity:**
   - Linux task migration between CPU cores introduces non-deterministic cache invalidation. Mini-A-IPC enforces deterministic CPU affinity via `sched_setaffinity`:
     - Producer Process pinned to **CPU Core 0**
     - Consumer Process pinned to **CPU Core 1**
3. **Artifact Cleanup:**
   - Prior to each trial run, all temporary shared memory segments (`/dev/shm/*mini_aipc*`), named FIFO nodes (`/tmp/mini_aipc*`), POSIX message queues (`/mini_aipc*`), and Unix domain socket files (`/tmp/mini_aipc*.sock`) are purged to prevent resource leakage or descriptor reuse.

---

## 2. Statistical Rigor & Metric Definitions

To prevent loss of tail-latency fidelity, Mini-A-IPC records the high-resolution round-trip latency (in nanoseconds) of every single measured transaction.

### 2.1 Calculated Metrics
- **Mean (Average) Round-Trip Time:**
  $$\mu = \frac{1}{N} \sum_{i=1}^N L_i$$
- **Sample Standard Deviation:**
  $$s = \sqrt{\frac{1}{N-1} \sum_{i=1}^N (L_i - \mu)^2}$$
- **P50 (Conventional Median):**
  - For odd $N$: Element at index $\lfloor N/2 \rfloor$.
  - For even $N$: Mean of elements at $N/2 - 1$ and $N/2$.
- **Tail Percentiles (P90, P95, P99, P99.9):**
  - Calculated using the nearest-rank formula on the sorted sample array:
    $$k = \lceil \frac{P}{100} \cdot N \rceil - 1$$
- **Throughput:**
  $$\text{Throughput (msg/s)} = \frac{N}{\Delta t_{\text{sec}}}$$
  $$\text{Throughput (MB/s)} = \frac{N \times \text{payload\_bytes}}{1024 \times 1024 \times \Delta t_{\text{sec}}}$$
  $$\text{Wire Throughput (MB/s)} = \frac{2 \times N \times \text{payload\_bytes}}{1024 \times 1024 \times \Delta t_{\text{sec}}}$$
- **95% Confidence Intervals:**
  $$\text{CI}_{95\%} = \bar{x} \pm t_{0.025, \text{df}} \cdot \frac{s}{\sqrt{N}}$$
- **Non-Parametric Hypothesis Testing:**
  Pairwise differences between mechanisms are verified using the **Wilcoxon Signed-Rank Test** to avoid assuming normal distribution on skewed tail latencies.

### 2.2 Resource Profiling (`getrusage`)
- **User CPU Time ($t_{\text{user}}$)** and **System CPU Time ($t_{\text{sys}}$)**
- **Voluntary Context Switches (`ru_nvcsw`)**: Yields during blocking I/O or semaphore synchronization.
- **Involuntary Context Switches (`ru_nivcsw`)**: Preemptions caused by time-slice expiration.
- **Maximum Resident Set Size (`ru_maxrss`)**: High-water memory mark in kilobytes.
- **Major and Minor Page Faults (`ru_majflt`, `ru_minflt`)**.

---

## 3. Environmental Separation and Hardware Provenance Disclosure

Mini-A-IPC strictly enforces dataset isolation across different execution environments. Under no circumstances are measurements from distinct operating system environments aggregated together.

### Environment 1: Native Linux / Fedora 45 (Authoritative Unified Dataset)
- **Dataset Path**: `results/unified/raw/all_results.csv`, `results/unified/processed/aggregated_results.csv`
- **Host CPU**: Intel Core 7 240H (x86_64, 4 vCPUs)
- **Kernel Version**: Linux 7.3.3-300.fc45.x86_64
- **Toolchain**: GCC 16.2.1, GNU C Library 2.41
- **Tested Mechanisms**: All 6 userspace IPC mechanisms + Custom Kernel Mailbox (`/dev/aipc`) + Adaptive Policy.

### Environment 2: Ubuntu 26.04 on WSL2 (Comparative Host Dataset)
- **Dataset Path**: `results/comparative_benchmark.csv`
- **Host CPU**: AMD Ryzen 7 8845HS (16 vCPUs)
- **Kernel Version**: Linux 6.6.87.2-microsoft-standard-WSL2
- **Toolchain**: GCC 13.3.0
- **Tested Mechanisms**: Pipe, FIFO, POSIX SHM, System V MQ, POSIX MQ, Unix Domain Sockets (Payloads: 64 B to 1024 B).

### Environment 3: Windows 11 / MSYS2 POSIX Emulation (Host Validation Environment)
- **Dataset Path**: `results/msys2_historical/`
- **Host CPU**: AMD Ryzen 7 8845HS (16 vCPUs)
- **OS**: Windows 11 Home (64-bit)
- **POSIX Emulation**: MSYS2 / Cygwin API layer (GCC 13.3.0, Make 4.4.1)
- **Supported Transports**: Pipe, FIFO, POSIX SHM, POSIX MQ, Unix Domain Sockets, SPSC Ring Buffer.
- **Subsystem Blockers**: System V IPC syscalls (`msgget`) return `ENOSYS` unless background `cygserver` daemon is running. Linux kernel module (`aipc.ko`) cannot be loaded due to absence of a native Linux kernel.
