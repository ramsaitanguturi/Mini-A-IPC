# Mini-A-IPC: Architectural Design & System Internals

## 1. High-Level Architectural Model

Mini-A-IPC is structured into three coordinated layers:
1. **Core Transport Implementations (`src/`)**: Modular, self-contained C implementations of six standard Linux IPC mechanisms, the custom SPSC ring buffer, and the adaptive selection engine.
2. **Kernel Mailbox Subsystem (`kernel/`)**: A Linux Loadable Kernel Module (LKM) providing `/dev/aipc` backed by a 64 KB in-kernel circular ring buffer with sleepable mutex synchronization and wait-queue notification.
3. **Benchmarking & Analysis Infrastructure (`bench/`, `tests/`)**: A unified measurement harness, microbenchmark binaries, multi-process concurrency orchestrators, system-call profilers, and Python statistical processing pipelines.

```
+===================================================================================+
|                                User Application Layer                             |
|                                                                                   |
|  +---------------------+  +----------------------+  +--------------------------+  |
|  | mini-aipc (RTT CLI) |  | mini-aipc-concurrency|  | mini-aipc-mixed (80/20)  |  |
|  +----------+----------+  +----------+-----------+  +------------+-------------+  |
|             |                        |                           |                |
+=============|========================|===========================|================+
|             v                        v                           v                |
|  +-----------------------------------------------------------------------------+  |
|  |                        Adaptive Transport Selector                          |  |
|  |   - Static Size Threshold (<= 1024 B -> SHM, > 1024 B -> Pipe)              |  |
|  |   - Dynamic EWMA Telemetry Controller (alpha=0.15, 8% Hysteresis)           |  |
|  +-----------------------------------------------------------------------------+  |
|             |                                                                     |
|             +--------+----------------+----------------+----------------+         |
|                      |                |                |                |         |
|                      v                v                v                v         |
|  +=============================================================================+  |
|  |                             IPC Transport Layer                             |  |
|  |                                                                             |  |
|  |  +----------------+  +-----------------+  +-----------------+               |  |
|  |  | Anonymous Pipe |  | Named Pipe FIFO |  | Unix Domain Skt |  (Stream IPC) |  |
|  |  +----------------+  +-----------------+  +-----------------+               |  |
|  |                                                                             |  |
|  |  +----------------+  +-----------------+                                    |  |
|  |  | System V MQ    |  | POSIX MQ        |                       (Message IPC)|  |
|  |  +----------------+  +-----------------+                                    |  |
|  |                                                                             |  |
|  |  +----------------+  +-----------------+                                    |  |
|  |  | POSIX SHM      |  | SPSC Ring Buffer|                       (Memory IPC) |  |
|  |  +----------------+  +-----------------+                                    |  |
|  +=============================================================================+  |
|                      |                                                            |
+======================|============================================================+
|                      v                                                            |
|  +=============================================================================+  |
|  |                          Linux Kernel Subsystem                             |  |
|  |                                                                             |  |
|  |  +-----------------------------------------------------------------------+  |  |
|  |  |              Custom Kernel Character Device: /dev/aipc                |  |  |
|  |  |   - 64 KB In-Kernel Bounded Circular Buffer                           |  |  |
|  |  |   - Reader/Writer Wait Queues (wait_event_interruptible)              |  |  |
|  |  |   - Sleepable Mutex Locking & Teardown Barrier Synchronization        |  |  |
|  |  +-----------------------------------------------------------------------+  |  |
|  |                                                                             |  |
|  |  +-------------------+  +-------------------+  +-------------------------+  |  |
|  |  | VFS Pipe Buffers  |  | IPC Namespace     |  | AF_UNIX Socket Buffers  |  |  |
|  |  +-------------------+  +-------------------+  +-------------------------+  |  |
|  +=============================================================================+  |
+===================================================================================+
```

---

## 2. Directory Layout & Module Responsibilities

```text
Mini-A-IPC/
├── include/
│   └── ipc.h                      Authoritative C API definitions, structs, limits
├── src/
│   ├── ipc_pipe.c                 Anonymous pipe round-trip implementation
│   ├── ipc_fifo.c                 Named FIFO round-trip implementation
│   ├── ipc_shm.c                  POSIX shared memory mailbox implementation
│   ├── ipc_sysv_mq.c              System V message queue implementation
│   ├── ipc_posix_mq.c             POSIX message queue implementation
│   ├── ipc_uds.c                  Unix domain stream socket implementation
│   ├── ipc_spsc_ring.c            Lock-free single-producer single-consumer ring
│   ├── selector.c                 Static threshold and EWMA adaptive controllers
│   ├── mixed_benchmark.c          Mixed-payload (80% small / 20% large) benchmark
│   ├── concurrency_benchmark.c    Multi-producer multi-consumer benchmark
│   └── main.c                     CLI driver for mini-aipc executable
├── kernel/
│   ├── aipc_module.c              Linux character device driver source (/dev/aipc)
│   ├── Kbuild                     Linux kernel build system file
│   └── Makefile                   Out-of-tree kernel module build configuration
├── bench/
│   ├── unified_bench.c            C unified microbenchmark harness
│   ├── orchestrate_unified.py     Experiment coordinator across all workloads
│   ├── process_unified_results.py Result aggregator, chart generator, report author
│   ├── analyze_results.py         Statistical calculations & hypothesis testing
│   ├── generate_graphs.py         Matplotlib publication chart generation
│   ├── generate_report.py         Automated Markdown research report generator
│   ├── profile_resources.py       Resource profiler (CPU, RSS, context switches)
│   ├── run_unified_benchmark.sh   Automated test runner shell script
│   └── run_kernel_suite.sh        Kernel module automated test suite
├── tests/
│   ├── test_cli.sh                CLI options, error paths, and regression tests
│   ├── final_verification_test.py Comprehensive 15-test Python verification suite
│   ├── test_unified_benchmark.py  Pytest validation of unified pipeline
│   └── kernel/
│       ├── test_device.sh         Functional verification script for /dev/aipc
│       ├── test_mailbox.c         C loopback test for kernel mailbox
│       └── benchmark_mailbox.py   Python throughput/latency test for /dev/aipc
├── results/
│   ├── comparative_benchmark.csv  WSL2 Ubuntu comparative dataset (historical)
│   └── unified/                   Fedora Linux authoritative dataset
│       ├── raw/                   Raw trial CSVs (all_results.csv, kernel_results.csv)
│       ├── processed/             Aggregated summaries, metadata JSON
│       ├── graphs/                13 publication-quality PNG and PDF charts
│       └── reports/               Generated benchmark reports
└── docs/                          Academic reports, audits, and technical guides
```

---

## 3. Data Structures and Synchronization Contracts

### 3.1 POSIX Shared Memory Mailbox Layout
To prevent cache-line bouncing (false sharing) between producer and consumer processes, `shared_mailbox_t` explicitly aligns synchronization primitives and payload buffers across distinct CPU cache lines (64 bytes):

```c
typedef struct {
    /* Cache line 0: Request synchronization */
    _Alignas(64) sem_t request_empty;
    sem_t request_full;

    /* Cache line 1: Response synchronization */
    _Alignas(64) sem_t response_empty;
    sem_t response_full;

    /* Cache line 2+: Producer-written payload */
    _Alignas(64) size_t request_length;
    unsigned char request[SHM_MAX_PAYLOAD];

    /* Cache line N+: Consumer-written payload */
    _Alignas(64) size_t response_length;
    unsigned char response[SHM_MAX_PAYLOAD];
} shared_mailbox_t;
```

### 3.2 Kernel Ring Buffer State Machine
The kernel mailbox operates as a circular queue protected by a sleepable mutex:
- $\text{Buffer Capacity} = C$ (default 65,536 bytes)
- In-flight bytes: $U = \text{used}$
- Available write space: $W = C - U$
- Head index: $H$ (read pointer), Tail index: $T$ (write pointer)
- Read operation: consumes $\min(\text{requested}, U)$ bytes, updates $H = (H + n) \pmod C$, decrements $U$, wakes `writers` wait queue.
- Write operation: produces $\min(\text{requested}, W)$ bytes, updates $T = (T + n) \pmod C$, increments $U$, wakes `readers` wait queue.
- Teardown barrier: `aipc_exit()` asserts `shutdown = true`, wakes all waiters, and waits on `wait_event(teardown_wait, atomic_read(&active_ops) == 0)` before releasing buffer memory.

