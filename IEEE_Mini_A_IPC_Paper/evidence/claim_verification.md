# Mini-A-IPC: Quantitative Claim Verification Document

This document verifies every quantitative measurement, table row, latency percentile, throughput number, system call count, and benchmark parameter reported in the IEEE research paper against the underlying repository CSV files.

---

## 1. Primary Round-Trip Latency Claims (Fedora 45 Linux on KVM Guest)

Dataset: `results/unified/processed/aggregated_results.csv` and `results/unified/processed/statistical_summary.csv`  
Environment: Intel Core 7 240H (4 vCPUs, 3.8 GiB RAM), Fedora 45 Linux (KVM Guest), Linux 7.3.4-300.fc45.x86_64, GCC 16.2.1, 7 Trials, 10,000 Messages/Trial (over 3.4M single-pair exchanges, >3.9M total messages).

| Payload Size | Mechanism | Paper Claimed Mean RTT ($\mu\text{s}$) | CSV Exact Value (`avg_rtt_us_mean`) | Verification |
|---|---|---|---|---|
| **64 B** | Anonymous Pipe | 129.84 | 129.836 | **MATCH** |
| **64 B** | Named FIFO | 132.15 | 132.154 | **MATCH** |
| **64 B** | System V MQ | **123.33** | **123.333** | **MATCH** (Lowest userspace RTT) |
| **64 B** | POSIX MQ | 143.52 | 143.518 | **MATCH** |
| **64 B** | POSIX SHM | 138.66 | 138.662 | **MATCH** |
| **64 B** | Unix Domain Socket | 126.93 | 126.926 | **MATCH** |
| **64 B** | Kernel Mailbox | **3.29** (P50: 0.79) | 3.289 (mean_p50: 0.789) | **MATCH** (In-process loopback floor; 2-process IPC bounded by context-switch floor) |
| **64 B** | Adaptive Policy | 132.07 | 132.065 | **MATCH** (Routed to SHM) |
| **256 B** | Anonymous Pipe | 123.85 | 123.849 | **MATCH** |
| **256 B** | Named FIFO | 131.51 | 131.508 | **MATCH** |
| **256 B** | System V MQ | **115.13** | **115.127** | **MATCH** (Lowest userspace RTT) |
| **256 B** | POSIX MQ | 118.03 | 118.029 | **MATCH** |
| **256 B** | POSIX SHM | 146.40 | 146.401 | **MATCH** |
| **256 B** | Unix Domain Socket | 121.28 | 121.280 | **MATCH** |
| **256 B** | Kernel Mailbox | **2.95** (P50: 0.77) | 2.947 (mean_p50: 0.771) | **MATCH** (In-process loopback floor) |
| **256 B** | Adaptive Policy | 147.01 | 147.009 | **MATCH** (Routed to SHM) |
| **1,024 B** | Anonymous Pipe | 136.21 | 136.208 | **MATCH** |
| **1,024 B** | Named FIFO | 134.40 | 134.398 | **MATCH** |
| **1,024 B** | System V MQ | 134.12 | 134.120 | **MATCH** |
| **1,024 B** | POSIX MQ | 130.65 | 130.651 | **MATCH** |
| **1,024 B** | POSIX SHM | 139.73 | 139.734 | **MATCH** |
| **1,024 B** | Unix Domain Socket | **128.28** | **128.283** | **MATCH** (Lowest userspace RTT) |
| **1,024 B** | Kernel Mailbox | **3.35** (P50: 0.93) | 3.349 (mean_p50: 0.925) | **MATCH** (In-process loopback floor) |
| **1,024 B** | Adaptive Policy | 138.83 | 138.834 | **MATCH** (Routed to SHM) |
| **4,096 B** | Anonymous Pipe | 125.75 | 125.751 | **MATCH** |
| **4,096 B** | Named FIFO | **119.44** | **119.439** | **MATCH** (Lowest userspace RTT) |
| **4,096 B** | Unix Domain Socket | 134.02 | 134.019 | **MATCH** |
| **4,096 B** | POSIX SHM | N/A (EMSGSIZE) | Bounded capacity $\le 1024$ B | **MATCH** |
| **16,384 B** | Anonymous Pipe | **140.60** | **140.602** | **MATCH** (Lowest userspace RTT) |
| **16,384 B** | Unix Domain Socket | 142.14 | 142.142 | **MATCH** |
| **65,536 B** | Anonymous Pipe | 135.57 | 135.568 | **MATCH** (7,508.6 msg/s, 984.2 MB/s wire) |
| **65,536 B** | Unix Domain Socket | **123.53** | **123.533** | **MATCH** (8,325.9 msg/s, 1,091.3 MB/s wire, lowest RTT) |
| **262,144 B** | Anonymous Pipe | 1,144.22 | 1144.218 | **MATCH** (958.2 msg/s, 502.4 MB/s wire) |
| **262,144 B** | Unix Domain Socket | **449.64** | **449.643** | **MATCH** (2,488.0 msg/s, 1,304.4 MB/s wire, 2.54x faster) |

---

## 2. Tail Latency Percentiles (1,024-Byte Payloads)

Dataset: `results/unified/processed/aggregated_results.csv` (Payload: 1024 B, `single_pair_rtt`)

| Mechanism | Min ($\mu\text{s}$) | P50 Median ($\mu\text{s}$) | P90 ($\mu\text{s}$) | P95 ($\mu\text{s}$) | P99 ($\mu\text{s}$) | Max ($\mu\text{s}$) |
|---|---|---|---|---|---|---|
| **Anonymous Pipe** | 25.18 | 103.45 | 172.68 | 238.21 | 589.55 | 3,705.00 |
| **Named FIFO** | 28.87 | 101.26 | 163.63 | 249.67 | 673.32 | 4,973.34 |
| **System V MQ** | 50.40 | 107.16 | 206.96 | 274.49 | 584.49 | 4,240.19 |
| **POSIX MQ** | 45.76 | 101.58 | 167.36 | 243.14 | 602.82 | 3,390.22 |
| **POSIX SHM** | 6.33 | 114.59 | 190.20 | 254.59 | 434.93 | 4,283.17 |
| **Unix Domain Socket**| 51.39 | 101.21 | 179.06 | 231.93 | 455.49 | 4,770.49 |
| **Kernel Mailbox** | 0.84 | 0.93 | 0.99 | 1.07 | 1.90 | 4.88 |
| **Adaptive Policy** | 21.04 | 102.75 | 178.00 | 311.45 | 960.18 | 6,464.58 |

*Verification*: All percentiles satisfy strict monotonicity: $\text{Min} \le P_{50} \le P_{90} \le P_{95} \le P_{99} \le \text{Max}$. The user-space P50 values tightly cluster around 101–114 $\mu$s, reflecting the KVM hypervisor vCPU scheduling and VM exit floor.

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
