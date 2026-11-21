# CHANGELOG: Mini-A-IPC IEEE Research Paper Quality Redesign

This document details the complete redesign and final submission polish of the Mini-A-IPC IEEE research paper directly within the repository (`IEEE_Mini_A_IPC_Paper/`), elevating its visual typography, scientific visualizations, technical diagrams, and empirical rigor to match and exceed the publication standards of the reference report (`FlexGuard_vs_Futex_IEEE_Report_4vCPU.pdf`).

---

## 1. Final Scientific and IEEE Validation — main(8).pdf (Camera-Ready Polish)

- **Title Block Refinement — Email Removal (Page 1):**
  - Completely removed the Email field (`Email: {124cs0037, 124cs0038}@iiitk.ac.in, srinivas@iiitk.ac.in`) from the title block per submission guidelines.
  - Strictly preserved paper title, student author names and roll numbers (`Tanguturi Ram Sai (124CS0037)*`, `Ayush Naresh Gatla (124CS0038)*`), course instructor designation (`Dr. N. Srinivas Naik†`), department, and institutional affiliation (IIITDM Kurnool).
  - Verified balanced vertical margins and spacing across the title block, abstract, and two-column body text.

- **Statistical Methodology Reconciled (Pages 11–12):**
  - Resolved the apparent contradiction between "matched trial blocks ($N=7$)" in Table IV and "independent randomized sweeps" in Section VIII-B.
  - Inspected `bench/analyze_results.py` (lines 570–606) and raw trial datasets (`results/unified/raw/all_results.csv`).
  - Confirmed the experimental setup is a **randomized block design** ($N = 7$ blocks): in every trial block $k \in \{1,\dots,7\}$, both Anonymous Pipes and Adaptive were executed under identical environmental conditions.
  - Confirmed the comparison is strictly **paired by trial block**, making the **paired Student's $t$-test** the statistically appropriate test.
  - Verified exact parameters from `results/unified/processed/statistical_summary.csv`:
    $$t = -0.1894, \quad p = 0.856037 \approx \mathbf{0.86}, \quad \text{df} = 6, \quad \text{Wilcoxon } W = 11.0, \; p = 0.6875$$
  - Updated Section VIII-B and the Table IV footnote to clarify that the $-3.27\%$ empirical regret reflects within-block hypervisor scheduling jitter between the two executions rather than unpaired independent sweeps, confirmed statistically indistinguishable from zero ($p = 0.86$).

- **Candidate Accuracy Definition & Cross-Document Alignment (Table IV):**
  - Confirmed that the candidate comparison is strictly **POSIX SHM versus Anonymous Pipe** (the two mechanisms routed by the static selector in `src/selector.c`).
  - Verified all 4 core summary metrics:
    - **Candidate Accuracy (SHM vs. Pipe):** **71.43%** (5 of 7 payload classes select the faster candidate: 64 B, 256 B, 4 KB, 16 KB, 64 KB; Pipe chosen exclusively $>1024$ B due to bounded SHM mailbox capacity).
    - **Global Selection Accuracy (vs. 6 Mechanisms):** **14.29%** (1 of 7 payload classes, matching global oracle at 16 KB).
    - **Mean Intra-Trial Latency Regret:** **27.68%** across workloads ($+7.08\%, +27.69\%, +12.66\%, +13.69\%, -3.27\%, +22.94\%, +112.97\%$).
    - **Offline 3-Tier Policy Calibration:** **100.00%** (7 of 7 payload classes match empirical optimum).
  - Aligned definitions, values, and calculations across Table IV, Figure 8, Section VIII-B, Abstract, and Section IX.

- **Confidence Taxonomy & Descriptive Lead Clarification (Table VII):**
  - Clarified that System V MQ's low-payload lead ($123.33\,\mu\text{s}$ at 64 B, $115.13\,\mu\text{s}$ at 256 B) represents a **descriptive sample lead** within the hypervisor scheduling noise band, rather than a statistically significant separation ($p \ge 0.05$ across the userspace cluster under the KVM floor).
  - Changed Table VII Confidence column for System V MQ from `High` to **`Descriptive`**.
  - Added a formal taxonomy footnote to Table VII:
    - *High*: Statistically significant separation ($\alpha = 0.05$) or deterministic OS telemetry.
    - *Descriptive*: Consistent sample-mean ranking without statistically significant separation ($p \ge 0.05$).
    - *Supported*: Empirically calibrated structural model.
  - Aligned the descriptive qualification across Section VII-A, Section VIII-H (*RQ1*), Section VIII-I (*Threats to Validity*), the Abstract, and Section IX (*Conclusion*).

- **13-Page Budget and Column Balance Preserved:**
  - Compacted Table V (`tables/hypotheses.tex`) and Table VI (`tables/recommendations.tex`) row spacing (`\arraystretch{0.98}`, `\addlinespace[1.2pt]`), pulling Section VIII completely onto Page 12.
  - Page 13 opens at the top of Column 1 with Table VII and Section IX (*Conclusion and Future Work*), followed by `References [1]--[12]` in Column 2.
  - Balanced symmetrically via `\balance` in Column 1 with 0 balance warnings and 0 overflow pages (exactly 13 pages).

---

## 2. Previous Polish — main(7).pdf Refinement
- **Author Block Metadata (Page 1):**
  - Supplied official student author and course instructor details:
    - Tanguturi Ram Sai (`124CS0037`) and Ayush Naresh Gatla (`124CS0038`)
    - Course: Operating Systems (`CS303/CS353`)
    - Course Instructor: Dr. N. Srinivas Naik
    - Department of Computer Science and Engineering, IIITDM Kurnool, India
- **Architecture Diagram (Page 4, Figure 1):**
  - Expanded subsystem horizontal spacing to 2.30 cm.
  - Created open-corridor Workload Dispatch Bus below Banner B with framed label at $x=3.10$.
  - Routed Kernel Telemetry horizontally with 0.81 cm clearance separating it from the `/dev/aipc` Custom Mailbox label.
- **Adaptive Regret Graph Title (Page 11, Figure 8):**
  - Set title font to 8.0 pt with 4 pt padding in `scripts/generate_paper_graphs.py`; regenerated `figures/adaptive_vs_best.pdf` with zero clipping.
- **References IEEE Consistency:**
  - Formatted `posix2018standard` as `"IEEE Std. 1003.1-2017"`.
