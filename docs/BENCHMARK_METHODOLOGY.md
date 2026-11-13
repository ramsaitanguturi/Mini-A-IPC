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
   - Prior to each trial run, all temporary shared memory segments (`/dev/shm/*mini_aipc*`) and named FIFO nodes (`/tmp/mini_aipc*`) are purged to prevent resource leakage or descriptor reuse.

---

## 2. Statistical Analysis & Percentile Calculations

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

---

## 3. System Environment & Virtualization Disclosure

All comparative benchmarks were collected in the following target execution environment:

- **Operating System:** Fedora Linux 45 (Workstation Edition)
- **Linux Kernel:** 7.2.15-300.fc45.x86_64 / 7.3.3
- **Compiler:** GCC 16.2.1 (flags: `-std=c11 -O2 -Wall -Wextra -pthread -lrt -lm`)
- **CPU Architecture:** Intel Core 7 240H (x86_64, 4 visible virtual CPUs)
- **Virtualization:** KVM / VirtualBox hypervisor guest VM

### 3.1 Impact of Virtualization on IPC Latency
1. **Hypervisor vCPU Scheduling:**
   - In a virtual machine, when a guest thread blocks on a semaphore or pipe wait-queue, the guest Linux kernel yields the virtual CPU. The host OS hypervisor may deschedule the vCPU thread.
   - When the partner thread posts or writes, an inter-processor interrupt (IPI) must traverse the hypervisor layer, causing hypervisor VM-exits and reinjections.
   - This produces a **context-switch latency floor of ~95 to 120 microseconds** on this virtualized environment.
2. **Trial-to-Trial Jitter:**
   - Background tasks on the host operating system can cause transient vCPU pauses, explaining occasional trial spikes (such as Trial 2 and Trial 6) where all synchronizing mechanisms showed elevated latencies.
