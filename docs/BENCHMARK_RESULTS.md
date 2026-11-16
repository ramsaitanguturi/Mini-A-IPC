# Mini-A-IPC: Comprehensive Benchmark Results & Empirical Analysis

## 1. Executive Summary

This report documents the empirical benchmark results of the Mini-A-IPC research suite across six classical userspace IPC mechanisms, the custom Linux kernel mailbox device (`/dev/aipc`), and the Adaptive Transport Selector.

The benchmark data presented here originates from two strictly isolated experimental environments:
1. **Primary Unified Dataset (Fedora 45 Linux, Kernel 7.3.3, Intel Core 7 240H)**: $N=7$ randomized trials of 10,000 round-trip exchanges per configuration (70,000 measured messages per cell), covering payload sizes from 64 B to 256 KB.
2. **Comparative Host Dataset (Ubuntu 26.04 on WSL2, Kernel 6.6.87, AMD Ryzen 7 8845HS)**: 10,000 exchanges across 64 B to 1024 B payloads.

All 13 publication-quality visualizations referenced in this document are located in [`results/unified/graphs/`](../results/unified/graphs/) in both vector PDF and high-resolution PNG formats.

---

## 2. Round-Trip Latency Results (Fedora 45 Linux)

The table below summarizes the mean round-trip latency ($\mu\text{s}$) across 7 independent trials ($10,000$ messages per trial, $500$ untimed warm-up cycles):

| Payload Size | Anonymous Pipe | Named FIFO | System V MQ | POSIX MQ | POSIX SHM | Unix Domain Skt | Kernel Mailbox* | Adaptive Policy |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **64 B** | 399.25 | 464.27 | 359.59 | 499.72 | **286.87** | 618.33 | 3.32 | 439.66 (`shm`) |
| **256 B** | 344.57 | 456.39 | 395.60 | 767.24 | **320.35** | 619.67 | 2.96 | 353.13 (`shm`) |
| **1,024 B** | **278.76** | 619.56 | 317.58 | 477.91 | 351.15 | 674.68 | 3.35 | 307.93 (`shm`) |
| **4,096 B** | **301.70** | 454.10 | 331.48 | 534.33 | *N/A (Exceeds 1KB)* | 720.01 | 3.95 | 372.07 (`pipe`) |
| **16,384 B** | **472.79** | 584.14 | *N/A (Limit)*| *N/A (Limit)*| *N/A* | 571.35 | 11.45 | 535.24 (`pipe`) |
| **65,536 B** | **505.93** | 633.72 | *N/A* | *N/A* | *N/A* | 648.34 | *N/A* | 882.30 (`pipe`) |
| **262,144 B** | 4,548.77 | 4,217.02 | *N/A* | *N/A* | *N/A* | **2,590.28** | *N/A* | 3,178.52 (`pipe`) |

*\*Note: Kernel Mailbox results represent single-process loopback through the character device without two-process context-switching overhead; under two-process constraints, scheduler dispatch adds ~95–120 µs.*

### Key Observations:
1. **Small Payloads ($\le 256$ B)**: POSIX Shared Memory achieves the lowest userspace round-trip latency ($286.87\,\mu\text{s}$ at 64 B and $320.35\,\mu\text{s}$ at 256 B) because memory copies execute entirely in userspace without traversing the Linux VFS or network stack.
2. **Intermediate Payloads ($1\text{ KB} - 64\text{ KB}$)**: Anonymous Pipes consistently deliver the lowest latency ($278.76\,\mu\text{s}$ at 1 KB, $301.70\,\mu\text{s}$ at 4 KB). The Linux kernel pipe buffer ring absorbs these payloads without allocation overhead.
3. **Very Large Payloads ($256\text{ KB}$)**: Unix Domain Sockets (`uds`) outperform Anonymous Pipes by **1.75x** ($2,590.28\,\mu\text{s}$ vs $4,548.77\,\mu\text{s}$). Pipes default to a 64 KB kernel capacity, forcing 256 KB transfers into 4 blocking chunk iterations, whereas UDS dynamic socket buffer auto-tuning handles large transfers efficiently.

---

## 3. Latency Percentiles and Tail Distribution (P50, P95, P99)

Below are the median (P50) and tail percentiles (P95, P99) for 1024-byte payloads across all mechanisms:

| Mechanism | Min RTT ($\mu\text{s}$) | Median P50 ($\mu\text{s}$) | Tail P90 ($\mu\text{s}$) | Tail P95 ($\mu\text{s}$) | Tail P99 ($\mu\text{s}$) | Max RTT ($\mu\text{s}$) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Anonymous Pipe** | 98.42 | 265.10 | 312.40 | 338.90 | 412.50 | 1,894.20 |
| **Named FIFO** | 104.20 | 589.40 | 694.10 | 742.30 | 884.60 | 2,410.80 |
| **System V MQ** | 101.15 | 298.40 | 345.20 | 382.10 | 489.30 | 2,105.40 |
| **POSIX MQ** | 115.30 | 442.80 | 520.60 | 580.40 | 710.20 | 2,980.50 |
| **POSIX SHM** | 92.10 | 335.60 | 398.20 | 430.50 | 552.10 | 2,240.10 |
| **Unix Domain Skt** | 108.70 | 640.20 | 750.10 | 812.40 | 995.80 | 3,120.40 |
| **Kernel Mailbox** | 0.84 | 0.93 | 0.96 | 1.00 | 1.30 | 157.19 |

Visualizations:
- [Figure 1: Mean Latency Comparison](../results/unified/graphs/latency_comparison.png)
- [Figure 2: Median P50 Latency Comparison](../results/unified/graphs/p50_latency.png)
- [Figure 3: P95 Tail Latency Comparison](../results/unified/graphs/p95_latency.png)
- [Figure 4: P99 Tail Latency Comparison](../results/unified/graphs/p99_latency.png)

---

## 4. Throughput and Bandwidth Scaling

Throughput in messages per second and wire bandwidth in megabytes per second:

| Mechanism | 64 B (msg/s) | 1,024 B (msg/s) | 16,384 B (msg/s) | 262,144 B (msg/s) | Peak Bandwidth |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Anonymous Pipe** | 2,504.70 | 3,587.32 | 2,115.10 | 219.84 | **110.0 MB/s** (64 KB) |
| **Named FIFO** | 2,153.92 | 1,614.05 | 1,711.92 | 237.13 | **98.5 MB/s** (64 KB) |
| **System V MQ** | 2,780.94 | 3,148.81 | *Unsupported* | *Unsupported* | **24.1 MB/s** (4 KB) |
| **POSIX MQ** | 2,001.12 | 2,092.44 | *Unsupported* | *Unsupported* | **14.9 MB/s** (4 KB) |
| **POSIX SHM** | **3,485.90** | 2,847.79 | *Unsupported* | *Unsupported* | **5.5 MB/s** (1 KB) |
| **Unix Domain Skt** | 1,617.26 | 1,482.18 | 1,750.24 | **386.06** | **193.3 MB/s** (256 KB) |

Visualizations:
- [Figure 5: Throughput Scaling](../results/unified/graphs/throughput_comparison.png)
- [Figure 10: Payload Scalability (64 B - 256 KB)](../results/unified/graphs/payload_scalability.png)

---

## 5. Comparative Host Dataset (Ubuntu WSL2 / AMD Ryzen 7 8845HS)

Measurements recorded on Ubuntu 26.04 on WSL2 across 10,000 message round-trips:

| Payload Size | Pipe ($\mu\text{s}$) | FIFO ($\mu\text{s}$) | System V MQ ($\mu\text{s}$) | POSIX MQ ($\mu\text{s}$) | POSIX SHM ($\mu\text{s}$) | Unix Domain Skt ($\mu\text{s}$) |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **64 B** | 107.71 | 108.21 | 109.85 | 116.91 | 106.60 | **99.60** |
| **128 B** | 114.74 | 117.09 | 115.47 | 127.50 | 114.29 | **94.44** |
| **256 B** | 112.89 | 119.69 | 116.19 | 112.89 | 102.92 | **93.53** |
| **512 B** | 117.41 | 119.43 | 118.57 | 124.19 | 110.85 | **95.53** |
| **1,024 B** | 114.72 | 141.98 | 123.53 | 119.92 | 108.06 | **95.15** |

### WSL2 Virtualization Insights:
- In WSL2, Unix Domain Sockets exhibited the lowest latency across all small payloads ($93.53 - 99.60\,\mu\text{s}$), outperforming both shared memory and pipes.
- This contrast highlights how hypervisor virtualization affects IPC: shared memory page table synchronizations can incur cross-VM fault costs, whereas socket loopback is optimized inside the WSL2 kernel.

---

## 6. Resource Profiling: CPU, Memory, and System Calls

| Mechanism | CPU Util (%) | User CPU (s) | Sys CPU (s) | Voluntary Switches | Involuntary Switches | Peak RSS (KB) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Anonymous Pipe** | 78.4% | 0.08 | 0.22 | 20,012 | 14 | 5,420 |
| **Named FIFO** | 74.2% | 0.09 | 0.26 | 20,014 | 18 | 5,432 |
| **System V MQ** | 81.0% | 0.06 | 0.20 | 20,008 | 12 | 5,390 |
| **POSIX MQ** | 83.5% | 0.07 | 0.25 | 20,010 | 16 | 5,448 |
| **POSIX SHM** | **68.2%** | 0.12 | **0.11** | 20,006 | 8 | 5,820 |
| **Unix Domain Skt** | 82.1% | 0.09 | 0.28 | 20,015 | 22 | 5,510 |

Visualizations:
- [Figure 6: CPU Utilization Comparison](../results/unified/graphs/cpu_comparison.png)
- [Figure 7: Memory Footprint (Peak RSS)](../results/unified/graphs/memory_comparison.png)
- [Figure 8: Voluntary and Involuntary Context Switches](../results/unified/graphs/context_switches.png)
- [Figure 9: System Call Breakdown](../results/unified/graphs/syscall_comparison.png)

---

## 7. Multi-Process Concurrency Evaluation

Evaluating Multi-Producer Multi-Consumer (M:N) scaling under high contention:
- **POSIX Message Queues (`posix`)**: Supported 4 Producers and 4 Consumers (4P:4C) with zero packet drops or synchronization faults.
- **Unix Domain Sockets (`uds`)**: Handled 4P:4C concurrent clients connected to a single server daemon cleanly.
- **Shared Memory Mailbox (`shm`)**: Bounded single-mailbox topology correctly rejected concurrent multi-producer topologies (`rc=3`, `UNSUPPORTED`), establishing that a single-mailbox SHM design is strictly SPSC.
- Visualization: [Figure 11: Concurrency Scalability](../results/unified/graphs/concurrency_scalability.png).
