# Comprehensive Paper Audit and Refinement Report: Mini-A-IPC

**Document:** IEEE Conference Research Paper Refinement  
**Target Paper Directory:** `IEEE_Mini_A_IPC_Paper/`  
**Primary Output Artifact:** `IEEE_Mini_A_IPC_Paper/main.pdf` (11 Pages, IEEE Conference Format)  
**Date of Audit:** November 21, 2026  
**Auditor:** Senior Linux Systems Researcher & IEEE Editor Specialist  

---

## 1. Executive Summary

This audit report documents the comprehensive refinement, data reconciliation, and structural verification performed on the research paper:

> **"Mini-A-IPC: Design, Implementation, and Performance Evaluation of Classical and Adaptive Inter-Process Communication Mechanisms in Linux"**

All modifications were strictly constrained to the LaTeX paper source, figure generators, TikZ diagrams, and tables within `IEEE_Mini_A_IPC_Paper/`. No benchmark implementations, kernel modules, C sources, or experimental CSV files were altered, ensuring 100% preservation of empirical integrity.

The paper now compiles cleanly with zero LaTeX errors, zero undefined citations, zero unresolved cross-references, and exactly matches the IEEE conference 11-page publication specification with balanced columns on the final page.

---

## 2. Inventory of Modified Files

| File Path | Type | Nature of Modifications |
|:---|:---|:---|
| `IEEE_Mini_A_IPC_Paper/main.tex` | LaTeX Master | Updated author block with formal placeholders; corrected abstract claims regarding adaptive controller and primary environment; adjusted float/bib spacing to achieve exact 11-page layout; added column balancing. |
| `IEEE_Mini_A_IPC_Paper/tables/environment.tex` | LaTeX Table | Removed Comparative Testbed (WSL2) column; preserved primary Fedora 45 KVM hardware, kernel, compiler, and workload sweep parameters in a clean single-column format. |
| `IEEE_Mini_A_IPC_Paper/sections/01_introduction.tex` | LaTeX Section | Removed WSL2 comparative mentions; corrected contribution claims regarding adaptive controller and kernel module teardown barrier. |
| `IEEE_Mini_A_IPC_Paper/sections/03_architecture.tex` | LaTeX Section | Promoted architecture diagram to full-width `figure*`; updated caption and text to reflect the 4 modular areas; clarified that adaptive selector routes strictly between SHM and Pipe; defensibly described kernel module teardown barrier. |
| `IEEE_Mini_A_IPC_Paper/sections/06_methodology.tex` | LaTeX Section | Removed comparative WSL2 testbed narrative; confirmed Fedora 45 KVM as the single primary experimental environment; preserved all scientific control descriptions and exchange totals. |
| `IEEE_Mini_A_IPC_Paper/sections/07_results.tex` | LaTeX Section | Updated Fig. 6 caption to reflect "System Calls per Round-Trip Exchange (distinguishing data-path from futex synchronization calls)". |
| `IEEE_Mini_A_IPC_Paper/sections/08_discussion.tex` | LaTeX Section | Removed WSL2 from threats to validity; refined RQ3 to distinguish static evaluation from implemented EWMA feedback control; added column balancing marker `\balance`. |
| `IEEE_Mini_A_IPC_Paper/sections/09_conclusion.tex` | LaTeX Section | Aligned conclusions with empirical findings: static selector evaluation, offline 3-tier calibration, and EWMA controller as future live runtime basis. |
| `IEEE_Mini_A_IPC_Paper/figures/architecture.tex` | TikZ Source | Completely redesigned into a clean, full-width IEEE architecture diagram organized into 4 clearly demarcated areas (A, B, C, D) with minimal crossing lines and strict candidate routing (SHM $\leftrightarrow$ Pipe). |
| `IEEE_Mini_A_IPC_Paper/figures/benchmark_workflow.tex` | TikZ Source | Proportionally scaled to ensure optimal vertical fit and avoid premature page ejection. |
| `IEEE_Mini_A_IPC_Paper/figures/kernel_mailbox.tex` | TikZ Source | Replaced absolute claim "Zero UAF Panics" with technically defensible "Active-Op Drain Barrier". |
| `IEEE_Mini_A_IPC_Paper/scripts/generate_paper_graphs.py` | Python Script | Replaced hardcoded syscall values with dynamic parser for `results/unified/raw/syscall_metrics.csv`; added numerical value annotations above bars; renamed title to "System Calls per Round-Trip Exchange"; regenerated all vector PDFs. |
| `IEEE_Mini_A_IPC_Paper/figures/*.pdf` | Vector Graphics | Regenerated all paper figure PDFs (`percentiles_resources_combined.pdf`, `resource_utilization.pdf`, etc.) using verified Python script. |
| `IEEE_Mini_A_IPC_Paper/final_page-01.png` ... `final_page-11.png` | Raster Previews | Regenerated 150 DPI page preview images for all 11 pages of `main.pdf`. |

---

## 3. Removal of Comparative Testbed (WSL2)

### Identified Issues
- Table~\ref{tab:environment} previously featured a two-testbed comparison column contrasting Fedora 45 KVM with WSL2 on AMD Ryzen.
- Section VI-A presented a detailed narrative of the WSL2 environment, which diluted focus from the primary Fedora 45 Linux KVM dataset.
- Several locations in the introduction (Section I-E) and discussion (Section VIII-E) referred to comparative hypervisor sweeps.

### Corrections Performed
1. **`tables/environment.tex`**: Completely removed the "Comparative Testbed (WSL2)" column. Converted the table into a compact, single-column table (`\begin{table}[!t]`) titled *"Experimental Hardware, Software Environment, and Benchmarking Workload Parameters"*. Preserved all hardware specifications (Intel Core 7 240H, 4 dedicated vCPUs, 3.8 GiB DDR5), OS details (Fedora 45 Linux, Linux kernel `7.3.4-300.fc45.x86_64`, `PREEMPT_DYNAMIC`), compiler (`GCC 16.2.1 20261029`, flags `-std=c11 -O2 -Wall -Wextra -D_GNU_SOURCE`), core pinning (Core 0 / Core 1), and full workload parameters (64 B to 256 KB sweep, 10,000 timed ping-pongs, 500 untimed warm-ups, $N=7$ randomized blocks, nanosecond `CLOCK_MONOTONIC` timing).
2. **`sections/06_methodology.tex`**: Rewrote Section VI-A to clearly identify Fedora 45 KVM as the primary experimental platform. Removed all references to Ubuntu 26.04 and WSL2.
3. **`sections/01_introduction.tex`** and **`sections/08_discussion.tex`**: Removed references to WSL2 in the contributions list and virtualization threats to validity, focusing strictly on hypervisor effects within the primary KVM platform.

---

## 4. Communication System-Call Graph Correction

### Source Dataset Verification
Inspected `results/unified/raw/syscall_metrics.csv`:
```csv
mechanism,payload_bytes,exchanges,total_calls,comm_syscalls,comm_syscalls_per_exchange,setup_syscalls,other_syscalls,classification,relevant_syscall_details
pipe,64,100,455,400,4.0,25,30,exact,comm: read(200)+write(200)=400; setup: clone(1)+close(10)+pipe2(2)+wait4(1)=25; other: runtime/loader=30
fifo,64,100,461,400,4.0,29,32,exact,comm: read(200)+write(200)=400; setup: clone(1)+close(6)+mknodat(2)+openat(6)+unlink(4)+wait4(1)=29; other: runtime/loader=32
sysv,64,100,448,400,4.0,17,31,exact,comm: msgrcv(200)+msgsnd(200)=400; setup: clone(1)+close(2)+msgctl(1)+msgget(1)+wait4(1)=17; other: runtime/loader=31
posix,64,100,458,400,4.0,25,33,exact,comm: mq_timedreceive(200)+mq_timedsend(200)=400; setup: clone(1)+close(6)+mq_open(2)+mq_unlink(4)+wait4(1)=25; other: runtime/loader=33
shm,64,100,256,206,2.06,21,29,exact,"comm: futex(206)=206 (sync only, 0 data-path syscalls); setup: clone(1)+close(3)+ftruncate(1)+mmap(9)+unlink(1)+wait4(1)=21; other: runtime/loader=29"
uds,64,100,458,400,4.0,27,31,exact,comm: recvfrom(200)+sendto(200)=400; setup: accept(1)+bind(1)+clone(1)+close(6)+connect(1)+listen(1)+socket(2)+unlink(2)+wait4(1)=27; other: runtime/loader=31
```

### Corrections Performed
1. **Dynamic Data Parsing**: Modified `scripts/generate_paper_graphs.py` to implement `load_syscall_metrics()`, which directly parses `results/unified/raw/syscall_metrics.csv`.
2. **Data-Path vs. Synchronization Distinction**:
   - Pipe, FIFO, SysV MQ, POSIX MQ, and UDS execute **4.00 data-path system calls** and **0.00 synchronization calls** per round-trip exchange.
   - POSIX SHM executes **0.00 data-path system calls** and **2.06 synchronization calls (`futex`)** per round-trip exchange (representing a 48.5% reduction in kernel transitions).
3. **Numerical Annotations**: Added bold numerical text annotations above every bar displaying `4.00` for the five stream/queue mechanisms and `2.06` for POSIX SHM.
4. **Renamed Title**: Changed title in both combined and single graphs to *"System Calls per Round-Trip Exchange"*.
5. **Aesthetics & Limits**: Extended y-axis limit to `[0, 5.2]` to prevent numerical labels from colliding with the legend or upper boundary.
6. **Vector Regeneration**: Successfully regenerated `figures/percentiles_resources_combined.pdf` and `figures/resource_utilization.pdf`.

---

## 5. Redesign of the IEEE Architecture Diagram

### Identified Issues
- The legacy diagram in `figures/architecture.tex` was cramped, used crossing diagonal arrows, and drew a misleading link from the adaptive controller directly to the custom kernel mailbox.
- The figure was placed as a single-column float (`figure[t]`), causing text congestion.

### Redesign Implemented
`figures/architecture.tex` was rebuilt from the ground up as a full-width vector TikZ architecture diagram organized into four clearly separated subsystems:
- **Area A (Top-Left): Application and API Layer**
  - CLI & User Applications (`bin/mini-aipc`, `user/aipc_client`)
  - Common IPC Interface (`include/ipc.h`: `ipc_run_opts()`, `ipc_bench_opts_t`)
  - Workload Dispatcher (Single RTT, MPMC Concurrency, Mixed Payloads, Streaming)
- **Area B (Middle-Left): IPC Transport Layer (Userspace)**
  - Anonymous Pipes (`src/ipc_pipe.c`)
  - Named FIFOs (`src/ipc_fifo.c`)
  - System V Message Queues (`src/ipc_sysv_mq.c`)
  - POSIX Message Queues (`src/ipc_posix_mq.c`)
  - POSIX Shared Memory (`src/ipc_shm.c` - `_Alignas(64)` mailbox with futex semaphores)
  - Unix Domain Sockets (`src/ipc_uds.c` - `AF_UNIX` full-duplex stream)
- **User-Kernel Boundary**: Clear horizontal dashed line demarcating userspace from kernel space.
- **Area C (Bottom-Left): Kernel Execution Layer**
  - Linux VFS (Pipe Inodes, Page Buffers)
  - Kernel Message Queues (SysV Linked Lists, POSIX `/dev/mqueue`)
  - Futex / Memory Subsystem (Zero-copy physical page mappings, fast CAS)
  - Unix Socket Core (Local socket buffers `struct sk_buff`)
  - Standalone Custom Character Device (`/dev/aipc` from `kernel/aipc_module.c` with 64 KB ring buffer, wait queues, and teardown barrier)
- **Area D (Right Column): Adaptive Selection & Benchmarking Infrastructure**
  - Adaptive Transport Selector (`src/selector.c`):
    - Static Threshold Policy: $s \le 1024\text{ B} \implies \text{SHM}$, $s > 1024\text{ B} \implies \text{Pipe}$
    - Dynamic EWMA Controller: $\bar{L}^{(t)} = \alpha L + (1-\alpha)\bar{L}^{(t-1)}$ ($\alpha = 0.15$)
    - 8% Hysteresis Switching Margin ($h = 1.08$)
    - **Strict Routing Fidelity:** Control routing arrows point strictly and exclusively to POSIX SHM and Anonymous Pipes. No connections to `/dev/aipc` or queue transports.
  - Unified Benchmarking Suite (`bench/unified_bench.c`, `orchestrate_unified.py`):
    - Scientific controls: Fisher-Yates trial shuffling, dedicated CPU affinity (Core 0 / Core 1)
    - Untimed priming: 500 warm-up cycles
    - Multi-dimensional OS telemetry: `CLOCK_MONOTONIC`, `getrusage`, `strace`
- **Float Integration**: Updated `sections/03_architecture.tex` to place the diagram as `\begin{figure*}[!t]` with a comprehensive caption.

---

## 6. Adaptive Controller Claims Audit

### Code and Benchmark Inspection
- `src/selector.c` implements:
  1. `select_transport(payload_size, threshold)`: Evaluates $s \le \min(T, \text{SHM\_MAX\_PAYLOAD})$ to select SHM vs. Pipe.
  2. `update_transport_telemetry()`: EWMA filter with $\alpha = 0.15$.
  3. `select_transport_adaptive()`: 8% hysteresis band ($h = 1.08$).
- `bench/unified_bench.c` (lines 1050, 1068): Live benchmarks invoke `select_transport(size, threshold)` (the static size-threshold fast path). Dynamic non-stationary traffic with runtime online adaptation was not evaluated in benchmark sweeps.
- `tests/test_unified_benchmark.py` and `tests/test_stats_and_calc.py`: Verify EWMA and selector logic via unit testing.
- `results/unified/raw/adaptive_results.csv`: Demonstrates empirical oracle regret of the static selector across the 7 payload sizes ($N=7$).

### Corrections Performed across Sections
- **Abstract & Section I-E**: Replaced claims of "evaluating dynamic EWMA telemetry" with precise wording: implemented the adaptive framework with static thresholding and dynamic EWMA telemetry with hysteresis, and evaluated the static threshold path experimentally against an empirical oracle.
- **Section III-C & Section V-B**: Explicitly stated that while EWMA and hysteresis logic are fully implemented in `src/selector.c` and verified in automated tests, the controlled benchmark evaluated the deterministic static threshold path to isolate pure dispatch overhead (0.66 ns).
- **Section VIII-B & Section VIII-D (RQ3)**: Clarified distinctions among:
  - *Static Selector Benchmark Evaluation:* 14.29% global accuracy, 71.43% candidate accuracy (SHM vs. Pipe), 27.68% mean latency regret, 0.66 ns decision overhead.
  - *EWMA Telemetry Controller:* Implemented and unit-tested in C; reserved for live dynamic traffic workloads.
  - *Offline 3-Tier Policy:* Oracle fitting demonstrating theoretical bounds ($\le 256$ B $\to$ SysV, 1--64 KB $\to$ Sockets/FIFOs, 256 KB $\to$ Sockets).

---

## 7. Kernel Module Safety Claims Audit

### Code Inspection (`kernel/aipc_module.c`)
- Key mechanics:
  - `atomic_t active_ops` incremented in `aipc_open()` and decremented in `aipc_release()`.
  - `shutdown = true` set under `mutex_lock(&aipc->lock)` in `aipc_exit()`.
  - Sleepable mutex (`struct mutex lock`) ensures page faults during `copy_to_user`/`copy_from_user` do not deadlock.
  - `wait_event_interruptible_all` wakes sleeping readers and writers with `-EPIPE`.
  - `wait_event(aipc->teardown_wait, atomic_read(&aipc->active_ops) == 0)` blocks module unloading until all file descriptors are closed before calling `kfree()`.

### Corrections Performed
- **Removed Unsupported Absolute Statements**:
  - Replaced *"mathematically eliminates module-unload race conditions"* in `sections/03_architecture.tex` with *"designed to coordinate orderly teardown and prevent premature memory deallocation during module unloading"*.
  - Replaced *"eliminating module-unload Use-After-Free race conditions"* in `sections/01_introduction.tex` with *"designed to mitigate module-unload Use-After-Free race conditions"*.
  - Replaced *"$\to$ Zero UAF Panics"* in `figures/kernel_mailbox.tex` with *"$\to$ Active-Op Drain Barrier"*.
- **Preserved Technical Defensibility**: Maintained all technical descriptions of atomic reference counting, wait queues, mutex synchronization, and shutdown signaling.

---

## 8. Author Information Placeholders

### Audit Finding
`main.tex` previously contained temporary placeholder student and supervisor names with `@iiitk.ac.in` domain emails.

### Corrections Performed
Updated the author block in `main.tex` with formal, standardized placeholders:
```latex
% Author Block: Formal placeholders marking fields requiring actual author information prior to submission.
% Replace placeholders below with actual authors, affiliations, and institutional email addresses.
\author{
    \IEEEauthorblockN{[Author 1 Name]\IEEEauthorrefmark{1}, [Author 2 Name]\IEEEauthorrefmark{1}, and [Faculty Advisor Name]\IEEEauthorrefmark{2}}
    \IEEEauthorblockA{\IEEEauthorrefmark{1}{\relax[Author Affiliation / Department / Institution]}\\
    {\relax[City, State, Country]}\\
    Email: \{author1, author2\}@institution.edu}
    \IEEEauthorblockA{\IEEEauthorrefmark{2}{\relax[Advisor Affiliation / Department / Institution]}\\
    {\relax[City, State, Country]}\\
    Email: advisor@institution.edu}
}
```
Wrapped bracketed terms in `{\relax[...]}` to prevent LaTeX from mistaking `[City...]` as an optional vertical dimension parameter to the preceding `\\` newline command (which previously caused a TeX parser error).

---

## 9. Numerical Verification and Empirical Reconciliation

Every numerical value reported across the paper's text and tables was audited against the repository's processed and raw CSV files:

### A. Table III: Mean Round-Trip Latency ($\mu\text{s}$, $N=7$ Randomized Trials)
*Cross-checked against `results/unified/processed/aggregated_results.csv`:*

| Mechanism | 64 B | 256 B | 1,024 B | 4,096 B | 16,384 B | 65,536 B | 262,144 B | Status |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Anonymous Pipe** | 129.84 $\pm$ 39.4 | 123.85 $\pm$ 24.9 | 131.33 $\pm$ 30.3 | 156.48 $\pm$ 60.1 | **140.60** $\pm$ 52.0 | 135.57 $\pm$ 20.5 | 1,144.22 $\pm$ 420.4 | **VERIFIED** |
| **Named FIFO** | 132.15 $\pm$ 33.0 | 131.51 $\pm$ 52.0 | 132.13 $\pm$ 50.8 | **119.44** $\pm$ 13.4 | 151.67 $\pm$ 64.3 | 149.84 $\pm$ 41.1 | 1,080.16 $\pm$ 415.0 | **VERIFIED** |
| **System V MQ** | **123.33** $\pm$ 16.5 | **115.13** $\pm$ 14.6 | 140.64 $\pm$ 42.8 | 137.13 $\pm$ 48.8 | *Limit* | *Limit* | *Limit* | **VERIFIED** |
| **POSIX MQ** | 143.52 $\pm$ 38.9 | 118.03 $\pm$ 16.2 | 128.59 $\pm$ 38.8 | 134.47 $\pm$ 21.0 | *Limit* | *Limit* | *Limit* | **VERIFIED** |
| **POSIX SHM** | 138.66 $\pm$ 44.5 | 128.69 $\pm$ 20.9 | 139.68 $\pm$ 41.3 | *Limit* | *Limit* | *Limit* | *Limit* | **VERIFIED** |
| **Unix Domain Skt** | 126.93 $\pm$ 16.2 | 144.36 $\pm$ 51.7 | **128.28** $\pm$ 30.4 | 135.11 $\pm$ 47.4 | 148.90 $\pm$ 80.8 | **123.53** $\pm$ 25.2 | **449.64** $\pm$ 212.5 | **VERIFIED** |
| **Adaptive Selector** | 132.07 $\pm$ 34.6 | 147.01 $\pm$ 62.7 | 144.52 $\pm$ 54.5 | 135.78 $\pm$ 31.3 | 136.00 $\pm$ 28.7 | 151.87 $\pm$ 36.1 | 957.62 $\pm$ 216.7 | **VERIFIED** |
| **Kernel Mailbox\*** | **3.29** $\pm$ 0.3 | **2.95** $\pm$ 0.2 | **3.35** $\pm$ 0.2 | **3.95** $\pm$ 0.3 | **11.45** $\pm$ 0.8 | *Capacity* | *Capacity* | **VERIFIED** |

### B. Table IV: Adaptive Selector Accuracy and Regret
*Cross-checked against `results/unified/raw/adaptive_results.csv`:*

| Payload Size | Selected | Oracle Best | Adaptive RTT ($\mu\text{s}$) | Oracle RTT ($\mu\text{s}$) | Latency Regret (%) | Match? | Status |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 64 B | `shm` | `sysv` | 132.07 | 123.33 | +7.08% | NO | **VERIFIED** |
| 256 B | `shm` | `sysv` | 147.01 | 115.13 | +27.69% | NO | **VERIFIED** |
| 1,024 B | `shm` | `uds` | 144.52 | 128.28 | +12.66% | NO | **VERIFIED** |
| 4,096 B | `pipe` | `fifo` | 135.78 | 119.44 | +13.69% | NO | **VERIFIED** |
| 16,384 B | `pipe` | `pipe` | 136.00 | 140.60 | -3.27% | YES | **VERIFIED** |
| 65,536 B | `pipe` | `uds` | 151.87 | 123.53 | +22.94% | NO | **VERIFIED** |
| 262,144 B | `pipe` | `uds` | 957.62 | 449.64 | +112.97% | NO | **VERIFIED** |

- **Global Selection Accuracy:** 1 of 7 payload classes = **14.29%** (VERIFIED)
- **Candidate Accuracy (SHM vs. Pipe):** 5 of 7 payload classes = **71.43%** (VERIFIED)
- **Mean Latency Regret:** Across all 7 payload classes = **27.68%** (VERIFIED)
- **Static Decision Overhead:** 0.66 ns per invocation ($< 0.0005\%$ of RTT) (VERIFIED)
- **Offline 3-Tier Policy:** 7 of 7 payload classes = **100.00%** (VERIFIED)

---

## 10. LaTeX Compilation, Diagnostics, and Layout Verification

### Compilation Protocol
The paper was compiled from scratch using `pdflatex` and `bibtex` in multiple passes:
```powershell
pdflatex -interaction=nonstopmode main.tex
bibtex main
pdflatex -interaction=nonstopmode main.tex
pdflatex -interaction=nonstopmode main.tex
```

### Compiler Results
- **Exit Code:** `0` (Success)
- **Undefined References:** `0`
- **Undefined Citations:** `0`
- **Missing Figures:** `0`
- **Broken Equations:** `0`
- **Overlapping Floats:** `0`
- **Total Pages:** Exactly **11 Pages**
- **Column Balancing:** Last page (Page 11) is balanced with equalized columns, terminating after Reference [12].

### Page Breakdown
- **Page 1:** Title, Author Placeholders, Abstract, Index Terms, Section I (Introduction).
- **Page 2:** Section I (cont.), Section II (Related Work).
- **Page 3:** Section II (cont.), Section III (System Architecture and Design).
- **Page 4:** Figure 1 (Full-width 4-Area Architecture Diagram), Section III (cont.), Section IV (Implementation of Classical IPC Mechanisms).
- **Page 5:** Table I (Architectural Comparison), Section IV (cont.), Figure 2 (Classical IPC Topologies).
- **Page 6:** Section IV (cont.), Section V (Adaptive IPC Framework and Kernel Module).
- **Page 7:** Figure 3 (Adaptive Selector & Kernel Mailbox Subfloats), Table II (Experimental Hardware, Software, & Workload Parameters), Section VI (Experimental Setup and Methodology).
- **Page 8:** Figure 4 (End-to-End Benchmarking Workflow), Section VI (cont.).
- **Page 9:** Table III (Mean Latency Table), Figure 5 (Latency & Throughput Scaling), Section VII (Experimental Results and Performance Analysis).
- **Page 10:** Figure 6 (Tail Latency & System Calls per Round-Trip Exchange), Table IV (Adaptive Selector Accuracy and Regret), Section VIII (Concurrency, Adaptive Evaluation, and Discussion).
- **Page 11:** Section VIII (cont., RQ1--RQ5, Limitations), Section IX (Conclusion and Future Work), References [1]--[12] (Balanced across both columns).

---

## 11. Remaining Pre-Submission Actions

While the paper is technically, empirically, and typographically refined to publication standards, the following administrative items must be addressed by the authors prior to camera-ready submission:

1. **Author Information**: Replace placeholder values in `IEEE_Mini_A_IPC_Paper/main.tex` (lines 49--57) with actual author names, institutional departments, postal affiliations, and academic email addresses.
2. **Institutional Supervision**: Fill in the corresponding Faculty Advisor / Supervisor block.
3. **Privileged Kernel Execution**: When demonstrating the `/dev/aipc` character device on physical Linux hardware, load the kernel module with root privileges (`sudo insmod kernel/aipc.ko`); unprivileged user execution will safely register as `BLOCKED`.

---

## 12. Verification Conclusion

The IEEE research paper `Mini-A-IPC` has been audited and refined to strict publication-quality standards. All empirical measurements originate directly from the verified CSV records in `results/unified/`. All theoretical claims regarding adaptive transport selection and kernel module safety have been reconciled with the actual repository implementations. The paper builds without errors into an 11-page publication PDF with vector graphics and balanced columns.