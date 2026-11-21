# IEEE Mini-A-IPC Research Paper: Compilation and Build Instructions

This document provides complete instructions for compiling the LaTeX source code of the Mini-A-IPC IEEE conference research paper into a publication-ready PDF.

---

## 1. Prerequisites

To compile the manuscript, ensure the following tools are installed:
- A modern TeX distribution: **TeX Live 2023+**, **MiKTeX 25+**, or **MacTeX**.
- PDFTeX engine: `pdflatex` (Version 3.141592653+).
- BibTeX: `bibtex` (Version 0.99d+).
- Python 3.10+ with `matplotlib` and `pandas` (only if regenerating the vector PDF figures from CSV datasets).

---

## 2. Standard Build Procedure

Open a terminal or command prompt, navigate to the `IEEE_Mini_A_IPC_Paper` directory, and execute the standard three-pass LaTeX build sequence:

### On Linux / macOS / Bash:
```bash
cd IEEE_Mini_A_IPC_Paper

# Pass 1: Parse document structure and generate citation keys
pdflatex -interaction=nonstopmode main.tex

# Pass 2: Compile BibTeX bibliography
bibtex main

# Pass 3: Resolve cross-references and citations
pdflatex -interaction=nonstopmode main.tex

# Pass 4: Finalize page layout, floats, and two-column balance
pdflatex -interaction=nonstopmode main.tex
```

### On Windows PowerShell:
```powershell
Set-Location IEEE_Mini_A_IPC_Paper
pdflatex -interaction=nonstopmode main.tex
bibtex main
pdflatex -interaction=nonstopmode main.tex
pdflatex -interaction=nonstopmode main.tex
```

The resulting compiled paper will be written to `IEEE_Mini_A_IPC_Paper/main.pdf`.

---

## 3. Regenerating Vector Plots (Optional)

The vector PDF plots in `figures/` are already pre-generated and included. If you modify any benchmark CSV datasets in `../results/unified/`, you can regenerate the figures using the provided Python script:

```bash
python scripts/generate_paper_graphs.py
```

This will automatically refresh:
- `figures/latency_comparison.pdf`
- `figures/throughput_comparison.pdf`
- `figures/percentile_comparison.pdf`
- `figures/resource_utilization.pdf`

---

## 4. Cleaning Auxiliary Build Files

To clean intermediate compilation files (`.aux`, `.log`, `.bbl`, `.blg`, `.out`):

### Linux / macOS:
```bash
rm -f *.aux *.log *.bbl *.blg *.out *.toc *.synctex.gz
rm -f sections/*.aux figures/*.aux tables/*.aux
```

### Windows PowerShell:
```powershell
Remove-Item *.aux, *.log, *.bbl, *.blg, *.out -ErrorAction SilentlyContinue
Remove-Item sections/*.aux, figures/*.aux, tables/*.aux -ErrorAction SilentlyContinue
```
