# IEEE Mini-A-IPC Research Paper

**Title:** Mini-A-IPC: Design, Implementation, and Performance Evaluation of Classical and Adaptive Inter-Process Communication Mechanisms in Linux  
**Institution:** Indian Institute of Information Technology Design and Manufacturing Kurnool  
**Department:** Department of Computer Science and Engineering  
**Format:** IEEE Two-Column Conference Paper Format (`IEEEtran.cls`, `\documentclass[conference]{IEEEtran}`)  
**Target Length:** 8–10 Pages, including References and Visualizations  

---

## 1. Directory Structure

```text
IEEE_Mini_A_IPC_Paper/
|-- main.tex                     # Primary LaTeX master document
|-- references.bib               # Verified IEEE BibTeX bibliographic database
|-- IEEEtran.cls                 # Canonical IEEEtran LaTeX document class
|-- main.pdf                     # Compiled publication-ready IEEE conference PDF
|
|-- sections/                    # Modular paper sections
|   |-- 01_introduction.tex      # Background, problem statement, contributions, RQs
|   |-- 02_related_work.tex       # IPC taxonomies, Danyliuk baseline, research gaps
|   |-- 03_architecture.tex      # 4-tier Mini-A-IPC framework architecture
|   |-- 04_ipc_implementation.tex# Detailed implementation mechanics of 6 IPC transports
|   |-- 05_adaptive_kernel.tex   # Regret math, EWMA telemetry, /dev/aipc driver design
|   |-- 06_methodology.tex       # Testbed specs, trial randomization, CPU core pinning
|   |-- 07_results.tex           # Empirical RTT, percentiles, throughput, syscall profiles
|   |-- 08_discussion.tex        # Concurrency scaling, adaptive evaluation, RQ answers
|   |-- 09_conclusion.tex        # Contribution summary, future research directions
|
|-- figures/                     # Vector graphics and TikZ diagrams
|   |-- architecture.tex         # Overall system architecture TikZ diagram (Fig. 1)
|   |-- ipc_mechanisms.tex       # Six IPC communication topologies TikZ diagram (Fig. 2)
|   |-- adaptive_selector.tex    # Adaptive telemetry flowchart TikZ diagram (Fig. 5a)
|   |-- kernel_mailbox.tex       # Kernel character device /dev/aipc TikZ diagram (Fig. 5b)
|   |-- benchmark_workflow.tex   # Experimental methodology workflow TikZ diagram (Fig. 6)
|   |-- latency_throughput_combined.pdf # Latency and wire bandwidth scaling 2-panel vector plot (Fig. 7)
|   |-- percentiles_resources_combined.pdf # Tail latency and classified syscalls 2-panel vector plot (Fig. 8)
|   |-- latency_comparison.pdf   # Round-trip latency scaling standalone vector plot
|   |-- throughput_comparison.pdf# Bandwidth throughput scaling standalone vector plot
|   |-- percentile_comparison.pdf# Tail latency distribution standalone bar chart
|   |-- resource_utilization.pdf # Classified communication system call standalone bar chart
|
|-- tables/                      # LaTeX tables
|   |-- ipc_comparison.tex       # Table I: Architectural comparison of 6 classical IPC transports
|   |-- environment.tex          # Table II: Experimental hardware, software testbeds, and workload sweep
|   |-- benchmark_results.tex    # Table III: Empirical round-trip latency across all payload sizes
|   |-- adaptive_results.tex     # Table IV: Adaptive selector accuracy and latency regret evaluation
|
|-- evidence/                    # Traceability and audit reports
|   |-- source_evidence_matrix.md# Line-by-line mapping of paper claims to C source code
|   |-- experiment_reconciliation.md # Multi-environment dataset reconciliation report
|   |-- reference_verification.md# Verification of all 15 academic references
|   |-- claim_verification.md    # Line-by-line verification of experimental numbers
|
|-- scripts/
|   |-- generate_paper_graphs.py # Matplotlib vector PDF graph generation script
|
|-- README.md                    # Project overview and metadata
|-- BUILD_INSTRUCTIONS.md        # Step-by-step reproduction and PDF compilation guide
```

---

## 2. Key Research Findings Summary

1. **Sub-Kilobyte Dominance of POSIX Shared Memory:** POSIX Shared Memory achieves the lowest round-trip latency for payloads $\le 256$~bytes ($286.87\,\mu\text{s}$ at 64~B) and completely eliminates data-path system calls (2.06 futex calls/exch vs. 4.00 for stream mechanisms).
2. **Intermediate Efficiency of Anonymous Pipes:** Anonymous Pipes achieve the lowest round-trip latency at 1~KB ($278.76\,\mu\text{s}$) and 4~KB ($301.70\,\mu\text{s}$), outperforming Shared Memory because Linux kernel pipe buffers absorb 1--4~KB writes without blocking or semaphore contention.
3. **Large-Payload Superiority of Unix Domain Sockets:** At 256~KB, Unix Domain Sockets outperform Anonymous Pipes by **1.756$\times$** ($2,590.28\,\mu\text{s}$ vs. $4,548.77\,\mu\text{s}$) due to pipe buffer saturation at 64~KB.
4. **Adaptive Selector Feasibility:** The static threshold selector delivers 71.43\% oracle accuracy with 29.51\% mean latency regret at a decision cost of only 2.36~ns. An empirically calibrated 3-tier policy eliminates structural regret entirely (100\% accuracy).
5. **Scheduler Context-Switch Floor:** The custom kernel mailbox (\texttt{/dev/aipc}) exhibits an uncontended loopback floor of $0.72\,\mu\text{s}$, while establishing that multi-process communication is bounded by the Linux CFS context-switch floor ($95\text{--}120\,\mu\text{s}$).

---

## 3. Author Information

Author placeholders have been established in `main.tex`:
```latex
\author{
    \IEEEauthorblockN{Student Author One\IEEEauthorrefmark{1}, Student Author Two\IEEEauthorrefmark{1}, and Faculty Supervisor\IEEEauthorrefmark{2}}
    ...
}
```
Please provide student names, author ordering, institutional emails, and supervisor details to update the author block.
