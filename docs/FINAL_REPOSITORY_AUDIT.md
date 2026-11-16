# Mini A-IPC: Comprehensive Final Repository Audit

**Author**: Senior Linux Kernel & Systems QA Engineering Audit  
**Date**: November 16, 2026  
**Repository Branch**: `main` (Local commit: `27817c9`, Tracking: `origin/main` at `726bce0`)  
**Status**: Pre-Reconciliation & Pre-Repair Audit  

---

## 1. Executive Summary

This document establishes the exhaustive technical baseline of the **Mini-A-IPC** repository prior to executing the comprehensive repair, reconciliation, benchmarking, and documentation phases.

Mini-A-IPC is an Operating Systems and High-Performance Computing (HPC) research project evaluating classical Linux Interprocess Communication (IPC) mechanisms:
1. Anonymous Pipes (`pipe`)
2. Named Pipes / FIFOs (`fifo`)
3. POSIX Shared Memory with Semaphores (`shm`)
4. System V Message Queues (`sysv`)
5. POSIX Message Queues (`posix`)
6. Unix Domain Stream Sockets (`uds`)
7. Custom Linux Kernel Character Device Mailbox (`/dev/aipc`)
8. Dynamic/Adaptive IPC Transport Selection (`adaptive`)

The audit inspects all source implementations, kernel drivers, test suites, benchmarking frameworks, historical and newly generated datasets, and academic documentation.

---

## 2. Directory Structure and Architectural Purpose

| Directory / File | Type | Purpose & Scope |
|---|---|---|
| `Makefile` | Build Automation | Compiles primary targets (`mini-aipc`, `mini-aipc-mixed`, `aipc-client`, `bin/ipc_fifo`, `bin/aipc_unified_bench`), runs tests, and invokes benchmark suites. |
| `include/ipc.h` | Core Header | Central C11 interface header declaring `transport_t`, `ipc_bench_opts_t`, standard run signatures, inline `set_cpu_affinity()`, and constants. |
| `include/spsc_ring.h` | Header (Remote) | Lock-free Single-Producer Single-Consumer cache-aligned circular ring buffer header. |
| `src/main.c` | Core CLI Application | Main CLI runner (`mini-aipc`) providing transport selection, argument parsing, high-resolution monotonic timing, nearest-rank percentile calculations, and CSV output. |
| `src/ipc_pipe.c` | IPC Implementation | Anonymous unidirectional pipe pair (`pipe()`) providing full-duplex request-response communication between parent and child processes. |
| `src/ipc_fifo.c` | IPC Implementation | Named pipes (`mkfifo()`) in `/tmp` with `0600` permissions, deadlock-free open order, and standalone CLI executable (`bin/ipc_fifo`). |
| `src/ipc_shm.c` | IPC Implementation | POSIX shared memory (`shm_open`, `mmap`) with POSIX unnamed semaphores, cache-line aligned mailbox, and child exit fault monitoring. |
| `src/ipc_sysv_mq.c` | IPC Implementation | System V message queue (`msgget(IPC_PRIVATE)`, `msgsnd`, `msgrcv`, `msgctl(IPC_RMID)`) using message types (`mtype`) for request-response multiplexing. |
| `src/ipc_posix_mq.c` | IPC Implementation | POSIX message queues (`mq_open`, `mq_send`, `mq_receive`, `mq_unlink`) in `/dev/mqueue` with dynamic sizing. |
| `src/ipc_uds.c` | IPC Implementation | Unix Domain Stream Sockets (`socket(AF_UNIX, SOCK_STREAM)`, `bind`, `listen`, `accept`, `connect`) in `/tmp`. |
| `src/selector.c` | Adaptive Selector | Payload-size based routing (`select_transport`) and telemetry-driven EWMA adaptive controller (`select_transport_adaptive`). |
| `src/mixed_benchmark.c` | Benchmark CLI | Mixed workload simulator (`mini-aipc-mixed`) generating mixed payload distributions (e.g., 80% small, 20% large). |
| `src/ipc_spsc_ring.c` | IPC Optimization (Remote) | Experimental zero-syscall lock-free SPSC shared memory queue using atomic head/tail indices. |
| `src/concurrency_benchmark.c`| Benchmark CLI (Remote) | Native multi-process concurrency harness (`mini-aipc-concurrency`) measuring multi-producer/multi-consumer scaling (1:1, 2:1, 4:1, 1:2, 4:4). |
| `kernel/aipc_module.c` | Linux Kernel Module | Bounded kernel-space character device (`/dev/aipc`) with circular ring buffer, wait queues, mutex synchronization, non-blocking I/O, and poll support. |
| `kernel/Makefile` | Kernel Build | Standard Kbuild Makefile compiling `aipc.ko` against `/lib/modules/$(uname -r)/build`. |
| `user/aipc_client.c` | Kernel Test Utility | User-space client reading/writing `/dev/aipc` with payload validation and timing. |
| `bench/` | Benchmark Framework | Contains trial orchestrators, system-call profilers, statistical analysis scripts, and visualization generators. |
| `tests/` | Test Suite | Contains regression verification (`final_verification_test.py`), shell CLI tests (`test_cli.sh`), pytest benchmark tests (`test_unified_benchmark.py`), and kernel tests (`tests/kernel/`). |
| `docs/` | Research Documentation | Architecture designs, viva questions, benchmark methodologies, fairness analyses, and implementation reports. |
| `results/` | Benchmark Datasets | Contains historical comparative CSVs, system-call profiles, and unified run snapshots. |
| `Paper.pdf` | Research Reference | Published academic paper (*Danyliuk I.M., SWorldJournal Issue 37, Part 2, 2026: Classical Interprocess Communication Mechanisms in Linux OS: Review and Latency Analysis for HPC Scenarios*). |

---

## 3. Detailed Component Audit & Existing Functionality

### 3.1 Six Userspace IPC Mechanisms
- **Anonymous Pipes (`src/ipc_pipe.c`)**:
  - Implements bidirectional ping-pong via dual pipe descriptors (`request_pipe` and `response_pipe`).
  - Correctly closes unused descriptor ends in both parent and child.
  - Implements `write_all()` and `read_all()` loops handling partial transfers, `EINTR`, and EOF.
  - Ignores `SIGPIPE` with `sigaction`, preventing abnormal termination when peers disconnect.
- **Named Pipes / FIFOs (`src/ipc_fifo.c`)**:
  - Uses private FIFO nodes in `/tmp/mini_aipc_req_<pid>.fifo` and `/tmp/mini_aipc_resp_<pid>.fifo` with secure `0600` permissions.
  - Open sequence prevents FIFO open deadlocks: child opens `req` RDONLY then `resp` WRONLY; parent opens `req` WRONLY then `resp` RDONLY.
  - Standalone binary `bin/ipc_fifo` compiles independently for standalone demonstration.
  - Clean `unlink()` removes FIFO nodes on both normal and error exit paths.
- **POSIX Shared Memory (`src/ipc_shm.c`)**:
  - Uses `shm_open()` with `O_CREAT | O_EXCL | 0600`, `ftruncate()`, and `mmap(MAP_SHARED)`.
  - Four POSIX unnamed semaphores (`request_empty`, `request_full`, `response_empty`, `response_full`) synchronize lockstep access.
  - Cache-line alignment (`_Alignas(64)`) isolates semaphores and payload buffers to prevent false sharing across CPU cores.
  - Maximum payload size is enforced at `SHM_MAX_PAYLOAD = 1024` bytes. Payloads > 1024 bytes are rejected safely.
  - Teardown performs `munmap()`, `close()`, and `shm_unlink()`.
- **System V Message Queues (`src/ipc_sysv_mq.c`)**:
  - Uses `msgget(IPC_PRIVATE, IPC_CREAT | IPC_EXCL | 0600)` to ensure completely private queues.
  - Multiplexes request (`mtype = 1`) and response (`mtype = 2`) over a single message queue.
  - Installs a `SIGCHLD` handler without `SA_RESTART` to break blocking `msgrcv()` on child death.
  - Destroys queue on exit via `msgctl(msqid, IPC_RMID, NULL)`.
  - *Platform Note*: Fails with `ENOSYS` ("Function not implemented") under MSYS2 POSIX emulation on Windows. Functions normally on Linux.
- **POSIX Message Queues (`src/ipc_posix_mq.c`)**:
  - Creates `/mini_aipc_req_<pid>` and `/mini_aipc_resp_<pid>` in `/dev/mqueue` with `mq_open()`.
  - Configures `mq_maxmsg = 10` (unprivileged Linux ceiling) and dynamic `mq_msgsize = payload_size`.
  - Cleans up descriptors with `mq_close()` and unlinks nodes via `mq_unlink()`.
- **Unix Domain Sockets (`src/ipc_uds.c`)**:
  - Creates stream socket pair using `socket(AF_UNIX, SOCK_STREAM, 0)`.
  - Binds and listens before `fork()` to ensure race-free connection rendezvous.
  - Robust byte streaming through `send_all()` and `recv_all()`.
  - Cleans up socket special file via `unlink()`.

### 3.2 Adaptive IPC Selector (`src/selector.c`)
- **Static Threshold Selection**: `select_transport(payload_size, threshold)` routes payloads $\le \text{threshold}$ (and $\le 1024$ B) to `shm`, and larger payloads to `pipe`.
- **Telemetry EWMA Adaptive Controller**: In `origin/main`, tracks exponential moving average latencies for SHM and Pipe with an 8% hysteresis threshold to avoid flapping.

### 3.3 Linux Kernel Module (`kernel/aipc_module.c`)
- **Character Device Registration**: Uses `alloc_chrdev_region()`, `cdev_init()`, `cdev_add()`, `class_create()`, `device_create()` to expose `/dev/aipc`.
- **Circular Buffer**: Dynamically allocated ring buffer (`kmalloc`) with configurable capacity (`module_param`).
- **Synchronization**: `mutex_lock_interruptible()` protects buffer pointers (`head`, `tail`, `used`).
- **Wait Queues**: Readers wait on `readers` queue when buffer is empty; writers wait on `writers` queue when buffer is full.
- **Non-blocking & Poll**: Honors `O_NONBLOCK` returning `-EAGAIN`; implements `aipc_poll()` returning `EPOLLIN` / `EPOLLOUT`.
- **Kernel Version Compatibility**: Fixed Linux 6.12+ VFS incompatibility by replacing obsolete `no_llseek` with `noop_llseek`.

---

## 4. Identified Defects, Inconsistencies & Technical Gaps

### 4.1 Git Branch Divergence
- **Local Branch**: `main` at commit `27817c9` ("Fixes 3").
- **Remote Tracking**: `origin/main` at commit `726bce0` ("test"), 10 commits ahead.
- **Divergence Cause**: Remote commits (`c2aef79` through `726bce0`) implemented unified benchmarking, SPSC lock-free queues, native concurrency benchmarks, and Fedora experimental results. Meanwhile, local working tree added alternative benchmark orchestrators (`unified_bench.c`, `orchestrate_unified.py`, etc.) and modified the `Makefile`.
- **Reconciliation Requirement**: Must reconcile remote commits without deleting or silently losing local unique implementations.

### 4.2 Kernel Module Teardown Race Condition (P1 Defect)
- In `kernel/aipc_module.c:aipc_exit()`:
  ```c
  wake_up_interruptible_all(&aipc->readers);
  wake_up_interruptible_all(&aipc->writers);
  kfree(aipc->buffer);
  kfree(aipc);
  aipc = NULL;
  ```
  Immediately after waking up sleeping readers/writers, `kfree(aipc)` is executed before waking threads can finish exiting the driver. If a thread wakes up and evaluates `READ_ONCE(aipc->shutdown)` or touches `aipc->lock`, a Use-After-Free (UAF) kernel panic occurs.
  *Remediation*: Module refcount (`cdev.owner = THIS_MODULE`) prevents normal `rmmod` while file descriptors are open, but defensive shutdown must use completion barriers or atomic open-count draining to eliminate race conditions completely.

### 4.3 Environment-Dependent Test Flaws
- In `tests/final_verification_test.py:26`:
  `bash_path = shutil.which('bash') or r'C:\Program Files\Git\bin\bash.exe'`
  On Windows systems where WSL is registered but not initialized, `shutil.which('bash')` selects `C:\Windows\System32\bash.exe`. Executing this prints an error ("Windows Subsystem for Linux must be updated..."), causing test 1 to fail even though MSYS2 and Git Bash are installed and functional.
  *Remediation*: Detect and bypass `System32\bash.exe`, prioritizing MSYS2 `/usr/bin/bash.exe` or Git `bash.exe`.

- In `tests/test_cli.sh`:
  `test_cli.sh` unconditionally tests System V message queues. On Windows/MSYS2, `msgget()` returns `ENOSYS`. The script aborts with `FAIL: sysv correctness`.
  *Remediation*: Check OS environment or handle `ENOSYS` gracefully on MSYS2 while strictly enforcing `PASS` on Linux.

### 4.4 Shared Memory 1,024-Byte Payload Boundary
- `SHM_MAX_PAYLOAD` is fixed at 1,024 bytes.
- Attempting to run `./mini-aipc --mode shm --size 4096` fails with `EINVAL`.
- The adaptive selector properly routes payloads > 1,024 bytes to `pipe`, but documentation must consistently clarify that this is a deliberate design boundary for bounded low-latency mailboxes rather than an arbitrary bug.

### 4.5 Benchmark Dataset Provenance & Environmental Isolation
- The repository contains experimental datasets from different environments:
  1. `results/comparative_benchmark.csv`: Ubuntu 26.04 on WSL2 (AMD Ryzen 7 8845HS).
  2. `results/unified/raw/` on `origin/main`: Fedora 45 Linux 7.3.3 native (Intel Core 7 240H).
  3. `results/unified/runs/` local untracked: MSYS2 / Windows runs (`exp_20261111T153614Z_392` and `exp_20261111T154018Z_2004`).
- *Strict Rule*: These datasets must remain segregated by unique experiment IDs and environment descriptors. They must never be merged or conflated.

---

## 5. Duplicate and Superfluous Files Analysis

| File / Pattern | Status | Recommendation |
|---|---|---|
| `mini-aipc`, `mini-aipc-mixed`, `aipc-client`, `bin/ipc_fifo` (tracked ELF binaries) | Tracked Unix binaries in Git index | Remove compiled binaries from Git index; ensure `.gitignore` excludes executables. |
| `*.exe` (`mini-aipc.exe`, `mini-aipc-mixed.exe`, etc.) | Untracked build artifacts | Exclude via `.gitignore`. |
| `bench/.backup_pre_unified/` | Untracked backup directory | Archive or preserve as reference; do not let it clutter build. |
| `__pycache__/` | Python bytecode cache | Exclude via `.gitignore`. |
| `tests/__pycache__/` | Pytest bytecode cache | Exclude via `.gitignore`. |

---

## 6. Authoritative Source Files vs. Generated Outputs

### Authoritative Source Files
- **C Source**: `src/main.c`, `src/ipc_pipe.c`, `src/ipc_fifo.c`, `src/ipc_shm.c`, `src/ipc_sysv_mq.c`, `src/ipc_posix_mq.c`, `src/ipc_uds.c`, `src/selector.c`, `src/mixed_benchmark.c`, `src/ipc_spsc_ring.c`, `src/concurrency_benchmark.c`, `user/aipc_client.c`.
- **Headers**: `include/ipc.h`, `include/spsc_ring.h`.
- **Kernel**: `kernel/aipc_module.c`, `kernel/Makefile`.
- **Build**: `Makefile`.
- **Tests**: `tests/test_cli.sh`, `tests/final_verification_test.py`, `tests/test_unified_benchmark.py`, `tests/kernel/test_device.sh`, `tests/kernel/test_load_unload.sh`.
- **Benchmark Engines**: `bench/run_unified_benchmark.sh`, `bench/process_unified_results.py`, `bench/unified_bench.c`, `bench/orchestrate_unified.py`, `bench/analyze_results.py`, `bench/generate_graphs.py`, `bench/generate_report.py`.

### Generated Outputs (Artifacts)
- **Executables**: `mini-aipc`, `mini-aipc-mixed`, `mini-aipc-concurrency`, `aipc-client`, `bin/ipc_fifo`, `bin/aipc_unified_bench`.
- **Processed Benchmark CSVs**: `results/unified/processed/aggregated_results.csv`, `results/unified/processed/statistical_summary.csv`.
- **Metadata**: `results/unified/processed/benchmark_metadata.json`, `results/unified/environment.txt`.
- **Visualizations**: 13 generated PNG/PDF charts in `results/unified/graphs/`.
- **Reports**: `results/unified/reports/FINAL_BENCHMARK_REPORT.md`.

---

## 7. Submission Risks & Action Plan

| Risk Level | Risk Description | Remediation Plan |
|---|---|---|
| **High** | Git branch divergence (10 commits behind origin) | Perform non-destructive reconciliation preserving local files. |
| **High** | Kernel module UAF during unload | Harden `aipc_exit()` synchronization. Document WSL2 vs bare-metal validation. |
| **Medium** | MSYS2 System V `ENOSYS` handling | Preserve genuine Linux SysV MQ implementation; document platform limitation. |
| **Medium** | Documentation inconsistencies | Align all Markdown documentation with actual measured data and limits. |
| **Low** | Leaked temporary files or missing `.gitignore` | Create comprehensive root `.gitignore` excluding all build artifacts and caches. |

---
*End of Final Repository Audit (Phase 0).*
