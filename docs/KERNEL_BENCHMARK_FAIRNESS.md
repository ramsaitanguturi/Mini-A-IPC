# Mini-A-IPC: Kernel Mailbox Benchmark Fairness and Equivalence Audit

## 1. Executive Summary

During full benchmark evaluation on Fedora Linux (Linux kernel 7.2.15/7.3.3, KVM virtualized), the experimental kernel character device (`/dev/aipc`) reported round-trip latencies between **0.66 us and 2.59 us** (throughput exceeding 1,200,000 msg/s). Concurrently, user-space IPC mechanisms (Anonymous Pipes, Named Pipes, System V Message Queues, POSIX Message Queues, Shared Memory with semaphores, and Unix Domain Sockets) exhibited round-trip latencies clustered between **95 us and 175 us** (throughput ~5,000–9,000 msg/s).

This audit investigates the scientific validity and equivalence of comparing these measurements. It establishes that **the kernel character device loopback benchmark and the user-space inter-process benchmarks evaluate fundamentally different architectural boundaries**. Direct comparison without scientific qualification is invalid for academic evaluation.

---

## 2. Measurement-Equivalence Audit (10-Point Analysis)

The table below audits the 10 operational dimensions across all 8 Mini-A-IPC components:

| Audit Dimension | Anonymous Pipes | Named Pipes (FIFO) | SysV Message Queue | POSIX Message Queue | POSIX SHM + Semaphores | Unix Domain Sockets | Kernel Mailbox (`/dev/aipc`) |
|---|---|---|---|---|---|---|---|
| **1. What constitutes one exchange?** | Parent writes req, Child reads req, Child writes echo, Parent reads echo | Parent writes req, Child reads req, Child writes echo, Parent reads echo | Parent sends req, Child receives req, Child sends resp, Parent receives resp | Parent sends req, Child receives req, Child sends resp, Parent receives resp | Parent writes SHM, signals sem, Child wakes, copies, signals sem, Parent wakes | Parent writes req, Child reads req, Child writes echo, Parent reads echo | Process writes payload to `/dev/aipc`, immediately reads back from ring buffer |
| **2. One-way or Round-trip?** | Complete Round-Trip (Ping-Pong) | Complete Round-Trip (Ping-Pong) | Complete Round-Trip (Ping-Pong) | Complete Round-Trip (Ping-Pong) | Complete Round-Trip (Ping-Pong) | Complete Round-Trip (Ping-Pong) | Complete Syscall Round-Trip (Driver Loopback) |
| **3. Inter-process synchronization included?** | Yes (Pipe blocking read/write wait queues) | Yes (FIFO blocking read/write wait queues) | Yes (SysV kernel queue wait queues) | Yes (POSIX mqueue kernel wait queues) | Yes (Process-shared semaphores / futex wait/wake) | Yes (Socket stream buffer wait queues) | **No** (Single process; no partner process synchronization) |
| **4. System calls included?** | 4 syscalls (`write`, `read`, `write`, `read`) | 4 syscalls (`write`, `read`, `write`, `read`) | 2 syscalls (`msgsnd`, `msgrcv`) | 2 syscalls (`mq_send`, `mq_receive`) | 2-4 syscalls (`futex` wait/wake on contention) | 4 syscalls (`write`, `read`, `write`, `read`) | 2 syscalls (`write`, `read`) |
| **5. User-to-kernel copy?** | Yes (2 times: req + resp) | Yes (2 times: req + resp) | Yes (2 times: req + resp) | Yes (2 times: req + resp) | **No** (Zero-copy in shared memory) | Yes (2 times: req + resp) | Yes (1 time: `copy_from_user` in driver) |
| **6. Kernel-to-user copy?** | Yes (2 times: req + resp) | Yes (2 times: req + resp) | Yes (2 times: req + resp) | Yes (2 times: req + resp) | **No** (Zero-copy in shared memory) | Yes (2 times: req + resp) | Yes (1 time: `copy_to_user` in driver) |
| **7. Echo response generation?** | Yes (Child process receives and echoes payload) | Yes (Child process receives and echoes payload) | Yes (Child process receives and echoes payload) | Yes (Child process receives and echoes payload) | Yes (Child process reads request, writes response) | Yes (Child process receives and echoes payload) | **No** (Kernel ring buffer retains bytes; reader drains same buffer) |
| **8. Payload validation?** | Yes (Parent validates returned byte pattern) | Yes (Parent validates returned byte pattern) | Yes (Parent validates returned byte pattern) | Yes (Parent validates returned byte pattern) | Yes (Parent validates returned byte pattern) | Yes (Parent validates returned byte pattern) | Yes (Process verifies read bytes match written bytes) |
| **9. Process wakeups & scheduling?** | **Yes (2 context switches per round trip)** | **Yes (2 context switches per round trip)** | **Yes (2 context switches per round trip)** | **Yes (2 context switches per round trip)** | **Yes (2 context switches per round trip)** | **Yes (2 context switches per round trip)** | **No (0 context switches; single process remains running)** |
| **10. Setup / cleanup included in timed loop?** | No (Excluded; allocated before timing loop) | No (Excluded; allocated before timing loop) | No (Excluded; allocated before timing loop) | No (Excluded; allocated before timing loop) | No (Excluded; allocated before timing loop) | No (Excluded; allocated before timing loop) | No (Excluded; opened before timing loop) |

---

## 3. Root Cause of the Latency Discrepancy

### 3.1 The Process Scheduling and Context-Switch Floor (~95–120 us)
Every user-space IPC mechanism in Mini-A-IPC operates between **two distinct processes**:
1. Process 1 (Producer, pinned to Core 0) sends a message and blocks.
2. The Linux kernel scheduler transitions Process 1 to `TASK_INTERRUPTIBLE`, signals the partner, and invokes `schedule()`.
3. In a virtualized KVM environment, the hypervisor vCPU must be dispatched, triggering virtual machine exits (VM-exits) and translation lookaside buffer (TLB) flushes.
4. Process 2 (Consumer, pinned to Core 1) awakens, handles the message, enqueues the response, and blocks.
5. A second context switch and scheduling event returns execution to Process 1.

Across 7 trials and 70,000 exchanges on the Fedora VM, the median round-trip context switch floor was measured at **95.27 us to 118.60 us**. This scheduling latency accounts for **>95% of total user-space round-trip time**.

### 3.2 Pure Driver Loopback in `/dev/aipc` (0.66–2.59 us)
The character device `/dev/aipc` is implemented in `kernel/aipc_module.c` as a single shared 64 KiB circular ring buffer.
In `bench/benchmark_kernel_runner.py`:
- A single process opens `/dev/aipc`.
- The process calls `write(fd, payload, size)`. The kernel module acquires `mutex_lock(&aipc->lock)`, executes `copy_from_user()`, increments `tail`, and releases the mutex.
- The process immediately calls `read(fd, buffer, size)`. The kernel module acquires `mutex_lock(&aipc->lock)`, executes `copy_to_user()`, increments `head`, and releases the mutex.
- Because the same thread writes and reads:
  - **Zero context switches occur.**
  - **Zero process scheduler invocations occur.**
  - **Zero inter-core cache invalidations occur.**
  - The measurement purely captures **system call overhead and kernel memory copy latency**.

Each `read()` or `write()` system call on x86_64 takes ~300 nanoseconds. Two system calls plus small memcpy operations total **~680 nanoseconds (0.68 us)**.

---

## 4. Multi-Process Concurrency Evaluation

To evaluate `/dev/aipc` under true multi-process execution matching the other components, Mini-A-IPC provides `mini-aipc-concurrency`:
- Multiple concurrent producers write distinct message blocks into `/dev/aipc`.
- Multiple concurrent consumers drain the kernel buffer.
- Under this multi-process workload, `/dev/aipc` throughput scales dynamically with available CPU cores, demonstrating the performance of the kernel mutex and wait queues.

---

## 5. Scientific Recommendations for Academic Presentation

When presenting Mini-A-IPC results in papers, presentations, or project vivas:

1. **Do not claim the kernel module is 150x faster than user-space IPC:**
   Explain transparently that the single-process test benchmarks kernel character driver entry/exit overhead, whereas the user-space benchmark benchmarks full inter-process communication including operating system process scheduling.
2. **Present them under separate headings:**
   - *Section A: Comparative Inter-Process Communication (Pipes vs FIFO vs SysV vs POSIX MQ vs SHM vs UDS)*
   - *Section B: Kernel-Space Character Driver Mailbox (/dev/aipc Syscall & Copy Overhead)*
3. **Disclose Environment Constraints:**
   Explicitly declare that tests were executed in a virtual machine (KVM on Intel Core 7 240H), where hypervisor vCPU scheduling amplifies inter-process context switch times compared to bare-metal hardware.

