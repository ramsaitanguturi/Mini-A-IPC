# Mini-A-IPC IEEE Paper: Comprehensive Change Log

**Document Version:** 4.0.0 (Version 11 Final Numerical Consistency Audit Changelog)  
**Date:** November 22, 2026  
**Auditor:** Senior Linux Systems Researcher, Experimental Statistics Auditor & IEEE Manuscript Reviewer  
**Target Repository:** `Mini-A-IPC`  
**Paper Directory:** `Mini_A_IPC_IEEE_Final/`  

---

## 0. Version 11.0 Final Numerical Consistency Audit (November 22, 2026)

### 1. Candidate Accuracy Discrepancy Resolution
- **Issue Investigated:** Table IV reported 71.43% candidate accuracy (5 of 7 classes). However, Table III displays across-trial mean RTT values where Anonymous Pipes outperform POSIX Shared Memory across all three payloads $\le 1$~KB ($129.84\,\mu\text{s}$ vs. $138.66\,\mu\text{s}$ at 64 B; $123.85\,\mu\text{s}$ vs. $128.69\,\mu\text{s}$ at 256 B; $131.33\,\mu\text{s}$ vs. $139.68\,\mu\text{s}$ at 1 KB). Because the static selector routes $\le 1$~KB to Shared Memory and $>1$~KB to Anonymous Pipes, it correctly selects the candidate only for the four sizes $>1$~KB (4 KB, 16 KB, 64 KB, 256 KB) where Shared Memory is unavailable, yielding $4/7 = 57.14\%$.
- **Provenance Traced:** Traced the historical 71.43% figure to preliminary uncalibrated baseline testing (`docs/ADAPTIVE_POLICY_RESULTS.md` Section 4.1 & `docs/BENCHMARK_RESULTS.md` Section 2) where Shared Memory had achieved lower latency than Pipes at 64 B ($286.87\,\mu\text{s}$ vs. $399.25\,\mu\text{s}$) and 256 B ($320.35\,\mu\text{s}$ vs. $344.57\,\mu\text{s}$), producing 5 of 7 correct choices.
- **Harmonization Applied:** To maintain 100% mathematical consistency with Table III, Candidate Accuracy has been corrected throughout the manuscript from 71.43% to **57.14% (4 of 7 classes)** across:
  - Abstract (`Mini-A-IPC-IEEE-Final.tex`)
  - Table IV (`tables/adaptive_results.tex` summary row and footnote)
  - Section VIII-B (`sections/08_discussion.tex` point 1)
  - Section VIII-F (`sections/08_discussion.tex` RQ3)
  - Table VII (`tables/summary_of_findings.tex`)
  - Section IX Conclusion (`sections/09_conclusion.tex`)
- **Mechanistic Context Documented:** Detailed how KVM hypervisor scheduling and POSIX semaphore wake-up contention elevate Shared Memory latency above Anonymous Pipes for small payloads, whereas buffer boundaries correctly constrain selection for $>1$~KB.

### 2. Kernel Mailbox Percentile Provenance & Integrity
- **Statistical Population Verified:**
  - Intra-trial percentiles ($\text{Min} = 0.84\,\mu\text{s}, P_{50} = 0.93\,\mu\text{s}, P_{90} = 0.99\,\mu\text{s}, P_{95} = 1.07\,\mu\text{s}, P_{99} = 1.90\,\mu\text{s}, \text{Max} = 4.88\,\mu\text{s}$) strictly represent **one representative low-noise trial block ($n = 10,000$ exchanges)** from native Fedora 45 driver loopback testing.
  - The reported maximum of $4.88\,\mu\text{s}$ belongs strictly to this same $n = 10,000$ population.
  - Across-trial mean of $3.35 \pm 0.2\,\mu\text{s}$ represents $N=7$ randomized blocks (70,000 pooled exchanges).
  - Explicitly documented the repository limitation: automated testbed runs in `results/unified/` recorded driver insertion as `BLOCKED` due to unprivileged KVM credentials, and native loopback telemetry was preserved in validation documentation rather than fabricating synthetic per-exchange traces.

### 3. Final Typesetting & Column Balance
- Compiled with zero errors, zero warnings.
- Exactly 13 pages (528,682 bytes).
- Page 13 column balance: Column 1 = 1,040 pixels, Column 2 = 1,038 pixels (2-pixel differential).
- Symmetrical margins across all 13 pages.

---

## 1. Version 10.0 Final Submission Audit (November 22, 2026)
- Section VIII-B: Fully expanded offline 3-tier policy description to explicitly map all seven empirical winners (including 16 KB Anonymous Pipes), confirming 100% (7/7) in-sample fit.
- Section I: Corrected description of six IPC mechanisms to "standards-based (encompassing POSIX-compliant primitives alongside the System V IPC interface)".
- Global consistency check conducted across all latency floor and mean RTT metrics.
