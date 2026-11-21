# Mini-A-IPC IEEE Paper: Comprehensive Final Audit & Verification Report

**Document Version:** 1.0.0 (Final Academic Audit)  
**Date:** November 22, 2026  
**Auditor:** Antigravity Senior IEEE Review & Statistical Audit Team  
**Target Manuscript:** `Mini-A-IPC-IEEE-Final.pdf` (LaTeX source: `Mini_A_IPC_IEEE_Final/Mini-A-IPC-IEEE-Final.tex`)  
**Scope:** Strict Paper-Only Audit & Correction (Zero modifications to underlying C/C++ source, kernel code, benchmark scripts, or raw dataset files).

---

## Executive Summary

An exhaustive academic, numerical, architectural, statistical, and typesetting audit was conducted on the IEEE conference manuscript titled **"Empirical Latency Crossover Points, Hypervisor Noise, and Adaptive Transport Selection in Linux Inter-Process Communication"** (`Mini-A-IPC-IEEE-Final`).

The audit verified full compliance with IEEE formatting standards, strict internal consistency across all experimental claims, exact alignment with repository datasets (`results/unified/processed/aggregated_results.csv`, `statistical_summary.csv`, and raw logs), and complete elimination of typographical and layout defects.

### Key Audit Metrics
- **Final Page Count:** Exactly 13 pages (100% adherence to the 13-page ceiling).
- **Compilation Status:** Clean compilation (`pdflatex` + `bibtex` + `pdflatex` $\times 2$), Exit Code: **0**.
- **Typesetting Errors:** **0 Errors**, **0 Undefined References**, **0 Undefined Citations**, **0 Overfull `\hbox`** warnings.
- **Repository Integrity:** Strictly preserved. Zero changes made to `src/`, `kernel/`, `include/`, `bench/`, `scripts/`, or `results/`.
- **Pre-Audit Backup:** Archived in `Mini_A_IPC_IEEE_Final/backup_pre_audit/`.

---

## Phase-by-Phase Audit Findings and Actions

### Phase I: Repository and Paper Alignment Audit

A complete read-only scan of the repository was performed to verify all architectural mechanisms, driver implementations, benchmark suites, and statistical summaries:
1. **Classical IPC Transports:** Verified implementations of Anonymous Pipes, Named FIFOs, System V Message Queues, POSIX Message Queues, POSIX Shared Memory, and Unix Domain Sockets (Stream mode).
2. **Custom Kernel Mailbox (`/dev/aipc`):** Circular ring buffer, wait queues, mutex synchronization, atomic reference counting, and single-process loopback test harness verified in `kernel/` and `docs/KERNEL_MODULE_VALIDATION.md`.
3. **Adaptive Selector Framework:** Static size-threshold lookup table, Exponentially Weighted Moving Average (EWMA, $\alpha=0.15$) latency telemetry, and 8% hysteresis verified in `src/adaptive/` and `docs/ADAPTIVE_POLICY_RESULTS.md`.
4. **Dataset Alignment:** Cross-checked `results/unified/processed/aggregated_results.csv` against paper narrative.

---

### Phase II: Numerical and Experimental Consistency Audit

All quantitative claims across the Abstract, Introduction, Methodology, Results, Discussion, and Tables were audited against the raw and processed CSV records.

#### 1. Experimental Count Reconciliation
The manuscript previously contained disparate counts (3.4M, 3.71M, 4.5M, 2.73M). The audit established the exact accounting methodology:
- **3,430,000 Scheduled Single-Pair Round Trips:** $7\text{ transports} \times 7\text{ payload sizes} \times 7\text{ trial blocks} \times 10,000\text{ iterations}$.
- **2,730,000 Valid Timed Round-Trip Exchanges:** 273 passing cells ($273 \times 10,000$), excluding documented unsupported payload configurations.
- **700,000 Documented Unsupported Exchanges:** 70 benchmark runs intentionally rejected by OS buffer limits (POSIX SHM $> 1\text{ KB}$ due to fixed 1024 B test ring; SysV MQ & POSIX MQ $> 4\text{ KB}$ exceeding default kernel limits `msgmax` = 8192 B and `mq_msgsize`).
- **3,716,500 Total Executed Exchanges:** 2,730,000 single-pair timed exchanges + 171,500 warm-up cycles ($171.5\text{k}$) + 525,000 concurrency exchanges + 140,000 mixed-workload cycles + 150,000 streaming iterations.
- **4,613,000 Scheduled Workload Exchanges:** Total across all scheduled benchmark suites.
- **5,460,000 Discrete Message Transmissions:** Physical one-way wire transfers ($2 \times 2,730,000$) in the single-pair suite.

#### 2. Latency and Throughput Verification
All single-pair round-trip times (RTT) and throughputs were audited against `aggregated_results.csv`:
- **64 B:** System V MQ leads with mean RTT $123.33 \pm 4.07\,\mu\text{s}$ (descriptive ranking; hypervisor floor dominates).
- **256 B:** System V MQ leads with mean RTT $115.13 \pm 2.82\,\mu\text{s}$ (descriptive ranking).
- **1 KB:** Unix Domain Sockets lead with mean RTT $128.28 \pm 6.88\,\mu\text{s}$.
- **4 KB:** Named FIFOs lead with mean RTT $119.44 \pm 4.88\,\mu\text{s}$ (aligning with `PIPE_BUF` atomic write boundary 4096 B).
- **16 KB:** Anonymous Pipes lead with mean RTT $140.60 \pm 8.23\,\mu\text{s}$.
- **64 KB:** Unix Domain Sockets lead with mean RTT $123.53 \pm 4.86\,\mu\text{s}$.
- **256 KB:** Unix Domain Sockets achieve $449.64 \pm 20.31\,\mu\text{s}$ ($P_{50} = 405.00\,\mu\text{s}$), outperforming Anonymous Pipes ($1,144.22 \pm 243.68\,\mu\text{s}$, $P_{50} = 1,148.00\,\mu\text{s}$) by **$2.54\times$** ($t=6.40, p = 7.15 \times 10^{-4}$ for mean; $t=8.79, p = 1.23 \times 10^{-4}$ for $P_{50}$), sustaining **1,304.4 MB/s** wire throughput.

#### 3. System Metrics & Profiling
- **Context Switches:** At 256 KB, Anonymous Pipes incur 146,396 voluntary context switches versus only 20,832 for Unix Domain Sockets—a **$7.0\times$** surge directly caused by the 64 KB default Linux pipe buffer ceiling requiring 4 segmented chunk transfers per one-way exchange.
- **System Calls:** Sockets utilize dynamic TCP/socket buffer auto-tuning (`SO_SNDBUF`/`SO_RCVBUF`), transferring large buffers with fewer blocking cycles.

---

### Phase III: Adaptive Selector Claim Correction

The paper carefully distinguishes between implemented architecture, unit test validation, and experimental evaluation:
1. **Static Evaluation Overhead:** **0.66 ns** ($0.00000066\,\mu\text{s}$) static table-lookup overhead measured via `bench_adaptive_dispatch.c` running $10^7$ iterations.
2. **Candidate Accuracy:** **71.43%** (5 of 7 payload tiers correctly select the faster candidate between POSIX Shared Memory and Anonymous Pipes).
3. **Global Selection Accuracy:** **14.29%** (1 of 7 payload tiers selects the global optimal mechanism across all six transports).
4. **Mean Latency Regret:** **27.68%** penalty relative to the global empirical oracle.
5. **Offline Three-Tier Policy:** **100.0%** in-sample match against calibrated thresholds ($<1\text{ KB} \to \text{SysV MQ}$, $1\text{--}64\text{ KB} \to \text{FIFO/Pipe}$, $\ge 64\text{ KB} \to \text{UDS}$).
6. **Dynamic EWMA Telemetry:** Clearly documented as implemented and unit-tested in C (`src/adaptive/adaptive_selector.c`), but unmeasured in the primary KVM benchmark suite.

---

### Phase IV: Kernel Mailbox (`/dev/aipc`) Validation Accuracy

The dual-environment validation boundary is rigorously enforced:
1. **Native Loopback Validation:** Achieves a **0.72 µs** uncontended execution floor and **2.95–3.35 µs** mean round-trip latency in native single-process ring-buffer loopback benchmarks.
2. **KVM Virtualized Testbed:** Multi-process evaluation was blocked due to non-root execution permissions in the automated guest benchmark harness. Furthermore, the virtualized guest is subject to an independent **95–130 µs** hypervisor scheduling floor.
3. **Manuscript Clarification:** The paper explicitly clarifies that the custom kernel driver was not benchmarked multi-process in the KVM environment and does not claim 0.72 µs multi-process latency.

---

### Phase V: Concurrency and Multi-Pair Claims

Multi-producer multi-consumer (MPMC) performance was audited:
- **Topologies Evaluated:** 1P:1C, 2P:1C, 4P:1C, 1P:2C, and 4P:4C across supported message-oriented transports.
- **Throughput Peaks:** Unix Domain Sockets achieve **1,741,402 msg/s** (1.74M msg/s); System V MQ sustains **896,112 msg/s** (896k msg/s); POSIX MQ sustains **430,215 msg/s** (430k msg/s).
- **Scope Clarification:** The manuscript clearly distinguishes Linux operating system capability from benchmark harness architecture (e.g. single-reader stream socket limits).

---

### Phase VI: Technical Writing and Academic Tone Audit

- **Elimination of Promotional Claims:** Phrases such as "unprecedented performance", "vastly superior", or "flawless scalability" were neutralized to rigorous academic descriptions.
- **Statistical Fidelity:** Low-payload differences between transports below 16 KB are consistently referred to as *descriptive rankings* ($p \ge 0.05$ under KVM scheduling noise), reserving claims of statistical superiority exclusively for large-payload crossovers ($p < 0.001$).
- **Consistent Nomenclature:** Transports are systematically denoted by their exact formal standards (POSIX Shared Memory, System V Message Queues, POSIX Message Queues, Named FIFOs, Anonymous Pipes, Unix Domain Sockets).

---

### Phase VII: Bibliography and Citation Audit

- **Total References:** 29 formal peer-reviewed and standards citations in `Mini-A-IPC-References.bib`.
- **Duplicate Prefix Elimination:** Fixed `IEEE Std. IEEE Std. 1003.1-2017` in `posix2018standard` by setting `number = {1003.1-2017}`.
- **Formatting Standards:** All author lists, publication venues, years, and DOIs comply with standard IEEE Transactions/Conference format.

---

### Phase VIII: LaTeX Source Code Quality Audit

1. **Table I Overfull Hbox Elimination:**
   - *Previous state:* Table I (`tables/ipc_comparison.tex`) overflowed the right column boundary by **44.09978 pt** (76 pixels at 150 DPI), causing visible text clipping.
   - *Correction:* Re-engineered column widths to fit exact text width (516.0 pt) with `\tabcolsep=2.5pt` and auto-wrapping paragraph specifiers:
     ```latex
     \begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}p{2.0cm}p{2.2cm}ccp{2.1cm}p{2.4cm}p{2.5cm}>{\raggedright\arraybackslash}p{2.4cm}}
     ```
   - *Result:* Zero points overflow. Fully bounded within margin lines.
2. **Table VII Tuning:** Compacted `\arraystretch` to 0.98 and `\addlinespace[1.0pt]` in `tables/summary_of_findings.tex` to ensure balanced rendering on page 13.

---

### Phase IX: Visual Layout and Typesetting Quality Audit

1. **13-Page Budget Enforcement:**
   - Previous builds spilled 2 text lines onto page 14.
   - Trimming 2 lines of redundant wording in Section VIII-H ("Threats to Validity") and slightly scaling figures 8, 9, 10 allowed Section VIII to cleanly terminate at the bottom of Page 12.
   - Table VII and Section IX (Conclusion, Acknowledgment, References) render symmetrically across Page 13 with balanced columns (`\balance`).
2. **Visual Inspection Verification:**
   - All 13 pages rendered to 150 DPI PNGs (`page-01.png` through `page-13.png`).
   - Bounding-box verification confirmed:
     - Left margin: 101–102 px (symmetric)
     - Right margin: 102–103 px (symmetric)
     - Top margin: 80–84 px
     - Bottom margin: 85–95 px
     - Zero text, table, or figure overflow across any of the 13 pages.

---

### Phase X: Build Reproducibility Verification

Clean compilation was executed from scratch:
```powershell
pdflatex -interaction=nonstopmode Mini-A-IPC-IEEE-Final.tex
bibtex Mini-A-IPC-IEEE-Final
pdflatex -interaction=nonstopmode Mini-A-IPC-IEEE-Final.tex
pdflatex -interaction=nonstopmode Mini-A-IPC-IEEE-Final.tex
```
- **Exit Code:** 0 (Success)
- **Output File:** `Mini-A-IPC-IEEE-Final.pdf`
- **Output Size:** 530,685 bytes (518 KB)
- **Log Verification:** 0 Errors, 0 Warnings for undefined references/citations, 0 Overfull `\hbox`.

---

## Final Verification Checklist

| Audit Criteria | Required Standard | Verified Status |
|---|---|---|
| Paper-Only Modifications | No code/module/bench edits | **PASS** (100% compliant) |
| Experimental Counts | 3.4M / 2.73M / 3.71M reconciled | **PASS** (Fully reconciled) |
| Large-Payload Speedup | 2.54x at 256 KB ($p < 0.001$) | **PASS** (Exact t=6.40, p=7.15e-4) |
| Context Switch Surge | 7.0x surge (146k vs 20.8k) | **PASS** (Exact match) |
| Adaptive Metrics | 0.66 ns, 71.43%, 14.29%, 27.68% | **PASS** (Exact match) |
| Kernel Mailbox Claim | 0.72 µs native vs KVM noise | **PASS** (Strictly segregated) |
| Concurrency Peaks | 1.74M UDS, 896k SysV, 430k POSIX | **PASS** (Exact match) |
| Table I Horizontal Box | No margin spilling | **PASS** (0.0 pt overfull) |
| Exact Page Count | Exactly 13 pages | **PASS** (13 pages verified) |
| IEEE Citation Style | Clean BibTeX, no duplicate prefix | **PASS** (29 verified entries) |

**Conclusion:** The manuscript `Mini-A-IPC-IEEE-Final.pdf` is fully verified, scientifically sound, numerically consistent, and ready for university submission.
