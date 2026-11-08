# Mini A-IPC: Archived Experimental Datasets

This directory contains preserved historical benchmark datasets to ensure reproducibility, scientific auditability, and clear separation between long-running multi-trial experiments and rapid verification runs.

## Archived Datasets

### 1. `comparative_benchmark_10k_5trials.csv`
- **Workload**: 10,000 request-response round-trip exchanges per trial
- **Trials**: 5 independent runs per mechanism and payload size (150 total data rows)
- **Warm-up**: 500 untimed exchanges per run
- **Payload Sizes**: 64, 128, 256, 512, 1024 bytes
- **Mechanisms**: Anonymous Pipes (`pipe`), Named Pipes (`fifo`), System V MQ (`sysv`), POSIX MQ (`posix`), Shared Memory (`shm`), Unix Domain Sockets (`uds`)
- **CPU Affinity**: Producer pinned to CPU 0, Consumer pinned to CPU 1 via `sched_setaffinity()`
- **Hardware / Subsystem**: AMD Ryzen 7 8845HS (16 vCPUs), Ubuntu 26.04 LTS on Microsoft WSL2 (Kernel 6.6.87.2-microsoft-standard-WSL2). Captured in `environment_10k_5trials.txt`.

## Provenance and Environmental Integrity Note
- All empirical data recorded in this repository represents genuine measurements from the documented testbed.
- **Never conflate environments**: These results were produced on the AMD Ryzen 7 8845HS / WSL2 Ubuntu 26.04 environment. They must never be described as bare-metal Debian/KVM or Fedora results.
- Active and quick verification runs are stored in the parent `results/` directory (`results/comparative_benchmark.csv` and `results/syscall_benchmark.csv`).

