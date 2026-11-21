# Mini-A-IPC: Quantitative Claim Verification Document

This document verifies every quantitative measurement, table row, latency percentile, throughput number, system call count, and benchmark parameter reported in the IEEE research paper against the underlying repository CSV files.

---

## 1. Primary Round-Trip Latency Claims (Fedora 45 Linux)

Dataset: `results/unified/processed/statistical_summary.csv`  
Environment: Intel Core 7 240H, Linux 7.3.3-300.fc45.x86_64, GCC 16.2.1, 7 Trials, 10,000 Messages/Trial.

| Payload Size | Mechanism | Paper Claimed Mean RTT ($\mu\text{s}$) | CSV Exact Value (`mean_avg_rtt_us`) | Verification |
|---|---|---|---|---|
| **64 B** | Anonymous Pipe | 399.25 | 399.247 | **MATCH** |
| **64 B** | Named FIFO | 464.27 | 464.273 | **MATCH** |
| **64 B** | System V MQ | 359.59 | 359.588 | **MATCH** |
| **64 B** | POSIX MQ | 499.72 | 499.723 | **MATCH** |
| **64 B** | POSIX SHM | **286.87** | **286.871** | **MATCH** (Lowest userspace RTT) |
| **64 B** | Unix Domain Socket | 618.33 | 618.329 | **MATCH** |
| **64 B** | Kernel Mailbox | **3.29** (P50: 0.79) | 3.289 (mean_p50: 0.789) | **MATCH** |
| **64 B** | Adaptive Policy | 439.66 | 439.659 | **MATCH** (Routed to SHM) |
| **256 B** | Anonymous Pipe | 344.57 | 344.574 | **MATCH** |
| **256 B** | Named FIFO | 456.39 | 456.386 | **MATCH** |
| **256 B** | System V MQ | 395.60 | 395.597 | **MATCH** |
| **256 B** | POSIX MQ | 767.24 | 767.243 | **MATCH** |
| **256 B** | POSIX SHM | **320.35** | **320.346** | **MATCH** (Lowest userspace RTT) |
| **256 B** | Unix Domain Socket | 619.67 | 619.667 | **MATCH** |
| **256 B** | Kernel Mailbox | **2.95** (P50: 0.77) | 2.947 (mean_p50: 0.771) | **MATCH** |
| **256 B** | Adaptive Policy | 353.13 | 353.125 | **MATCH** (Routed to SHM) |
| **1,024 B** | Anonymous Pipe | **278.76** | **278.756** | **MATCH** (Lowest userspace RTT) |
| **1,024 B** | Named FIFO | 619.56 | 619.563 | **MATCH** |
| **1,024 B** | System V MQ | 317.58 | 317.576 | **MATCH** |
| **1,024 B** | POSIX MQ | 477.91 | 477.912 | **MATCH** |
| **1,024 B** | POSIX SHM | 351.15 | 351.147 | **MATCH** |
| **1,024 B** | Unix Domain Socket | 674.68 | 674.682 | **MATCH** |
| **1,024 B** | Kernel Mailbox | **3.35** (P50: 0.93) | 3.349 (mean_p50: 0.925) | **MATCH** |
| **1,024 B** | Adaptive Policy | 307.93 | 307.925 | **MATCH** (Routed to SHM) |
| **4,096 B** | Anonymous Pipe | **301.70** | **301.700** | **MATCH** (Lowest userspace RTT) |
| **4,096 B** | Unix Domain Socket | 720.01 | 720.010 | **MATCH** |
| **4,096 B** | POSIX SHM | N/A (EMSGSIZE) | Bounded capacity $\le 1024$ B | **MATCH** |
| **16,384 B** | Anonymous Pipe | **472.79** | **472.786** | **MATCH** |
| **16,384 B** | Unix Domain Socket | 571.35 | 571.347 | **MATCH** |
| **65,536 B** | Anonymous Pipe | **505.93** | **505.928** | **MATCH** |
| **65,536 B** | Unix Domain Socket | 648.34 | 648.337 | **MATCH** |
| **262,144 B** | Anonymous Pipe | 4,548.77 | 4548.766 | **MATCH** (Kernel pipe buffer saturates) |
| **262,144 B** | Unix Domain Socket | **2,590.28** | **2590.284** | **MATCH** (1.756x faster than Pipe) |

---

## 2. Tail Latency Percentiles (1,024-Byte Payloads)

Dataset: `results/unified/processed/statistical_summary.csv` (Payload: 1024 B)

| Mechanism | P50 Median ($\mu\text{s}$) | P90 ($\mu\text{s}$) | P95 ($\mu\text{s}$) | P99 ($\mu\text{s}$) | Minimum ($\mu\text{s}$) |
|---|---|---|---|---|---|
| **Anonymous Pipe** | 119.34 | 210.03 | 255.20 | 392.06 | 5.78 |
| **Named FIFO** | 203.54 | 1,640.44 | 3,095.62 | 5,273.61 | 3.56 |
| **System V MQ** | 122.99 | 576.94 | 843.41 | 2,244.55 | 52.67 |
| **POSIX MQ** | 335.14 | 929.82 | 1,423.25 | 3,551.23 | 54.59 |
| **POSIX SHM** | 154.21 | 504.35 | 786.76 | 3,120.92 | 0.81 |
| **Unix Domain Socket**| 296.75 | 1,730.81 | 3,867.49 | 6,772.23 | 8.24 |
| **Kernel Mailbox** | 0.93 | 0.99 | 1.07 | 1.90 | 0.84 |

*Verification*: All percentiles satisfy strict monotonicity: $\text{Min} \le P_{50} \le P_{90} \le P_{95} \le P_{99} \le \text{Max}$.

---

## 3. System Call and Resource Classification

Dataset: `results/unified/raw/syscall_metrics.csv` (Workload: 100 round-trip exchanges)

| Mechanism | Communication Syscalls | Syscalls per Exchange | Synch Mechanism | Zero Data Copies? |
|---|---|---|---|---|
| **Anonymous Pipe** | 400 (`read` 200, `write` 200) | 4.00 | Blocking VFS wait queue | No (2 copies: User $\leftrightarrow$ Kernel) |
| **Named FIFO** | 400 (`read` 200, `write` 200) | 4.00 | Blocking VFS wait queue | No (2 copies) |
| **System V MQ** | 400 (`msgrcv` 200, `msgsnd` 200) | 4.00 | Kernel IPC wait queue | No (2 copies) |
| **POSIX MQ** | 400 (`mq_timedreceive`, `mq_timedsend`) | 4.00 | POSIX queue lock/wait | No (2 copies) |
| **POSIX SHM** | 206 (`futex` 206) | 2.06 | Unnamed semaphores / futex | **Yes (0 data copies)** |
| **Unix Domain Skt**| 400 (`recvfrom` 200, `sendto` 200) | 4.00 | Socket buffer sk_buff | No (2 copies) |

*Verification*: POSIX Shared Memory achieves a **48.5% reduction** in total communication system calls and executes **zero data-path copies** through the kernel.
