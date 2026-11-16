# Mini-A-IPC: Project Overview & Academic Research Scope

## 1. Project Introduction

**Mini-A-IPC** is an Operating Systems systems-programming and empirical research platform evaluating Inter-Process Communication (IPC) mechanisms on Linux for High-Performance Computing (HPC) and low-latency system architectures.

The project builds upon the empirical baseline established by **I. M. Danyliuk (2026)** ("Classical IPC in Linux OS: Review and Latency Analysis for HPC Scenarios", *SWorldJournal*, Issue 37, Part 2), extending the investigation to include:
1. All six classical Linux userspace IPC mechanisms (Anonymous Pipes, Named FIFOs, POSIX Shared Memory, System V Message Queues, POSIX Message Queues, and Unix Domain Sockets).
2. A custom Linux Kernel Mailbox module (`/dev/aipc`) utilizing an in-kernel circular ring buffer.
3. An Adaptive IPC Selection Engine implementing both static size thresholding and dynamic telemetry-based EWMA hysteresis controllers.
4. Comprehensive multi-process concurrency benchmarking (M:N producer-consumer topologies).
5. System-call profiling, CPU utilization, context switch analysis, and tail-latency percentile evaluation ($P_{50}, P_{90}, P_{95}, P_{99}, P_{99.9}$).

---

## 2. Research Objectives

1. **Empirical Latency vs. Throughput Characterization**:
   Quantify how message payload size ($64\text{ B}$ to $256\text{ KB}$) influences round-trip communication latency, wire throughput, and context-switching overhead across diverse IPC paradigms.
2. **Zero-Copy vs. Kernel-Buffered Transports**:
   Examine the tradeoff between memory-mapped zero-copy transfers (POSIX Shared Memory with unnamed semaphores) and kernel-buffered streaming interfaces (Anonymous Pipes, FIFOs, Unix Domain Sockets) under multi-core and virtualized scheduling.
3. **Adaptive IPC Routing**:
   Evaluate whether a software decision controller can dynamically route application payloads to optimal transports without introducing prohibitive decision overhead or selection regret.
4. **Kernel-Level Communication**:
   Determine whether a custom character-device driver (`/dev/aipc`) can bridge the performance gap between userland shared memory and traditional system-call based IPC.
5. **Multi-Process Concurrency & Scalability**:
   Analyze how structured message queues (POSIX MQ, System V MQ) and stream sockets scale when subjected to high-contention multi-producer multi-consumer workloads.

---

## 3. Technology Stack & Supported Transports

| Transport | Category | Paradigm | Data Path | Primary Syscalls | Typical Use Case |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Anonymous Pipe** | Byte Stream | Unidirectional / Duplex Pair | Kernel page buffer (`pipe_buffer`) | `pipe2()`, `read()`, `write()` | Parent-child streaming |
| **Named FIFO** | Byte Stream | Named Filesystem Node | Kernel page buffer | `mkfifo()`, `open()`, `read()`, `write()` | Unrelated local process streaming |
| **POSIX SHM** | Shared Memory | Memory-Mapped Ring Buffer | Direct RAM copy (Cache-coherent) | `shm_open()`, `mmap()`, `sem_wait()`, `sem_post()` | Ultra-low-latency small payloads |
| **System V MQ** | Message Queue | Kernel Linked List | Kernel IPC allocation | `msgget()`, `msgsnd()`, `msgrcv()`, `msgctl()` | Legacy message passing |
| **POSIX MQ** | Message Queue | Virtual VFS (`/dev/mqueue`) | Kernel priority queue | `mq_open()`, `mq_send()`, `mq_receive()` | Modern real-time priority messaging |
| **Unix Domain Socket**| Socket Stream | Bidirectional Local Stream | Kernel socket buffers | `socket()`, `bind()`, `connect()`, `send()`, `recv()` | Daemon/client local network IPC |
| **Kernel Mailbox** | Kernel Driver | Character Device (`/dev/aipc`)| In-kernel circular ring | `open()`, `read()`, `write()`, `poll()` | Custom driver-assisted IPC |
| **Adaptive Selector** | Hybrid | Dynamic Policy Routing | Delegates to SHM, Pipe, or UDS | Dynamic delegation | General-purpose adaptive systems |

---

## 4. Key Experimental Takeaways

- **Sub-Microsecond Kernel Floor**: The custom kernel mailbox module achieves an uncontended single-process loopback latency of **0.72–0.85 $\mu\text{s}$**, demonstrating the raw efficiency of in-kernel circular buffering.
- **Context-Switch Latency Floor**: In multi-process benchmark configurations, the Linux process scheduler introduces an unavoidable context-switch floor of **95–120 $\mu\text{s}$** (and up to $280\,\mu\text{s}$ in virtualized guest environments), which dominates message transfer time for payloads below 1 KB.
- **Shared Memory Supremacy for Small Messages**: For payloads $\le 256$ B, POSIX Shared Memory achieves the lowest latency ($286.87\,\mu\text{s}$ on Fedora 45) by eliminating kernel data copying.
- **Pipe Efficiency for Intermediate Payloads**: For payloads between 1 KB and 64 KB, Anonymous Pipes deliver superior throughput ($110\text{ MB/s}$ peak) due to heavily optimized circular page rings in the Linux VFS.
- **Socket Buffer Scaling for Large Payloads**: For payloads exceeding 64 KB (up to 256 KB), Unix Domain Sockets outperform pipes by **1.75x** due to dynamic socket buffer window scaling.
- **Adaptive Controller Viability**: The adaptive selector incurs negligible decision overhead (~2.36–18.42 ns) and eliminates up to 47.5% of data-path system calls in mixed 80/20 small/large workloads.
