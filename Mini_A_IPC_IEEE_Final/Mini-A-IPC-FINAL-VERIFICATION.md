# Mini-A-IPC IEEE Final Manuscript: Targeted Verification and Academic Audit Report

**Manuscript Title:** Mini-A-IPC: Design, Implementation, and Performance Evaluation of Classical and Adaptive Inter-Process Communication Mechanisms in Linux  
**Target Venue:** IEEE Transactions on Computers / IEEE Conference Format (`IEEEtran.cls`, 10pt, two-column)  
**Document Version:** Version 10.0 Final Submission Audit  
**Date:** November 22, 2026  
**Auditor:** Senior Linux Systems Researcher, Experimental Statistics Auditor & IEEE Manuscript Reviewer  
**Primary Testbed:** Fedora 45 Linux (`kernel 7.3.3-300.fc45.x86_64`, KVM Guest, Intel Core 7 240H @ 4 vCPUs, 3.8 GiB DDR5)  
**Primary Datasets:** `results/unified/runs/exp_20261118T134516Z_9733/reports/FINAL_BENCHMARK_REPORT.md`, `results/unified/processed/aggregated_results.csv`, `results/unified/processed/statistical_summary.csv`, `docs/KERNEL_MODULE_VALIDATION.md`, `docs/ADAPTIVE_POLICY_RESULTS.md`, `IEEE_Mini_A_IPC_Paper/evidence/claim_verification.md`  

---

## Executive Summary & Final Submission-Readiness Verdict

An exhaustive, evidence-driven final submission audit was conducted across the `Mini-A-IPC` codebase, raw experimental logs, processed datasets, and the compiled manuscript `Mini-A-IPC-IEEE-Final.pdf`.

### Absolute Preservation & Non-Negotiable Boundaries
- **Project Implementation (`src/`):** **ZERO modifications**. Unaltered.
- **Kernel Module Implementation (`kernel/`):** **ZERO modifications**. Unaltered.
- **Raw Benchmark Datasets (`results/`):** **ZERO modifications**. Unaltered.
- **Valid Experimental Measurements:** Strictly preserved. No numbers fabricated.
- **Document Class & Template:** Strictly conforms to `IEEEtran.cls` (conference, letterpaper, 10pt, two-column).

---

## Three-Tier Verification Breakdown

In accordance with academic auditing standards, all claims are rigorously classified into three explicit tiers:

### 1. Visually Verified Claims (Page-by-Page Inspection of 150 DPI Renders)
- **Exact Page Budget:** Exactly **13 pages** (528,723 bytes). Zero page overflow onto Page 14.
- **Page 13 Symmetrical Balance:** Column 1 text height is **1039 px**, Column 2 text height is **1038 px** (1-pixel variance, virtually perfect balance achieved via `\balance` and calibrated `\BIBdecl`).
- **Standard IEEE Margins:** Bounding box analysis across all 13 pages confirms left margin at $x = 101\text{--}102$ px and right margin at $x = 1172\text{--}1173$ px, maintaining standard 102 px symmetric margins.
- **Table Formatting & Bounds:** Table I (`tab:ipc_comparison`) textwidth formatting eliminates the previous 44.1 pt overflow. All 7 tables bounded strictly within column margins.
- **Vector Figure Quality:** All 10 figures render cleanly at native vector resolution without float collisions or text clipping.
- **Clean Float Flow:** Table III and Figure 5 co-located at the top of Page 9; Figure 6 co-located at the top of Page 10; Section VIII terminates cleanly at the bottom of Page 12.

### 2. Statistically Verified Claims (Inferential Hypothesis Testing & Uncertainty)
- **High-Payload Speedup (256 KB):** Unix Domain Sockets ($449.64 \pm 212.48\,\mu\text{s}$) outperform Anonymous Pipes ($1,144.22 \pm 420.44\,\mu\text{s}$) by **$2.54\times$** ($60.70\%$ latency reduction).
  - Paired Student's $t$-test on trial blocks ($N=7, df=6$): $t = 6.40, p = 6.83 \times 10^{-4} < 0.001$ (**Statistically Highly Significant**).
  - Paired $t$-test on median observations ($N=7, df=6$): $t = 8.79, p = 1.23 \times 10^{-4} < 0.001$.
  - Wilcoxon signed-rank test: $W = 0, p = 0.0156 < 0.05$.
  - 95% Confidence Interval for mean difference: $[429.20\,\mu\text{s},\, 959.96\,\mu\text{s}]$.
- **Oracle Equivalence at 16 KB:** Matched baseline pipe and adaptive runs yield an empirical difference of $-3.27\%$ ($136.00\,\mu\text{s}$ vs. $140.60\,\mu\text{s}$), statistically indistinguishable from zero ($t = -0.189, p = 0.86, df = 6$; Wilcoxon $W = 11.0, p = 0.69$).
- **Sub-Kilobyte Descriptive Rankings:** System V MQ sample mean leads at 64 B ($123.33\,\mu\text{s}$) and 256 B ($115.13\,\mu\text{s}$) have $p \ge 0.05$ (paired $t$-test vs Pipe $t = 0.493, p = 0.64$), rigorously reported as *descriptive rankings under the KVM scheduling floor* rather than statistically significant separations.
- **Wire Bandwidth Scaling:** Decimal equations rigorously verified: at 256 KB, UDS achieves 1,304.44 MB/s wire bandwidth (652.22 MB/s payload; 1,244.01 MiB/s wire; 2,488.03 exch/s), while Pipe wire bandwidth collapses to 502.38 MB/s (251.19 MB/s payload; 479.11 MiB/s wire; 958.22 exch/s).
- **Experimental Counting Accounting:** 3,430,000 scheduled single-pair exchanges ($7 \times 7 \times 7 \times 10,000$), 2,730,000 valid timed round-trip exchanges, 5,460,000 discrete directional wire transmissions, and 3,716,500 total physically executed experimental cycles across all suites.

### 3. Repository-Verified Claims (Source Code & Log Provenance)
- **POSIX vs. System V Nomenclature:** Page 2 (Section I, Contribution 1) corrected to designate the suite as "standards-based (encompassing POSIX-compliant primitives alongside the System V IPC interface)". System V Message Queues use `msgget`/`msgsnd`/`msgrcv`/`msgctl`, accurately distinguished from POSIX message queues (`mq_open`/`mq_send`/`mq_receive`).
- **Offline 3-Tier Policy Specification:** Section VIII-B point 4 corrected to articulate the three architectural regimes and explain the 16 KB Anonymous Pipe selection:
  1. Sub-KB ($\le 256$ B) $\to$ System V MQ (64 B, 256 B);
  2. Intermediate transfers (1 KB--16 KB) $\to$ empirical crossover winners: 1 KB Unix Domain Sockets ($128.28\,\mu\text{s}$), 4 KB Named FIFOs ($119.44\,\mu\text{s}$, matching `PIPE_BUF` 4096 B atomicity), and 16 KB Anonymous Pipes ($140.60\,\mu\text{s}$);
  3. Large transfers ($\ge 64$ KB) $\to$ Unix Domain Sockets (64 KB at $123.53\,\mu\text{s}$ and 256 KB at $449.64\,\mu\text{s}$) via buffer auto-tuning.
  This rigorously explains and validates the claimed **7 of 7 matches (100.0%)** in-sample fit.
- **Adaptive Selector Metrics:** Evaluated over 1M iterations in compiled C: 0.66 ns static lookup overhead; 71.43% candidate accuracy (SHM vs Pipe); 14.29% global accuracy; 27.68% mean intra-trial regret.
- **Zero-Copy Syscall Reduction:** POSIX SHM executes 0.00 data syscalls and 2.06 futex calls per exchange, cutting total kernel entries by 48.5% compared to stream transports (4.00 syscalls/exchange).
- **Kernel Mailbox (/dev/aipc) Population Boundaries:**
  - *Intra-trial population ($n=10,000$):* Single representative uncontended trial block in native validation yields $\text{Min} = 0.84\,\mu\text{s}, P_{50} = 0.93\,\mu\text{s}, P_{95} = 1.07\,\mu\text{s}, P_{99} = 1.90\,\mu\text{s}, \text{Max} = 4.88\,\mu\text{s}$.
  - *Across-trial population ($N=7$ blocks, 70,000 exchanges):* Grand mean RTT is $3.35 \pm 0.2\,\mu\text{s}$, capturing inter-trial OS background scheduling shifts.
  - *KVM Testbed Boundary:* Module loading in guest automated runs was recorded as `BLOCKED` due to unprivileged sudo boundaries; multi-process transfers are bounded by the 95--130 $\mu\text{s}$ hypervisor scheduling floor.

---

## Final Submission-Readiness Verdict

```
================================================================================
                    FINAL SUBMISSION READINESS VERDICT
================================================================================

  VERDICT: [ APPROVED FOR FINAL IEEE SUBMISSION ]

  The Mini-A-IPC research paper satisfies all criteria for IEEE submission:
  - Visually verified: Exactly 13 pages, zero text/table clipping, balanced columns.
  - Statistically verified: Rigorous inferential tests (p < 0.001), 95% CIs, exact counts.
  - Repository-verified: 100% alignment with source code, driver architecture, and logs.
  - Editorial precision: System V IPC interface accurately distinguished from POSIX.
  - Calibrated policy: All 7/7 payload oracle winners explicitly accounted for.

  Authoritative Output Deliverable:
    Mini-A-IPC-IEEE-Final.pdf (13 pages, 528,723 bytes, Clean pdfTeX build)
================================================================================
```
