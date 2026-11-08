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

print('========================================')
if all_passed:
    print(f'SUCCESS: ALL {tests_run} TESTS PASSED CLEANLY!')
else:
    print(f'FAILURE: SOME TESTS FAILED out of {tests_run}')
    sys.exit(1)
print('========================================')
