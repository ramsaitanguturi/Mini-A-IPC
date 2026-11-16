# Mini-A-IPC: Known Technical Limitations, Blockers & System Constraints

## 1. Operating System & Subsystem Discrepancies

### 1.1 MSYS2 / Cygwin POSIX Emulation (Windows Host)
- **System V IPC Syscalls Return `ENOSYS`**:
  Under MSYS2 on Windows, the System V IPC functions (`msgget`, `msgsnd`, `msgrcv`, `msgctl`) are stubs that return `-1` with `errno = ENOSYS` ("Function not implemented") unless the standalone Windows service daemon `cygserver` is installed and actively running in the background.
  - *Handling in Mini-A-IPC*: Test suites detect `ENOSYS` on MSYS2 and mark the test as `SKIP` with an informative message rather than failing. On native Linux and WSL2, the implementation is fully tested and passes.
- **Absence of Linux Kernel Development Headers**:
  The MSYS2 environment does not run a native Linux kernel. Consequently, out-of-tree kernel modules (`kernel/aipc_module.c`) cannot be compiled or loaded on Windows/MSYS2. Exact verification instructions and reproduction commands for native Linux are provided in `docs/KERNEL_MODULE_VALIDATION.md`.

### 1.2 Virtual Machine & Hypervisor Schedulers (WSL2 / Guest VMs)
- **Context-Switch Latency Floor**:
  In virtualized guest environments (such as WSL2 or KVM virtual machines), thread yield and inter-processor interrupts (IPI) must cross the hypervisor boundary. This produces an artificial latency floor of **95–120 $\mu\text{s}$** (and up to $280\,\mu\text{s}$ on heavily loaded hosts). This floor dwarfs data-copy differences for small messages ($\le 1\text{ KB}$).
- **Trial-to-Trial Scheduling Jitter**:
  Host operating system background tasks (such as Windows Update, antimalware scans, or IDE indexing) can cause transient vCPU pauses. This accounts for sporadic trial latency spikes (e.g. Trial 2 in the Fedora dataset).

---

## 2. Implementation-Specific Constraints

### 2.1 POSIX Shared Memory Mailbox Bounded Payload (`SHM_MAX_PAYLOAD`)
- **Bounded Buffer Design**:
  The shared memory implementation uses a statically sized mailbox structure with `SHM_MAX_PAYLOAD = 1,024` bytes. Payloads exceeding 1,024 bytes are rejected with `errno = EMSGSIZE`.
  - *Rationale*: A fixed-size shared mailbox enables deterministic zero-copy memory transfers without dynamic runtime memory management or complex variable-length ring allocation.
  - *Mitigation*: The Adaptive Selector automatically detects payloads $> 1024$ bytes and routes them to Anonymous Pipes or Unix Domain Sockets.

### 2.2 Pipe Buffer Capacity (64 KB Linux Default)
- **Kernel Buffer Saturation at $\ge 256$ KB**:
  On standard Linux distributions, pipe capacity defaults to 16 memory pages ($65,536\text{ B}$). Payloads of 256 KB require multiple chunked writes and reads, resulting in multiple blocking context switches.
  - *Recommendation*: For payloads $\ge 256\text{ KB}$, use Unix Domain Sockets (`AF_UNIX`) or resize the pipe buffer via `fcntl(fd, F_SETPIPE_SZ, ...)`.

### 2.3 Single-Producer Single-Consumer (SPSC) Mailbox Model
- **Concurrency Limitation in SHM**:
  The single shared mailbox structure (`shared_mailbox_t`) in `src/ipc_shm.c` is strictly SPSC. Attempting to run multi-producer or multi-consumer workloads across a single mailbox causes race conditions unless external mutex locking or separate per-channel mailboxes are provisioned.
  - *Handling*: Multi-producer multi-consumer tests (`mini-aipc-concurrency`) correctly mark SHM as `UNSUPPORTED` (`rc=3`), while POSIX Message Queues and Unix Domain Sockets handle M:N scaling seamlessly.

---

## 3. Tooling & Profiling Limitations

### 3.1 `strace` Availability
- System-call profiling requires the Linux `strace` utility. On hosts where `strace` is not installed or when running under Windows/MSYS2, system call classification is based on static analysis of the source code, and runtime `strace` validation is reported as `PENDING` / `SKIPPED`.

