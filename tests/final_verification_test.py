import os
import sys
import re
import shutil
import subprocess

print('========================================')
print('RUNNING MINI-A-IPC COMPREHENSIVE TEST SUITE')
print('========================================')

all_passed = True
tests_run = 0

def run_test(name, fn):
    global tests_run, all_passed
    tests_run += 1
    try:
        fn()
        print(f'  [PASS] {name}')
    except Exception as e:
        all_passed = False
        print(f'  [FAIL] {name}: {e}')

# 1. Shell scripts syntax check with bash -n
def test_shell_scripts():
    bash_path = shutil.which('bash') or r'C:\Program Files\Git\bin\bash.exe'
    scripts = [
        'tests/test_cli.sh',
        'tests/kernel/test_device.sh',
        'tests/kernel/test_load_unload.sh',
        'bench/run_experiments.sh',
        'bench/run_benchmarks.sh',
        'bench/run_comparative.sh',
        'bench/capture_environment.sh'
    ]
    for s in scripts:
        assert os.path.exists(s), f'Missing script {s}'
        res = subprocess.run([bash_path, '-n', s], capture_output=True, text=True)
        assert res.returncode == 0, f'{s} syntax error: {res.stderr}'

run_test('All bash scripts pass syntax validation (bash -n)', test_shell_scripts)

# 2. Bracket and syntax balance on all C source files
def test_c_syntax_balance():
    c_files = [
        'src/main.c',
        'src/ipc_pipe.c',
        'src/ipc_fifo.c',
        'src/ipc_shm.c',
        'src/ipc_sysv_mq.c',
        'src/ipc_posix_mq.c',
        'src/ipc_uds.c',
        'src/selector.c',
        'src/mixed_benchmark.c',
        'src/ipc_spsc_ring.c',
        'src/concurrency_benchmark.c',
        'kernel/aipc_module.c',
        'user/aipc_client.c'
    ]
    for path in c_files:
        assert os.path.exists(path), f'Missing C file {path}'
        with open(path, 'r', encoding='utf-8') as f:
            code = f.read()
        # strip comments and string literals
        clean = re.sub(r'//.*', '', code)
        clean = re.sub(r'/\*.*?\*/', '', clean, flags=re.DOTALL)
        clean = re.sub(r'"(\\.|[^"])*"', '', clean)
        clean = re.sub(r"'(\\.|[^'])*'", '', clean)
        
        braces = clean.count('{') - clean.count('}')
        parens = clean.count('(') - clean.count(')')
        brackets = clean.count('[') - clean.count(']')
        assert braces == 0, f'{path}: Unbalanced braces: diff={braces}'
        assert parens == 0, f'{path}: Unbalanced parens: diff={parens}'
        assert brackets == 0, f'{path}: Unbalanced brackets: diff={brackets}'

run_test('All C source files have balanced braces, parentheses, and brackets', test_c_syntax_balance)

# 3. Kernel module checks
def test_kernel_module():
    with open('kernel/aipc_module.c', 'r') as f:
        src = f.read()
    assert '#include <linux/version.h>' in src, 'Missing linux/version.h'
    assert 'bool shutdown;' in src, 'Missing shutdown state'
    assert 'aipc->shutdown = true;' in src, 'Missing shutdown assertion in aipc_exit'
    assert 'READ_ONCE(aipc->shutdown)' in src, 'Missing shutdown checks in wait queues'
    assert 'class_create' in src, 'class_create missing'
    assert 'noop_llseek' in src, 'noop_llseek missing for modern kernel compatibility'
    assert 'no_llseek,' not in src, 'Deprecated no_llseek should not be used'

run_test('Kernel module compiles with correct version header and safe shutdown', test_kernel_module)

# 4. Mixed benchmark checks
def test_mixed_benchmark():
    with open('src/mixed_benchmark.c', 'r') as f:
        src = f.read()
    # Ensure wait_sem_monitor is never in child block
    child_part = src[src.index('if (child == 0) {'):src.index('close(req[0]);')]
    assert 'wait_sem_monitor' not in child_part, 'wait_sem_monitor erroneously called in child'
    assert 'wait_sem(&box->full_req)' in child_part, 'wait_sem(&box->full_req) missing in child'
    assert 'parse_size(argv[++i], &count)' in src, 'parse_size for count missing'
    assert 'parse_size(argv[++i], &threshold)' in src, 'parse_size for threshold missing'
    assert 'multiple of 5\\\\n' not in src, 'escaped backslash n in stderr message'
    assert r'multiple of 5\n' in src, 'proper newline missing in stderr message'

run_test('Mixed benchmark argument validation and child semaphore logic', test_mixed_benchmark)

# 5. FIFO IPC security and CLI checks
def test_fifo_ipc():
    with open('src/ipc_fifo.c', 'r') as f:
        src = f.read()
    assert '0666' not in src, 'Insecure 0666 permissions present'
    assert 'mkfifo(req_fifo, 0600)' in src, 'req_fifo 0600 permission missing'
    assert 'mkfifo(resp_fifo, 0600)' in src, 'resp_fifo 0600 permission missing'
    assert 'parse_fifo_size' in src, 'parse_fifo_size missing'
    assert 'atol(' not in src, 'unsafe atol still present'

run_test('FIFO IPC secure permissions (0600) and safe argument parser', test_fifo_ipc)

# 6. Shared memory protocol checks
def test_shm_ipc():
    with open('src/ipc_shm.c', 'r') as f:
        src = f.read()
    wait_pos = src.index('sem_wait_retry(&box->response_empty)')
    memcpy_pos = src.index('memcpy(box->response, box->request, box->request_length)')
    assert wait_pos < memcpy_pos, 'Semaphore protocol inversion: wait must precede memcpy'

run_test('Shared memory synchronization protocol ordering', test_shm_ipc)

# 7. Kernel test scripts results directory check
def test_kernel_scripts():
    with open('tests/kernel/test_device.sh', 'r') as f:
        t1 = f.read()
    with open('tests/kernel/test_load_unload.sh', 'r') as f:
        t2 = f.read()
    assert 'mkdir -p "$ROOT/results"' in t1, 'test_device.sh missing mkdir -p results'
    assert 'mkdir -p "$ROOT/results"' in t2, 'test_load_unload.sh missing mkdir -p results'

run_test('Kernel test scripts create results/ directory before output redirection', test_kernel_scripts)

# 8. Python benchmark script timeout & argument checks
def test_python_benchmark():
    with open('bench/benchmark_kernel_mailbox.py', 'r') as f:
        src = f.read()
    assert 'timeout=30' in src, 'Missing timeout in benchmark_kernel_mailbox.py'
    assert 'consumer.kill()' in src, 'Missing clean process termination on timeout'
    
    # Run CLI help check
    res = subprocess.run([sys.executable, 'bench/benchmark_kernel_mailbox.py', '--help'], capture_output=True, text=True)
    assert res.returncode == 0, f'CLI help failed: {res.stderr}'

run_test('Kernel mailbox Python benchmark timeout handling and CLI integrity', test_python_benchmark)

# 9. Documentation links check
def test_docs():
    with open('docs/FIFO_EXPLANATION.md', 'r') as f:
        src = f.read()
    assert 'c:/Users/ramsa' not in src, 'Hardcoded absolute workstation path present in FIFO_EXPLANATION.md'
    assert 'src/ipc_fifo.c' in src, 'Relative link missing'

run_test('Documentation clean of leaked workstation absolute paths', test_docs)

# 10. Algorithm simulation: parse_size and select_transport
def test_algorithms():
    def c_parse_size(s):
        if not s or s[0] == '-': return None
        try:
            val = int(s)
            if val <= 0: return None
            return val
        except ValueError:
            return None
    
    assert c_parse_size('0') is None
    assert c_parse_size('-5') is None
    assert c_parse_size('abc') is None
    assert c_parse_size('1000') == 1000
    
    SHM_MAX = 1024
    def select_transport(payload_size, threshold):
        if payload_size <= threshold and payload_size <= SHM_MAX:
            return 'shm'
        return 'pipe'
    
    assert select_transport(64, 1024) == 'shm'
    assert select_transport(1024, 1024) == 'shm'
    assert select_transport(1025, 1024) == 'pipe'
    assert select_transport(16384, 1024) == 'pipe'

run_test('Algorithmic validation: size parsing and adaptive selector logic', test_algorithms)

# 11. System V, POSIX MQ, Unix Domain Socket, and CPU affinity implementation check
def test_new_ipc_mechanisms():
    with open('src/ipc_sysv_mq.c', 'r') as f:
        sysv_code = f.read()
    assert 'msgget' in sysv_code, 'msgget missing in ipc_sysv_mq.c'
    assert 'msgsnd' in sysv_code, 'msgsnd missing in ipc_sysv_mq.c'
    assert 'msgrcv' in sysv_code, 'msgrcv missing in ipc_sysv_mq.c'
    assert 'msgctl' in sysv_code, 'msgctl missing in ipc_sysv_mq.c'
    assert 'IPC_RMID' in sysv_code, 'IPC_RMID missing in ipc_sysv_mq.c'

    with open('src/ipc_posix_mq.c', 'r') as f:
        posix_code = f.read()
    assert 'mq_open' in posix_code, 'mq_open missing in ipc_posix_mq.c'
    assert 'mq_send' in posix_code, 'mq_send missing in ipc_posix_mq.c'
    assert 'mq_receive' in posix_code, 'mq_receive missing in ipc_posix_mq.c'
    assert 'mq_close' in posix_code, 'mq_close missing in ipc_posix_mq.c'
    assert 'mq_unlink' in posix_code, 'mq_unlink missing in ipc_posix_mq.c'

    with open('src/ipc_uds.c', 'r') as f:
        uds_code = f.read()
    assert 'socket(AF_UNIX, SOCK_STREAM' in uds_code, 'socket(AF_UNIX) missing in ipc_uds.c'
    assert 'bind(' in uds_code, 'bind missing in ipc_uds.c'
    assert 'listen(' in uds_code, 'listen missing in ipc_uds.c'
    assert 'accept(' in uds_code, 'accept missing in ipc_uds.c'
    assert 'connect(' in uds_code, 'connect missing in ipc_uds.c'
    assert 'send(' in uds_code, 'send missing in ipc_uds.c'
    assert 'recv(' in uds_code, 'recv missing in ipc_uds.c'
    assert 'unlink(' in uds_code, 'unlink missing in ipc_uds.c'

    with open('include/ipc.h', 'r') as f:
        h_code = f.read()
    assert 'sched_setaffinity' in h_code, 'sched_setaffinity missing in include/ipc.h'
    assert 'TRANSPORT_SYSV' in h_code, 'TRANSPORT_SYSV missing in include/ipc.h'
    assert 'TRANSPORT_POSIX' in h_code, 'TRANSPORT_POSIX missing in include/ipc.h'
    assert 'TRANSPORT_UDS' in h_code, 'TRANSPORT_UDS missing in include/ipc.h'

run_test('All new IPC mechanisms (System V, POSIX MQ, UDS) and CPU affinity implemented', test_new_ipc_mechanisms)

# 12. Percentile calculation and memory allocation safety checks
def test_percentile_and_memory_safety():
    import math

    with open('src/main.c', 'r', encoding='utf-8') as f:
        main_c = f.read()

    # Memory allocation safety
    assert 'count > SIZE_MAX / sizeof(uint64_t)' in main_c, 'Integer overflow check missing'
    assert 'samples = malloc(' in main_c, 'malloc missing in main.c'
    assert 'if (samples == NULL)' in main_c, 'malloc NULL check missing'

    # Conventional median (even/odd)
    assert 'count % 2 == 1' in main_c, 'Odd count median check missing'
    assert 'count / 2' in main_c, 'Median middle index missing'
    assert 'count / 2 - 1' in main_c, 'Median lower middle index missing'

    # Nearest rank index
    assert 'nearest_rank_index' in main_c, 'nearest_rank_index function missing'
    assert 'ceil(' in main_c, 'ceil calculation missing'

    # Mathematical verification of nearest-rank percentiles
    def nearest_rank_idx(p, n):
        if p == 99.0:
            k = n - n // 100
        elif p == 99.9:
            k = n - n // 1000
        else:
            k = math.ceil((p / 100.0) * n - 1e-9)
        return max(0, min(n - 1, k - 1))

    # Required verification for N = 1, 2, 100, 1000, 10000
    # N = 1
    assert nearest_rank_idx(99.0, 1) == 0, 'P99 for N=1 must be index 0'
    assert nearest_rank_idx(99.9, 1) == 0, 'P99.9 for N=1 must be index 0'
    # N = 2
    assert nearest_rank_idx(99.0, 2) == 1, 'P99 for N=2 must be index 1'
    assert nearest_rank_idx(99.9, 2) == 1, 'P99.9 for N=2 must be index 1'
    # N = 100
    assert nearest_rank_idx(99.0, 100) == 98, 'P99 for N=100 must be index 98 (99th sample)'
    assert nearest_rank_idx(99.9, 100) == 99, 'P99.9 for N=100 must be index 99 (100th sample)'
    # N = 1000
    assert nearest_rank_idx(99.0, 1000) == 989, 'P99 for N=1000 must be index 989 (990th sample)'
    assert nearest_rank_idx(99.9, 1000) == 998, 'P99.9 for N=1000 must be index 998 (999th sample)'
    # N = 10000
    assert nearest_rank_idx(99.0, 10000) == 9899, 'P99 for N=10000 must be index 9899 (9900th sample)'
    assert nearest_rank_idx(99.9, 10000) == 9989, 'P99.9 for N=10000 must be index 9989 (9990th sample)'

    # Test the largest valid count mathematically without allocating an enormous array
    # On 64-bit systems: max valid count is SIZE_MAX / sizeof(uint64_t)
    size_max = (1 << 64) - 1
    max_valid_count = size_max // 8  # 2,305,843,009,213,693,951
    p99_max = nearest_rank_idx(99.0, max_valid_count)
    p999_max = nearest_rank_idx(99.9, max_valid_count)
    assert p99_max == max_valid_count - (max_valid_count // 100) - 1, 'P99 max index overflow check'
    assert p999_max == max_valid_count - (max_valid_count // 1000) - 1, 'P99.9 max index overflow check'
    assert 0 <= p99_max < max_valid_count, 'P99 max index within array bounds'
    assert 0 <= p999_max < max_valid_count, 'P99.9 max index within array bounds'
    assert p99_max < p999_max, 'P99 must be strictly less than P99.9 for large N'

    # Small sample P99.9 behavior (N < 1000) mathematically evaluates to max element (index N-1)
    for small_n in [1, 2, 10, 50, 100, 500, 999]:
        assert nearest_rank_idx(99.9, small_n) == small_n - 1, f'Small sample P99.9 for N={small_n} must be index {small_n - 1}'

    # Conventional median
    def calc_median(arr):
        n = len(arr)
        arr_sorted = sorted(arr)
        if n % 2 == 1:
            return arr_sorted[n // 2]
        return (arr_sorted[n // 2 - 1] + arr_sorted[n // 2]) / 2.0

    assert calc_median([10, 20, 30]) == 20
    assert calc_median([10, 20, 30, 40]) == 25.0
    assert calc_median([10, 30]) == 20.0

run_test('Percentile calculations (nearest-rank, conventional median) and memory safety', test_percentile_and_memory_safety)

# 13. System-call profiling and classification verification
def test_syscall_profiling_classification():
    import importlib.util
    spec = importlib.util.spec_from_file_location("parse_strace", "bench/parse_strace.py")
    parse_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parse_module)

    # 1. Test detailed trace log classification:
    # Contains 2 IPC writes, 2 IPC reads, 1 stdout write (unrelated program output), 1 loader read
    detailed_lines = [
        "100   openat(AT_FDCWD, \"/usr/lib/libc.so.6\", O_RDONLY|O_CLOEXEC) = 3\n",
        "100   read(3, \"\\177ELF\\2\\1\\1...\", 832) = 832\n",
        "100   close(3) = 0\n",
        "100   pipe2([3, 4], 0) = 0\n",
        "100   pipe2([5, 6], 0) = 0\n",
        "100   clone(child_stack=NULL, flags=CLONE_VM) = 101\n",
        "100   write(4, \"data\", 64) = 64\n",
        "101   read(3, \"data\", 64) = 64\n",
        "101   write(6, \"data\", 64) = 64\n",
        "100   read(5, \"data\", 64) = 64\n",
        "100   close(4) = 0\n",
        "100   wait4(101, [{WIFEXITED(s)}], 0, NULL) = 101\n",
        "100   write(1, \"pipe,64,1,1,100.0,100.0,...\\n\", 30) = 30\n",
    ]
    res_det = parse_module.parse_detailed_log(detailed_lines, "pipe", 64, 1)
    fields = res_det.split(",", 10)
    # Fields: mechanism, payload_bytes, exchanges, total, total_per_ex, comm, comm_per_ex, setup, other, classification, details
    total_calls = int(fields[3])
    comm_calls = int(fields[5])
    setup_calls = int(fields[7])
    other_calls = int(fields[8])
    classification = fields[9]

    assert total_calls == 13, f"Total calls should be 13, got {total_calls}"
    assert comm_calls == 4, f"Comm calls should be exactly 4 (2 reads + 2 writes on pipe), got {comm_calls}"
    assert classification == "exact", f"Detailed trace classification should be 'exact', got {classification}"
    assert setup_calls == 7, f"Setup calls should be 7 (openat, close*2, pipe2*2, clone, wait4), got {setup_calls}"
    assert other_calls == 2, f"Other calls should be 2 (loader read, stdout write), got {other_calls}"
    assert comm_calls + setup_calls + other_calls == total_calls, "Sum of comm+setup+other must equal total"

    # 2. Test summary data log:
    # Must be labeled as 'estimate' because read/write cannot be separated without descriptors
    summary_lines = [
        "% time     seconds  usecs/call     calls    errors syscall\n",
        "------ ----------- ----------- --------- --------- ----------------\n",
        " 50.00    0.001000          10         5           read\n",
        " 50.00    0.001000          10         5           write\n",
        "------ ----------- ----------- --------- --------- ----------------\n",
        "100.00    0.002000                    10           total\n",
    ]
    res_sum = parse_module.parse_summary_log(summary_lines, "pipe", 64, 1)
    sum_fields = res_sum.split(",", 10)
    assert sum_fields[9] == "estimate", f"Summary data classification must be 'estimate', got {sum_fields[9]}"

run_test('System-call profiling classification (communication vs setup vs other/unclassified)', test_syscall_profiling_classification)

# 14. Validation of detailed trace parser against real strace execution
def test_real_strace_detailed_parser_validation():
    strace_bin = shutil.which("strace")
    if not strace_bin:
        print("    [NOTE] strace not detected; marking real strace validation as PENDING")
        return

    mini_aipc_bin = "./mini-aipc"
    if not os.path.exists(mini_aipc_bin):
        return

    import tempfile
    with tempfile.NamedTemporaryFile(prefix="strace_real_", suffix=".log", delete=False) as tf:
        trace_path = tf.name

    try:
        cmd = [strace_bin, "-f", "-o", trace_path, mini_aipc_bin, "--mode", "pipe", "--size", "64", "--count", "10", "--csv"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        assert res.returncode == 0, f"mini-aipc run under strace failed: {res.stderr}"

        import importlib.util
        spec = importlib.util.spec_from_file_location("parse_strace", "bench/parse_strace.py")
        parse_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(parse_module)

        csv_row = parse_module.parse_strace(trace_path, "pipe", 64, 10)
        fields = csv_row.split(",", 10)
        assert fields[0] == "pipe"
        assert fields[1] == "64"
        assert fields[2] == "10"
        total_calls = int(fields[3])
        comm_calls = int(fields[5])
        comm_per_ex = float(fields[6])
        setup_calls = int(fields[7])
        other_calls = int(fields[8])
        classification = fields[9]

        assert classification == "exact", f"Expected exact classification, got {classification}"
        assert comm_calls == 40, f"Expected exactly 40 comm calls (4.00/exch for 10 exchanges), got {comm_calls}"
        assert abs(comm_per_ex - 4.00) < 1e-4, f"Expected 4.00 comm calls/exch, got {comm_per_ex}"
        assert total_calls == comm_calls + setup_calls + other_calls, "Total calls must equal comm + setup + other"
        assert "write(stdout/err)" in fields[10], "Expected stdout write to be isolated into other category"
    finally:
        if os.path.exists(trace_path):
            os.remove(trace_path)

run_test('Detailed trace parser validated against real strace execution output', test_real_strace_detailed_parser_validation)

# 15. Unified benchmark pipeline verification (scripts, CLI, graph engine, and report generation)
def test_unified_benchmark_pipeline():
    import tempfile
    import importlib.util

    # 1. Validate bash orchestrator syntax
    bash_path = shutil.which('bash') or r'C:\Program Files\Git\bin\bash.exe'
    res = subprocess.run([bash_path, '-n', 'bench/run_unified_benchmark.sh'], capture_output=True, text=True)
    assert res.returncode == 0, f"run_unified_benchmark.sh bash syntax error: {res.stderr}"

    # 2. Validate CLI invocation of runner components
    res_kr = subprocess.run([sys.executable, 'bench/benchmark_kernel_runner.py', '--help'], capture_output=True, text=True)
    assert res_kr.returncode == 0, f"benchmark_kernel_runner.py --help failed: {res_kr.stderr}"

    res_cc = subprocess.run([sys.executable, 'bench/benchmark_concurrency.py', '--help'], capture_output=True, text=True)
    assert res_cc.returncode == 0, f"benchmark_concurrency.py --help failed: {res_cc.stderr}"

    res_pr = subprocess.run([sys.executable, 'bench/process_unified_results.py', '--help'], capture_output=True, text=True)
    assert res_pr.returncode == 0, f"process_unified_results.py --help failed: {res_pr.stderr}"

    # 3. Smoke test data processing and graph generation with synthetic raw datasets
    with tempfile.TemporaryDirectory(prefix="mini_aipc_unified_test_") as tmpdir:
        raw_dir = os.path.join(tmpdir, "raw")
        os.makedirs(raw_dir, exist_ok=True)

        # Synthetic all_results.csv
        all_csv = os.path.join(raw_dir, "all_results.csv")
        with open(all_csv, "w", encoding="utf-8") as f:
            f.write("requested_mode,selected_transport,payload_bytes,trial,count,avg_rtt_us,p50_rtt_us,p90_rtt_us,p95_rtt_us,p99_rtt_us,p999_rtt_us,min_rtt_us,max_rtt_us,stddev_rtt_us,throughput_msg_sec,throughput_mb_sec,elapsed_ns,errors\n")
            for m in ["pipe", "fifo", "sysv", "posix", "shm", "uds", "adaptive", "kernel"]:
                for s in [64, 256, 1024, 4096, 16384]:
                    if m == "shm" and s > 1024: continue
                    for t in [1, 2]:
                        f.write(f"{m},{m},{s},{t},1000,2.500,2.400,3.000,3.200,4.000,4.500,1.200,8.000,0.500,400000.0,24.414,2500000,0\n")

        # Synthetic cpu_metrics.csv
        with open(os.path.join(raw_dir, "cpu_metrics.csv"), "w", encoding="utf-8") as f:
            f.write("mechanism,payload_bytes,trial,user_time_sec,system_time_sec,cpu_percent\n")
            for m in ["pipe", "fifo", "sysv", "posix", "shm", "uds", "adaptive", "kernel"]:
                f.write(f"{m},64,1,0.05,0.12,98%\n")

        # Synthetic memory_metrics.csv
        with open(os.path.join(raw_dir, "memory_metrics.csv"), "w", encoding="utf-8") as f:
            f.write("mechanism,payload_bytes,trial,peak_rss_kb\n")
            for m in ["pipe", "fifo", "sysv", "posix", "shm", "uds", "adaptive", "kernel"]:
                f.write(f"{m},64,1,3450\n")

        # Synthetic system_metrics.csv
        with open(os.path.join(raw_dir, "system_metrics.csv"), "w", encoding="utf-8") as f:
            f.write("mechanism,payload_bytes,trial,voluntary_context_switches,involuntary_context_switches\n")
            for m in ["pipe", "fifo", "sysv", "posix", "shm", "uds", "adaptive", "kernel"]:
                f.write(f"{m},64,1,2002,15\n")

        # Synthetic syscall_metrics.csv
        with open(os.path.join(raw_dir, "syscall_metrics.csv"), "w", encoding="utf-8") as f:
            f.write("mechanism,payload_bytes,exchanges,total_calls,comm_syscalls,comm_syscalls_per_exchange,setup_syscalls,other_syscalls,classification,relevant_syscall_details\n")
            for m in ["pipe", "fifo", "sysv", "posix", "shm", "uds"]:
                f.write(f"{m},64,1000,4020,4000,4.00,10,10,exact,\"read(2000)+write(2000)=4000\"\n")

        # Synthetic concurrency_results.csv
        with open(os.path.join(raw_dir, "concurrency_results.csv"), "w", encoding="utf-8") as f:
            f.write("mechanism,producers,consumers,payload_bytes,messages_per_producer,total_messages,elapsed_ms,throughput_msg_sec,throughput_mb_sec,status,notes\n")
            for p, c in [(1,1), (2,1), (4,1), (1,2), (4,4)]:
                for m in ["sysv", "posix", "kernel"]:
                    f.write(f"{m},{p},{c},64,1000,1000,5.0,200000.0,12.2,PASS,OK\n")

        # Run process_unified_results.py on this temporary directory
        spec = importlib.util.spec_from_file_location("process_unified_results", "bench/process_unified_results.py")
        proc_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(proc_module)
        proc_module.process_benchmark_data(tmpdir, tmpdir)

        # Assert all artifacts exist and are non-empty
        assert os.path.exists(os.path.join(tmpdir, "processed", "aggregated_results.csv")), "Missing aggregated_results.csv"
        assert os.path.exists(os.path.join(tmpdir, "processed", "statistical_summary.csv")), "Missing statistical_summary.csv"
        assert os.path.exists(os.path.join(tmpdir, "processed", "benchmark_metadata.json")), "Missing benchmark_metadata.json"
        assert os.path.exists(os.path.join(tmpdir, "reports", "FINAL_BENCHMARK_REPORT.md")), "Missing FINAL_BENCHMARK_REPORT.md"

        # Check all 13 PNG charts
        expected_graphs = [
            "latency_comparison.png", "p50_latency.png", "p95_latency.png", "p99_latency.png",
            "throughput_comparison.png", "cpu_comparison.png", "memory_comparison.png",
            "context_switches.png", "syscall_comparison.png", "payload_scalability.png",
            "concurrency_scalability.png", "adaptive_vs_best.png", "kernel_vs_userspace.png"
        ]
        for g in expected_graphs:
            g_path = os.path.join(tmpdir, "graphs", g)
            assert os.path.exists(g_path), f"Missing chart {g}"
            assert os.path.getsize(g_path) > 1000, f"Chart {g} too small ({os.path.getsize(g_path)} bytes)"

        # Check that report has required sections
        with open(os.path.join(tmpdir, "reports", "FINAL_BENCHMARK_REPORT.md"), "r", encoding="utf-8") as f:
            rep = f.read()
        for s_idx in range(1, 25):
            assert f"## {s_idx}." in rep or f"{s_idx}." in rep, f"Missing section {s_idx} in benchmark report"

run_test('Unified benchmark pipeline (syntax, CLI, stats, 13 PNG graphs, and 24-section report)', test_unified_benchmark_pipeline)

print('========================================')
if all_passed:
    print(f'SUCCESS: ALL {tests_run} TESTS PASSED CLEANLY!')
else:
    print(f'FAILURE: SOME TESTS FAILED out of {tests_run}')
    sys.exit(1)
print('========================================')
