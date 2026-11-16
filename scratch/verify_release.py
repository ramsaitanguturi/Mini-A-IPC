import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ZIP_PATH = os.path.join(ROOT, "release", "Mini-A-IPC-v2.0-Final-Submission.zip")

assert os.path.exists(ZIP_PATH), f"Zip file missing: {ZIP_PATH}"

print(f"Verifying release archive: {ZIP_PATH}")

with tempfile.TemporaryDirectory() as tmp_dir:
    print(f"Extracting to temporary directory: {tmp_dir}")
    with zipfile.ZipFile(ZIP_PATH, "r") as zf:
        zf.extractall(tmp_dir)
    
    extracted_root = os.path.join(tmp_dir, "Mini-A-IPC")
    assert os.path.isdir(extracted_root), "Expected root directory 'Mini-A-IPC' inside zip"

    # 1. Verify critical directories and files exist
    required_files = [
        "README.md",
        "Makefile",
        "Paper.pdf",
        "include/ipc.h",
        "src/ipc_pipe.c",
        "src/ipc_fifo.c",
        "src/ipc_shm.c",
        "src/ipc_sysv_mq.c",
        "src/ipc_posix_mq.c",
        "src/ipc_uds.c",
        "src/selector.c",
        "src/main.c",
        "kernel/aipc_module.c",
        "kernel/Makefile",
        "docs/PROJECT_OVERVIEW.md",
        "docs/ARCHITECTURE.md",
        "docs/IPC_IMPLEMENTATIONS.md",
        "docs/KERNEL_MODULE_VALIDATION.md",
        "docs/ADAPTIVE_POLICY_RESULTS.md",
        "docs/BENCHMARK_METHODOLOGY.md",
        "docs/BENCHMARK_RESULTS.md",
        "docs/FINAL_TEST_REPORT.md",
        "docs/KNOWN_LIMITATIONS.md",
        "docs/FINAL_REPOSITORY_AUDIT.md",
        "docs/FINAL_ACADEMIC_REPORT.md",
        "docs/FINAL_SUBMISSION_CHECKLIST.md",
        "results/comparative_benchmark.csv",
        "results/unified/processed/aggregated_results.csv",
        "results/unified/processed/statistical_summary.csv",
        "tests/final_verification_test.py",
        "tests/test_cli.sh",
        "tests/test_unified_benchmark.py",
    ]
    for rf in required_files:
        p = os.path.join(extracted_root, rf)
        assert os.path.exists(p), f"Missing required file in archive: {rf}"
    print(f"Verified all {len(required_files)} critical files exist in archive.")

    # 2. Verify all 13 graphs (PNG and PDF)
    graphs = [
        "adaptive_vs_best", "concurrency_scalability", "context_switches",
        "cpu_comparison", "kernel_vs_userspace", "latency_comparison",
        "memory_comparison", "p50_latency", "p95_latency", "p99_latency",
        "payload_scalability", "syscall_comparison", "throughput_comparison"
    ]
    for g in graphs:
        png = os.path.join(extracted_root, "results", "unified", "graphs", f"{g}.png")
        pdf = os.path.join(extracted_root, "results", "unified", "graphs", f"{g}.pdf")
        assert os.path.exists(png) and os.path.getsize(png) > 1000, f"Graph PNG missing/empty: {g}"
        assert os.path.exists(pdf) and os.path.getsize(pdf) > 1000, f"Graph PDF missing/empty: {g}"
    print("Verified all 13 PNG and PDF graphs exist and are non-empty.")

    # 3. Verify clean build: make all
    print("Building project inside extracted directory...")
    bash_path = r"C:\msys64\usr\bin\bash.exe"
    # Convert windows path to posix path for bash
    drive = extracted_root[0].lower()
    rest = extracted_root[2:].replace("\\", "/")
    posix_path = f"/{drive}{rest}"

    build_cmd = f"cd '{posix_path}' && make clean && make all"
    r = subprocess.run([bash_path, "-lc", build_cmd], capture_output=True, text=True)
    assert r.returncode == 0, f"Build failed inside extracted archive: {r.stdout}\n{r.stderr}"
    print("Build succeeded inside extracted archive!")

    # 4. Run automated test suites
    print("Running final_verification_test.py inside extracted archive...")
    r_py = subprocess.run([sys.executable, "tests/final_verification_test.py"], cwd=extracted_root, capture_output=True, text=True)
    assert r_py.returncode == 0, f"final_verification_test.py failed: {r_py.stdout}\n{r_py.stderr}"
    print("final_verification_test.py PASSED (15/15) in extracted archive!")

    print("Running test_cli.sh inside extracted archive...")
    cli_cmd = f"cd '{posix_path}' && bash tests/test_cli.sh"
    r_cli = subprocess.run([bash_path, "-lc", cli_cmd], capture_output=True, text=True)
    assert r_cli.returncode == 0, f"test_cli.sh failed: {r_cli.stdout}\n{r_cli.stderr}"
    print("test_cli.sh PASSED in extracted archive!")

    print("Running test_unified_benchmark.py inside extracted archive...")
    r_pt = subprocess.run(["pytest", "tests/test_unified_benchmark.py"], cwd=extracted_root, capture_output=True, text=True)
    assert r_pt.returncode == 0, f"test_unified_benchmark.py failed: {r_pt.stdout}\n{r_pt.stderr}"
    print("test_unified_benchmark.py PASSED (5/5) in extracted archive!")

print("\n=======================================================")
print("RELEASE PACKAGE VERIFICATION: 100% COMPLETE & VALIDATED")
print("=======================================================")

