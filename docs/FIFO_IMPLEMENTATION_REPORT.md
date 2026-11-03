# FIFO (Named Pipe) IPC Implementation Report

This report documents the design, implementation, verification, and integration of the **FIFO (Named Pipe)** Inter-Process Communication (IPC) mechanism into the **Mini A-IPC** project.

---

## 1. Executive Summary

FIFO (Named Pipe) support has been successfully integrated into Mini A-IPC alongside Anonymous Pipes, POSIX Shared Memory, and the Kernel Character Device Mailbox.

The implementation strictly adheres to the code simplicity guidelines:
- Approximately 170 lines in `src/ipc_fifo.c`.
- Employs only standard POSIX system calls: `mkfifo()`, `open()`, `read()`, `write()`, `close()`, `unlink()`, `fork()`, and `waitpid()`.
- Provides full duplex parent-child communication using two named pipes (`req_fifo` and `resp_fifo`).
- Implements deadlock-free opening order and handles partial transfers and `EINTR`.
- Guarantees complete cleanup of FIFO filesystem nodes on both success and error paths.
- Provides a standalone executable (`bin/ipc_fifo`) as well as multi-mode integration in `mini-aipc --mode fifo`.
- 100% of existing tests, mixed-workload calibration benchmarks, and newly added FIFO tests pass cleanly.

---

## 2. Files Created

1. **`src/ipc_fifo.c`**:
   The complete FIFO IPC implementation. Implements `write_all()`, `read_all()`, `ipc_fifo_run()`, and when compiled standalone (`-DIPC_FIFO_STANDALONE`), `monotonic_ns()` and `main()` for `bin/ipc_fifo`.
2. **`docs/FIFO_EXPLANATION.md`**:
   Comprehensive, beginner-friendly OS viva preparation guide explaining FIFO concepts, system calls, deadlock prevention, function walkthroughs, architecture diagrams, and 10 viva questions with detailed answers.
3. **`docs/FIFO_IMPLEMENTATION_REPORT.md`**:
   This final verification report.

---

## 3. Files Modified

1. **`include/ipc.h`**:
   - Added `TRANSPORT_FIFO` to `transport_t` enum.
   - Declared `int ipc_fifo_run(size_t payload_size, size_t count, uint64_t *elapsed_ns, size_t *errors);`.
2. **`src/selector.c`**:
   - Added `case TRANSPORT_FIFO: return "fifo";` in `transport_name()`.
   - Maintained existing adaptive selection logic without modifications.
3. **`src/main.c`**:
   - Added `--mode fifo` option to usage documentation and command-line argument parsing.
   - Dispatched `ipc_fifo_run` when `TRANSPORT_FIFO` is selected.
4. **`Makefile`**:
   - Added `bin/ipc_fifo` to targets and `all`.
   - Included `src/ipc_fifo.c` in `SOURCES` for `mini-aipc`.
   - Added standalone build rule for `bin/ipc_fifo` (`mkdir -p bin && $(CC) $(CFLAGS) -DIPC_FIFO_STANDALONE src/ipc_fifo.c -o $@ $(LDFLAGS)`).
   - Updated `clean` target to remove `bin/` directory.
5. **`tests/test_cli.sh`**:
   - Added tests for `mini-aipc --mode fifo`.
   - Added tests for standalone `bin/ipc_fifo` (default mode and argument mode).
   - Added FIFO cleanup verification (ensuring `/tmp/mini_aipc_*.fifo` are unlinked).
   - Added invalid argument checks for FIFO mode and `bin/ipc_fifo`.
   - Added child-exit fault injection test (`AIPC_TEST_CHILD_EXIT=fifo`) to ensure the parent handles unexpected child termination without hanging.
6. **`bench/run_benchmarks.sh`**:
   - Included `fifo` in the benchmark mode loop (`pipe`, `fifo`, `shm`, `adaptive`).
7. **`README.md`**:
   - Updated introduction and usage instructions with FIFO commands.
   - Added an ASCII architecture diagram displaying FIFO as an independent transport.
   - Added an explanation of FIFO, system calls, differences from anonymous pipes, advantages, and limitations.
8. **`docs/design.md`**:
   - Added architecture and synchronization details for FIFO mode.

---

## 4. FIFO Communication Workflow

```
+--------------------------------------------------------------------------+
| 1. Parent: mkfifo(req_fifo, 0666) & mkfifo(resp_fifo, 0666)              |
| 2. Parent: fork() child process                                          |
+--------------------------------------------------------------------------+
                     |                                       |
                     v (Parent Process)                      v (Child Process)
    +---------------------------------+     +---------------------------------+
    | 3a. open(req_fifo, O_WRONLY)    |     | 3b. open(req_fifo, O_RDONLY)    |
    |     blocks until reader opens   |     |     blocks until writer opens   |
    +---------------------------------+     +---------------------------------+
                     \                                     /
                      ==== Rendezvous on req_fifo Complete ====
                     /                                     \
    +---------------------------------+     +---------------------------------+
    | 4a. open(resp_fifo, O_RDONLY)   |     | 4b. open(resp_fifo, O_WRONLY)   |
    |     blocks until writer opens   |     |     blocks until reader opens   |
    +---------------------------------+     +---------------------------------+
                     \                                     /
                      === Rendezvous on resp_fifo Complete ===
                     /                                     \
    +---------------------------------+     +---------------------------------+
    | 5. write_all(req_fd, payload)   | --> | 6. read_all(req_fd, buffer)     |
    +---------------------------------+     +---------------------------------+
                                                             |
    +---------------------------------+     +---------------------------------+
    | 8. read_all(resp_fd, buffer)    | <-- | 7. write_all(resp_fd, buffer)   |
    +---------------------------------+     +---------------------------------+
                     |                                       |
    +---------------------------------+     +---------------------------------+
    | 9. Validate integrity (memcmp)  |     | 10. close(fds) & _exit(0)       |
    | 10. close(fds)                  |     +---------------------------------+
    | 11. waitpid(child, &status, 0)  |
    | 12. unlink(req_fifo, resp_fifo) |
    +---------------------------------+
```

### Deadlock Prevention Strategy
In POSIX, opening a FIFO for reading blocks until a writer connects, and vice-versa. A classic deadlock occurs if Parent opens `req_fifo` (WR) while Child opens `resp_fifo` (WR); both block waiting for readers that will never open. Mini A-IPC enforces a strict matching order:
- Both processes open `req_fifo` first: Parent (WR) <-> Child (RD).
- Both processes open `resp_fifo` second: Parent (RD) <-> Child (WR).
This symmetric handshake guarantees deadlock-free initialization.

---

## 5. Build Results

Compilation command:
```bash
make clean && make
```

Build log:
```
rm -rf mini-aipc mini-aipc-mixed aipc-client bin results/benchmark.csv results/calibration.csv results/threshold.txt results/mixed_workload.csv results/environment.txt
gcc -std=c11 -D_POSIX_C_SOURCE=200809L -Wall -Wextra -Wpedantic -O2 -Iinclude src/main.c src/ipc_pipe.c src/ipc_fifo.c src/ipc_shm.c src/selector.c -o mini-aipc -pthread -lrt
gcc -std=c11 -D_POSIX_C_SOURCE=200809L -Wall -Wextra -Wpedantic -O2 -Iinclude src/mixed_benchmark.c -o mini-aipc-mixed -pthread -lrt
gcc -std=c11 -D_POSIX_C_SOURCE=200809L -Wall -Wextra -Wpedantic -O2 -Iinclude user/aipc_client.c -o aipc-client
gcc -std=c11 -D_POSIX_C_SOURCE=200809L -Wall -Wextra -Wpedantic -O2 -Iinclude -DIPC_FIFO_STANDALONE src/ipc_fifo.c -o bin/ipc_fifo -pthread -lrt
```

Status: **Clean compilation. Zero warnings under `-std=c11 -Wall -Wextra -Wpedantic`.**

---

## 6. Test Results

Command:
```bash
make test
```

Test log:
```
bash ./tests/test_cli.sh
make[1]: Entering directory '/mnt/c/Users/ramsa/Desktop/mini-aipc'
make[1]: Nothing to be done for 'all'.
make[1]: Leaving directory '/mnt/c/Users/ramsa/Desktop/mini-aipc'
PASS: pipe round-trip
PASS: fifo round-trip
PASS: standalone bin/ipc_fifo default demonstration
PASS: standalone bin/ipc_fifo custom size and count
PASS: fifo cleanup verified
PASS: shared-memory round-trip
PASS: adaptive routes large payload to pipe
PASS: shared-memory rejects oversized payload
PASS: invalid arguments rejected
PASS: pipe child exit handled without SIGPIPE termination or hang
PASS: fifo child exit handled without hang
PASS: shared-memory child exit detected while waiting
PASS: mixed adaptive child exit detected
PASS: mixed shared-memory child independently rejects corrupt payload
All CLI correctness and failure-path tests passed.
```

### Direct Executable Invocations
1. Standalone default invocation:
```
$ ./bin/ipc_fifo
=== Mini A-IPC: Standalone FIFO (Named Pipe) Demonstration ===
FIFO IPC completed: 1 exchanges, 64 bytes each.
Elapsed: 159957 ns
Average round-trip latency: 159957.00 ns
Validation errors: 0
Response validated successfully: data integrity verified.
FIFO cleanup complete.
```

2. Multi-exchange invocation via `mini-aipc`:
```
$ ./mini-aipc --mode fifo --size 64 --count 1000
Requested mode: fifo
Selected transport: fifo
Payload: 64 bytes | Exchanges: 1000
Elapsed: 107359868 ns
Average round-trip latency: 107359.87 ns
Throughput: 9314.47 exchanges/s
Validation errors: 0
```

---

## 7. Limitations

1. **Independent Transport:**
   The FIFO transport is implemented as an independent IPC mechanism and standalone demonstration. In strict compliance with task instructions, the adaptive selector policy routes between Anonymous Pipes and Shared Memory based on payload size; it does not automatically select FIFO.
2. **Filesystem Dependency:**
   FIFOs depend on the availability of a writable directory (`/tmp`). Stale FIFOs created by abnormally terminated external processes must be unlinked.
3. **Double Copying:**
   Like anonymous pipes, data passing through a FIFO is copied from user space to kernel buffer and from kernel buffer to user space. It does not achieve zero-copy throughput like POSIX shared memory.

---

## 8. Confirmation of Non-Regression

- **Anonymous Pipe:** Fully functional; passes round-trip tests and child-exit fault handling.
- **POSIX Shared Memory:** Fully functional; bounded mailbox checks, semaphore synchronization, and corrupt payload rejection all pass.
- **Adaptive Selector:** Fully functional; continues to route large payloads to pipe and small payloads to shared memory without changes.
- **Kernel Module Client:** Builds cleanly; unaffected by user-space additions.
- **Mixed-Workload Calibration Script (`bench/run_experiments.sh`):** Fully functional; completed calibration and evaluation phases successfully.

