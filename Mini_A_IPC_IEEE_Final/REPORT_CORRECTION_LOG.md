# Mini-A-IPC Research Paper Correction Log & Academic Audit

**Project:** Mini-A-IPC: Design, Implementation, and Performance Evaluation of Classical and Adaptive Inter-Process Communication Mechanisms in Linux  
**Target Publication:** IEEE Conference Format (Two-Column, 13 Pages)  
**Authors:** Tanguturi Ram Sai (124CS0037), Ayush Naresh Gatla (124CS0038), Dr. N. Srinivas Naik  
**Affiliation:** Department of Computer Science and Engineering, IIITDM Kurnool, India  
**Date of Audit & Finalization:** November 21, 2026  
**Document Directory:** `Mini_A_IPC_IEEE_Final/`  

---

## 1. Executive Summary of Corrections

This document provides a comprehensive, transparent record of all scientific, empirical, bibliographic, and architectural corrections applied to the Mini-A-IPC research paper. Every modification is grounded strictly in repository source code, raw experimental datasets, environmental captures, and validated external reference literature.

No synthetic data was generated, no contradictory evidence was silently reconciled, and no fabricated citations were retained.

---

## 2. Detailed Log of Corrections

### Correction 1: Kernel Version Inconsistency
- **Original Claim / Text:** The previous report text specified the experimental host running Linux kernel `7.3.4-300.fc45.x86_64`.
- **Repository Evidence:**
  - `results/unified/environment.txt` (Line 1): `Linux fedora 7.3.3-300.fc45.x86_64 #1 SMP PREEMPT_DYNAMIC Sun Feb 1 00:00:00 UTC 2026 x86_64 GNU/Linux`
  - `runs/exp_20261118T134516Z_9733/environment.txt` (Line 1): `Linux fedora 7.3.3-300.fc45.x86_64`
  - `runs/exp_20261118T134516Z_9733/benchmark_metadata.json` (Line 4): `"kernel_version": "7.3.3-300.fc45.x86_64"`
  - `docs/KERNEL_BENCHMARK_FAIRNESS.md`: Confirms Fedora 45 with kernel 7.3.3.
- **Correction Applied:**
  - Corrected all occurrences from `7.3.4` to `7.3.3-300.fc45.x86_64` across the entire document.
  - Affected locations: Abstract, Section I, Table II (`tables/environment.tex`), Section VI-A, Section VII, Section VIII, Section IX.
- **Status:** Fully Resolved & Verified.

---

### Correction 2: Kernel Mailbox Validation Limitations (`/dev/aipc`)
- **Original Claim / Text:** Ambiguous presentation in preliminary drafts conflated character device driver compilation with live multi-process benchmark execution, suggesting multi-process latencies were directly measured on the primary testbed.
- **Repository Evidence:**
  - `results/unified/kernel_results.csv`: Demonstrates compilation succeeded (`make kernel-module`), but `insmod` was recorded as `BLOCKED` due to unprivileged sudo boundaries on the KVM guest.
  - `docs/KERNEL_MODULE_VALIDATION.md` & `docs/KERNEL_BENCHMARK_FAIRNESS.md`: Explicitly details that single-process loopback testing on development hosts achieved uncontended floors of $0.72\,\mu\text{s}$ (64 B) to $3.35\,\mu\text{s}$ (1,024 B).
  - Multi-process exchanges in KVM virtualized environments are strictly dominated by the $95\text{--}130\,\mu\text{s}$ guest context switch and hypervisor vCPU scheduling floor.
- **Correction Applied:**
  - Clearly separated (1) successful module compilation, (2) static code analysis, (3) runtime privilege boundaries (`BLOCKED` status on primary KVM testbed), (4) standalone single-process loopback baseline ($0.72\text{--}3.35\,\mu\text{s}$), and (5) the hypervisor context-switch floor ($95\text{--}130\,\mu\text{s}$).
  - Updated Table III footnote to explain the loopback vs. scheduler floor distinction with zero ambiguity.
  - Explicitly characterized `/dev/aipc` as a proof-of-concept standalone kernel driver with atomic reference-counting teardown semantics.
- **Status:** Fully Resolved & Verified.

---

### Correction 3: Adaptive Transport Selector Evaluation
- **Original Claim / Text:** Preliminary drafts stated or implied that the adaptive selector achieved dynamic runtime switching during benchmarking with 100% accuracy.
- **Repository Evidence:**
  - `src/selector.c` (`select_transport()`): Implements deterministic static size-threshold selection (`payload_size <= 1024 ? IPC_SHM : IPC_PIPE`).
  - `src/selector.c` (`update_telemetry()`): Implements dynamic EWMA telemetry ($\alpha = 0.15$) and hysteresis ($1.08$), but controlled benchmark runs exercised the static threshold decision path.
  - `results/unified/adaptive_eval_results.csv` & `docs/ADAPTIVE_POLICY_RESULTS.md`:
    - Candidate accuracy between SHM and Pipe: 5 of 7 classes correct = **71.43%**.
    - Global accuracy vs. all 6 transports: 1 of 7 classes correct = **14.29%** (since SysV MQ and UDS frequently beat SHM/Pipe).
    - Mean intra-trial latency regret across workloads: **27.68%**.
    - Static selector execution overhead: **0.66 ns** per call.
    - Offline 3-tier mapping ($\le 256$ B $\to$ SysV MQ, 1--64 KB $\to$ UDS/FIFO, 256 KB $\to$ UDS): 7 of 7 classes = **100.0%** in-sample empirical fit.
- **Correction Applied:**
  - Accurately reported 71.43% candidate accuracy, 14.29% global accuracy, and 27.68% mean regret.
  - Explicitly classified the 3-tier policy as an *offline-calibrated in-sample baseline*, not generalized online control.
  - Clarified that while EWMA and hysteresis logic are fully implemented in `src/selector.c`, benchmark evaluation quantified the deterministic threshold execution path.
- **Status:** Fully Resolved & Verified.

---

### Correction 4: Experiment Provenance Reconciliation
- **Original Claim / Text:** Inconsistent experiment IDs (`exp_20261118T134516Z_9733`, `run_20261113_213428_11370`, and `unknown`) across raw CSVs, metadata, and scripts caused confusion regarding data lineage.
- **Repository Evidence:**
  - `runs/exp_20261118T134516Z_9733/`: Primary execution timestamp directory holding the complete raw experimental dataset (7 payload sizes $\times$ 6 classical transports $\times$ 7 randomized blocks $\times$ 10,000 iterations = 2,940,000 scheduled transmissions; 2,730,000 valid timed exchanges).
  - `run_config.json` (Line 2): Identifies `"run_id": "run_20261113_213428_11370"`, the persistent benchmark configuration template defining payload classes, core affinity, and iterations.
  - `bench/analyze_results.py`: Batch aggregation script that outputs `"unknown"` in `aggregated_results.csv` and `statistical_summary.csv` when executed without an explicit `--exp-id` argument.
- **Correction Applied:**
  - Added Section VI-B explaining the exact hierarchy and relationship between execution timestamps, configuration IDs, and analysis script output tags.
  - Created standalone `EXPERIMENT_PROVENANCE.md` mapping every CSV column and metric to its generating code and data file.
- **Status:** Fully Resolved & Verified.

---

### Correction 5: Transport Practitioner Recommendations (Table VI)
- **Original Claim / Text:** Table VI in earlier drafts broadly recommended "FIFOs / Anonymous Pipes" across the entire 1--64 KB range without distinguishing measured crossover points.
- **Repository Evidence:**
  - `results/unified/aggregated_results.csv`:
    - 1 KB: Unix Domain Sockets ($128.28\,\mu\text{s}$) and POSIX MQ ($129.28\,\mu\text{s}$) achieve lower mean latency than Pipes ($143.51\,\mu\text{s}$).
    - 4 KB: Named FIFOs achieve lowest mean latency ($119.44\,\mu\text{s}$), perfectly fitting Linux's 4,096-byte `PIPE_BUF`.
    - 16 KB: Anonymous Pipes achieve lowest mean latency ($140.60\,\mu\text{s}$).
    - 64 KB: Unix Domain Sockets achieve lowest mean latency ($123.53\,\mu\text{s}$) vs. Pipes ($147.23\,\mu\text{s}$) and FIFOs ($149.03\,\mu\text{s}$).
    - 256 KB: Unix Domain Sockets achieve $449.64\,\mu\text{s}$ vs. Pipes ($1,144.22\,\mu\text{s}$, $2.54\times$ speedup) due to avoiding pipe circular buffer exhaustion.
- **Correction Applied:**
  - Restructured Table VI into distinct empirical crossover regimes:
    - Sub-Kilobyte ($\le 256$ B): System V Message Queue (115.1--123.3 µs, descriptive lead under KVM floor).
    - Intermediate Crossovers: 1 KB: UDS / POSIX MQ; 4 KB: Named FIFO; 16 KB: Anonymous Pipe.
    - Large Payloads ($\ge 64$ KB): Unix Domain Sockets (auto-tuning socket buffers prevent chunking).
    - Zero-Copy ($\le 1$ KB): POSIX Shared Memory (0 data syscalls, 48.5% fewer kernel transitions).
    - MPMC (4P:4C): Unix Domain Sockets (1.74M msg/s) / System V MQ (896k msg/s).
    - Dynamic Workloads: Adaptive Framework (0.66 ns dispatch; EWMA telemetry with 8% hysteresis).
  - Explicitly qualified all recommendations as workload- and testbed-specific findings under KVM virtualization.
- **Status:** Fully Resolved & Verified.

---

### Correction 6: Reference Paper Audit (Danyliuk, SWorldJournal 2026)
- **Original Claim / Text:** Earlier drafts miscited Danyliuk with inconsistent page ranges and inaccurately attributed large-payload socket throughput findings to Danyliuk's study.
- **Repository Evidence:**
  - Audited `Paper.pdf` (`156-318-PB.pdf`):
    - Author: I. M. Danyliuk
    - Title: "Classical interprocess communication mechanisms in Linux OS: Review and latency analysis for HPC scenarios"
    - Journal: *SWorldJournal*, Issue 37, Part 2, March 2026, pp. 40--45.
    - DOI: `10.30888/2663-5712.2026-37-02-028`.
    - Content Scope: Focuses strictly on small-message round-trip latency (64--1,024 bytes) across physical Linux hardware. Explicitly concludes on page 45: *"Comparison of the throughput of the IPC mechanisms for large messages will be addressed in the second part of this study."*
- **Correction Applied:**
  - Corrected BibTeX entry: pages `40--45`, exact DOI, full journal title, issue, and URL.
  - Removed all attributions of large-payload throughput or socket buffer saturation to Danyliuk.
  - Positioned Mini-A-IPC as a direct empirical continuation and extension of Danyliuk's work, addressing the deferred large-payload regime (up to 256 KB), tail latency ($P_{90}$ to $P_{99.9}$), multi-process MPMC concurrency, adaptive transport selection, and custom kernel mailboxes.
- **Status:** Fully Resolved & Verified.

---

### Correction 7: Reference [8] Audit and Replacement
- **Original Claim / Text:** Reference [8] was previously cited as `renault2018efficient`: "E. Renault and F. Dang, 'Analyzing and Optimizing Inter-Process Communication in Virtualized Linux Environments,' in IEEE Trans. Cloud Comput., 2018."
- **Audit Findings:** Independent verification revealed that `renault2018efficient` does not correspond to a real, verifiable publication by those authors in IEEE Transactions on Cloud Computing.
- **Correction Applied:**
  - Completely removed the unverified citation from `Mini-A-IPC-References.bib`.
  - Replaced it with the canonical, peer-recognized systems performance authority:  
    `gregg2020systems`: Brendan Gregg, *Systems Performance: Enterprise and the Cloud*, 2nd ed. Boston, MA, USA: Addison-Wesley, 2020.
  - Updated all citations in `01_introduction.tex` and `02_related_work.tex`.
- **Status:** Fully Resolved & Verified.

---

### Correction 8: IEEE Conference Layout & Exact Page-Budget Optimization
- **Original Status:** Document compiled with 0 errors but spanned 14 pages due to a 4-line overflow on Page 12 pushing Section VIII-I onto Page 13 and References onto Page 14.
- **Correction Applied:**
  - Adjusted figure widths in `sections/08_discussion.tex` (Fig. 10 to `0.68\columnwidth`).
  - Streamlined subsection phrasing in Sections VIII-D, VIII-E, VIII-F, VIII-H, and VIII-I.
  - Reduced table array stretches in `tables/hypotheses.tex` (`0.90`) and `tables/recommendations.tex` (`0.88`).
  - Structured Section IX with `\clearpage`, Table VII at top of Page 13, Section IX text, and `\balance` to equalize Columns 1 and 2.
  - Achieved exact 13-page balanced IEEE conference layout with 0 overfull vboxes, 0 undefined citations, and 0 unresolved references.
- **Status:** Fully Resolved & Verified.
