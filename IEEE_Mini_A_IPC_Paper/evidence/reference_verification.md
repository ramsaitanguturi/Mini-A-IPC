# Mini-A-IPC: Academic Reference Verification & Bibliographic Audit

Every citation included in the Mini-A-IPC research paper has been verified against legitimate academic journals, conference proceedings, operating system specifications, and canonical technical references. No DOIs, authors, publication years, or venues have been fabricated.

---

## 1. Canonical Reference List

### Ref [1]: Baseline Experimental Paper
- **Citation**: I. M. Danyliuk, "Classical Interprocess Communication Mechanisms in Linux OS: Review and Latency Analysis for HPC Scenarios," *SWorldJournal*, Issue 37, Part 2, pp. 68–77, 2026.
- **Verification Status**: **VERIFIED**. Preserved locally in the repository root as `Paper.pdf`. Covers latency analysis of Linux IPC mechanisms (Pipes, FIFOs, POSIX MQ, SysV MQ, SHM, UDS) in HPC environments.

### Ref [2]: Operating Systems Principles
- **Citation**: A. Silberschatz, P. B. Galvin, and G. Gagne, *Operating System Concepts*, 10th ed. Hoboken, NJ, USA: John Wiley & Sons, 2018.
- **Verification Status**: **VERIFIED**. Standard reference for process management, IPC taxonomies (message passing vs shared memory), and synchronization.

### Ref [3]: Linux Systems Programming
- **Citation**: M. Kerrisk, *The Linux Programming Interface: A Linux and UNIX System Programming Handbook*. San Francisco, CA, USA: No Starch Press, 2010.
- **Verification Status**: **VERIFIED**. Comprehensive reference for `pipe()`, `mkfifo()`, `shm_open()`, `mmap()`, `msgget()`, `mq_open()`, Unix domain sockets, and kernel buffer parameters (`PIPE_BUF`, `msg_max`).

### Ref [4]: Linux Kernel Architecture & Development
- **Citation**: R. Love, *Linux Kernel Development*, 3rd ed. Upper Saddle River, NJ, USA: Addison-Wesley, 2010.
- **Verification Status**: **VERIFIED**. Reference for Linux kernel module development, character devices, sleepable mutexes, wait queues (`wait_event_interruptible`), and VFS file operations.

### Ref [5]: Advanced Linux Kernel Internals
- **Citation**: D. P. Bovet and M. Cesati, *Understanding the Linux Kernel*, 3rd ed. Sebastopol, CA, USA: O'Reilly Media, 2005.
- **Verification Status**: **VERIFIED**. Detailed treatment of Linux VFS, pipe buffers (`struct pipe_inode_info`), memory-mapped pages, and page faults.

### Ref [6]: POSIX Specification
- **Citation**: IEEE and The Open Group, *Standard for Information Technology—Portable Operating System Interface (POSIX(R)) Base Specifications, Issue 7*, IEEE Std 1003.1-2017, 2018.
- **Verification Status**: **VERIFIED**. Defines POSIX message queues (`mqueue.h`), POSIX shared memory (`sys/mman.h`), and POSIX semaphores (`semaphore.h`).

### Ref [7]: Unix Network Programming
- **Citation**: W. R. Stevens, B. Fenner, and A. M. Rudoff, *UNIX Network Programming, Volume 1: The Sockets Networking API*, 3rd ed. Boston, MA, USA: Addison-Wesley, 2004.
- **Verification Status**: **VERIFIED**. Canonical authority on Unix Domain Sockets (`AF_UNIX`), stream sockets (`SOCK_STREAM`), socket buffers, and socket descriptor passing.

### Ref [8]: Interprocess Communication Architecture
- **Citation**: W. R. Stevens, *UNIX Network Programming, Volume 2: Interprocess Communications*, 2nd ed. Upper Saddle River, NJ, USA: Prentice Hall, 1999.
- **Verification Status**: **VERIFIED**. Classic reference dedicated specifically to Pipes, FIFOs, System V IPC, POSIX IPC, and shared memory synchronization.

### Ref [9]: Modern Multicore Synchronization
- **Citation**: M. Herlihy and N. Shavit, *The Art of Multiprocessor Programming*, 2nd ed. Cambridge, MA, USA: Morgan Kaufmann, 2020.
- **Verification Status**: **VERIFIED**. Theoretical foundation for Single-Producer Single-Consumer (SPSC) lock-free ring buffers, cache-line alignment, and acquire/release memory consistency.

### Ref [10]: IPC Performance in Microkernel and Virtualized Environments
- **Citation**: J. Liedtke, "On micro-kernel construction," in *Proc. 15th ACM Symp. Operating Systems Principles (SOSP)*, Copper Mountain, CO, USA, 1995, pp. 237–250.
- **Verification Status**: **VERIFIED**. Foundational paper on IPC optimization, context switching overheads, and hardware cache penalties during process communication.

### Ref [11]: Linux Tracing and Performance Tools
- **Citation**: B. Gregg, *Systems Performance: Enterprise and the Cloud*, 2nd ed. Boston, MA, USA: Addison-Wesley, 2020.
- **Verification Status**: **VERIFIED**. Reference for CPU profiling, context switches, system-call tracing (`strace`), and latency percentile analysis ($P_{50}, P_{95}, P_{99}$).

### Ref [12]: Linux Kernel Documentation
- **Citation**: Linux Kernel Organization, "The Linux Kernel Documentation," 2026. [Online]. Available: https://www.kernel.org/doc/html/latest/
- **Verification Status**: **VERIFIED**. Reference for VFS file operations, character device allocation, and kernel 6.x/7.x API evolution (e.g., `noop_llseek` replacing deprecated `no_llseek`).
