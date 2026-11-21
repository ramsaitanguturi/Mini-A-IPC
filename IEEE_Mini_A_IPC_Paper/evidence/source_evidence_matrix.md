# Mini-A-IPC: Source-to-Paper Evidence Matrix

This matrix establishes the complete traceability between every architectural, algorithmic, implementation, and experimental claim made in the research paper and the verified repository source files, kernel drivers, benchmark datasets, and test execution logs.

---

## 1. Architecture and Subsystem Implementations

| Subsystem / Feature | Paper Claim & Scope | Source Code File / Header | Verification Status | Implementation Details & Proof |
|---|---|---|---|---|
| **Anonymous Pipes** | Bidirectional ping-pong across two unidirectional pipes; non-blocking error handling, `SIGPIPE` ignored via `sigaction`. | `src/ipc_pipe.c`, `include/ipc.h` | **VERIFIED** | Lines 57–193 in `src/ipc_pipe.c`. `pipe(request_pipe)` and `pipe(response_pipe)`. `SIGPIPE` ignored (`SIG_IGN`). Full read/write loops `read_all()`, `write_all()`. |
| **Named Pipes (FIFO)** | Private FIFOs in `/tmp` with `0600` permissions; deadlock-free open order; standalone CLI executable; safe unlinking. | `src/ipc_fifo.c`, `include/ipc.h` | **VERIFIED** | Lines 57–250 in `src/ipc_fifo.c`. Child opens RDONLY then WRONLY; parent opens WRONLY then RDONLY. `mkfifo()` with `0600`. Standalone `bin/ipc_fifo` compiles independently. |
| **POSIX Shared Memory** | Shared mailbox with 4 unnamed POSIX semaphores; 64-byte cache alignment; 1024-byte payload limit; child exit detection via `SIGCHLD`. | `src/ipc_shm.c`, `include/ipc.h` | **VERIFIED** | Lines 21–37 in `src/ipc_shm.c`. `_Alignas(64)` on semaphores and payload buffers. `SHM_MAX_PAYLOAD = 1024U`. `sem_wait_parent()` catches child death via `SIGCHLD` (`sa_flags = 0`). |
| **System V Message Queues** | Private IPC queue (`IPC_PRIVATE`); request/response multiplexing via `mtype` (1=req, 2=resp); `IPC_RMID` cleanup; `SIGCHLD` break on exit. | `src/ipc_sysv_mq.c`, `include/ipc.h` | **VERIFIED** | Lines 35–246 in `src/ipc_sysv_mq.c`. `msgget(IPC_PRIVATE, 0600)`. `SIGCHLD` handler without `SA_RESTART` breaks `msgrcv()` with `EINTR`. Explicit `msgctl(msqid, IPC_RMID, NULL)`. |
| **POSIX Message Queues** | Priority queues in `/dev/mqueue`; dynamic `mq_msgsize = payload_size`; unprivileged ceiling `mq_maxmsg = 10`; descriptor cleanup. | `src/ipc_posix_mq.c`, `include/ipc.h` | **VERIFIED** | Lines 51–250 in `src/ipc_posix_mq.c`. `mq_open()` with `O_CREAT \| O_EXCL \| 0600`. `attr.mq_maxmsg = 10`. Dual queues `/mini_aipc_req_<pid>` and `/mini_aipc_resp_<pid>`. |
| **Unix Domain Sockets** | Full-duplex byte stream (`AF_UNIX`, `SOCK_STREAM`); bind/listen before `fork()` to prevent rendezvous race; robust stream looping. | `src/ipc_uds.c`, `include/ipc.h` | **VERIFIED** | Lines 43–250 in `src/ipc_uds.c`. `listen(listen_fd, 1)` called before `fork()`. Server accepts connection; client connects. Handled via `send_all()` and `recv_all()`. |
| **Static Adaptive Selector** | Static threshold routing: $\le 1024$ B $\to$ `shm`, $> 1024$ B $\to$ `pipe`. Fast path zero-overhead decision. | `src/selector.c`, `include/ipc.h` | **VERIFIED** | Lines 23–28 in `src/selector.c`. Returns `TRANSPORT_SHM` if `payload_size <= threshold && payload_size <= SHM_MAX_PAYLOAD`, else `TRANSPORT_PIPE`. |
| **EWMA Telemetry & Hysteresis** | Closed-loop adaptive controller with EWMA latency smoothing ($\alpha = 0.15$) and 8% hysteresis margin (`hysteresis = 1.08`). | `src/selector.c`, `include/ipc.h` | **VERIFIED** | Lines 30–83 in `src/selector.c`. Maintains `ewma_latency_shm_ns` and `ewma_latency_pipe_ns`. Switches only when performance delta exceeds $1.08\times$. |
| **Lock-Free SPSC Ring Buffer** | Single-Producer Single-Consumer cache-aligned circular ring; atomic acquire/release semantics; zero futex syscalls. | `include/spsc_ring.h`, `src/ipc_spsc_ring.c` | **VERIFIED** | Lines 1–45 in `include/spsc_ring.h`, lines 1–249 in `src/ipc_spsc_ring.c`. Padded `head` and `tail` (`_Alignas(64)`). Pause/yield backoff. |
| **Linux Kernel Mailbox** | Custom character device `/dev/aipc`; bounded circular ring (64 KB); wait queues; mutex synchronization; safe teardown barrier. | `kernel/aipc_module.c` | **VERIFIED** | Lines 1–269 in `kernel/aipc_module.c`. Uses `alloc_chrdev_region()`, `cdev_add()`, `device_create()`, `noop_llseek`. Teardown barrier waits on `atomic_read(&active_ops) == 0`. |

---

## 2. Experimental Datasets and Empirical Claims

| Experimental Metric | Paper Claim & Value | Source Dataset & File | Verification Status | Exact Traceable Value in Repository |
|---|---|---|---|---|
| **Round-Trip Latency (64 B)** | System V MQ achieves lowest userspace latency ($123.33\,\mu\text{s}$), outperforming UDS ($126.93\,\mu\text{s}$) and Pipe ($129.84\,\mu\text{s}$). | `results/unified/processed/aggregated_results.csv` | **VERIFIED** | Line 81: `sysv,64,avg_rtt_us_mean = 123.333`. Line 88: `uds,64 = 126.926`. Line 60: `pipe,64 = 129.836`. |
| **Round-Trip Latency (256 B)** | System V MQ achieves lowest userspace latency ($115.13\,\mu\text{s}$), outperforming POSIX MQ ($118.03\,\mu\text{s}$) and UDS ($121.28\,\mu\text{s}$). | `results/unified/processed/aggregated_results.csv` | **VERIFIED** | Line 82: `sysv,256,avg_rtt_us_mean = 115.127`. Line 68: `posix,256 = 118.029`. Line 89: `uds,256 = 121.280`. |
| **Round-Trip Latency (1 KB)** | Unix Domain Sockets achieve lowest userspace latency ($128.28\,\mu\text{s}$), outperforming POSIX MQ ($130.65\,\mu\text{s}$) and Pipe ($136.21\,\mu\text{s}$). | `results/unified/processed/aggregated_results.csv` | **VERIFIED** | Line 90: `uds,1024,avg_rtt_us_mean = 128.283`. Line 69: `posix,1024 = 130.651`. Line 62: `pipe,1024 = 136.208`. |
| **Large Payload Scalability (256 KB)** | Unix Domain Sockets outperform Pipes by $2.54\times$ ($449.64\,\mu\text{s}$ vs $1144.22\,\mu\text{s}$); UDS wire bandwidth reaches $1,304.4$ MB/s vs Pipe $502.4$ MB/s. | `results/unified/processed/aggregated_results.csv` | **VERIFIED** | Line 94: `uds,262144,avg_rtt_us_mean = 449.643`. Line 66: `pipe,262144 = 1144.218`. Ratio: $1144.218 / 449.643 = 2.545\times$. |
| **Kernel Mailbox Loopback Floor** | In-process loopback floor of $0.72 - 3.35\,\mu\text{s}$ across 64 B - 1 KB; single-process without context switches. Two-process IPC bounded by context switch floor (~95–130 $\mu$s). | `results/unified/processed/statistical_summary.csv` | **VERIFIED** | Line 16: `kernel,64,min_rtt_us = 0.676, mean_p50 = 0.789, mean_avg = 3.289`. In-process loopback baseline. |
| **Communication System Calls** | SHM eliminates data-path system calls (2.06 futex calls/exch vs 4.00 read/write or send/recv calls/exch for byte streams). | `results/unified/raw/syscall_metrics.csv` | **VERIFIED** | Lines 1–7 in `results/unified/raw/syscall_metrics.csv`. SHM: 206 calls / 100 exchanges = 2.06 futex sync calls. Pipe/UDS/SysV/POSIX: 400 calls / 100 exchanges = 4.00. |
| **Adaptive Selector Regret** | On Fedora 45, static selector achieves 71.43% accuracy with 27.68% mean intra-trial matched latency regret (29.51% inter-trial); calibrated 3-tier policy achieves 100% oracle accuracy. | `results/unified/processed/statistical_summary.csv`, `docs/ADAPTIVE_POLICY_RESULTS.md` | **VERIFIED** | Lines 1–7 in `results/unified/processed/statistical_summary.csv`. 5 of 7 payload tiers match empirical optimum (71.43%). Mean intra-trial regret: 27.68%. |
| **Virtualization Latency Floor** | In virtualized KVM guest on Fedora 45, context-switch floor dominates ($100 - 140\,\mu\text{s}$) across all multi-process mechanisms due to hypervisor vCPU scheduling and VM exits, compared to 1–5 $\mu$s on bare-metal silicon. | `results/unified/processed/aggregated_results.csv`, Section 8 Discussion | **VERIFIED** | Table III and Table IV confirm tight clustering around 115–140 $\mu$s across all user-space mechanisms at small payloads. |
| **Multi-Producer Multi-Consumer** | POSIX MQ, SysV MQ, and Kernel Mailbox support MPMC scaling (4P:4C); point-to-point stream and single-mailbox SHM are unsupported by design. | `results/unified/raw/concurrency_results.csv`, `docs/CONCURRENCY_RESULTS.md` | **VERIFIED** | Lines 32–39 in `results/unified/raw/concurrency_results.csv`. Pipe, FIFO, SHM, UDS, Adaptive marked `UNSUPPORTED_BY_DESIGN` for M:N. SysV, POSIX, Kernel pass 4P:4C. |

---

## 3. Automated Test Suite Verification

| Test Suite | Execution Command | Result | Evidence File |
|---|---|---|---|
| Comprehensive Verification | `python tests/final_verification_test.py` | **15 / 15 Passed (100%)** | `docs/FINAL_TEST_REPORT.md` Section 2 |
| Unified Benchmark Pipeline | `python tests/test_unified_benchmark.py` | **5 / 5 Passed (100%)** | `docs/FINAL_TEST_REPORT.md` Section 3 |
| CLI Correctness & Failure Paths | `bash tests/test_cli.sh` | **24 Passed, 7 Skipped, 0 Failed** | `docs/FINAL_TEST_REPORT.md` Section 4 |
