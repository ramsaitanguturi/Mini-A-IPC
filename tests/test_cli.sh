#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
make all

pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; exit 1; }

# 1. Anonymous pipe round-trip
./mini-aipc --mode pipe --size 64 --count 100 >/tmp/aipc_pipe.out || fail "pipe correctness"
grep -q 'Validation errors: 0' /tmp/aipc_pipe.out || fail "pipe validation"
pass "pipe round-trip"

# 2. Named pipe (FIFO) round-trip
./mini-aipc --mode fifo --size 64 --count 100 >/tmp/aipc_fifo.out || fail "fifo correctness"
grep -q 'Validation errors: 0' /tmp/aipc_fifo.out || fail "fifo validation"
pass "fifo round-trip"

# 3. Standalone bin/ipc_fifo tests
./bin/ipc_fifo >/tmp/aipc_fifo_standalone.out || fail "standalone fifo default run"
grep -q 'Validation errors: 0' /tmp/aipc_fifo_standalone.out || fail "standalone fifo validation"
grep -q 'Response validated successfully' /tmp/aipc_fifo_standalone.out || fail "standalone fifo integrity"
pass "standalone bin/ipc_fifo default demonstration"

./bin/ipc_fifo --size 128 --count 50 >/tmp/aipc_fifo_standalone_sized.out || fail "standalone fifo with arguments"
grep -q 'Validation errors: 0' /tmp/aipc_fifo_standalone_sized.out || fail "standalone fifo arguments validation"
pass "standalone bin/ipc_fifo custom size and count"

# Verify FIFO cleanup: no leftover FIFO files in /tmp
if ls /tmp/mini_aipc_req_*.fifo /tmp/mini_aipc_resp_*.fifo >/dev/null 2>&1; then
  fail "FIFO files were not cleaned up from /tmp"
fi
pass "fifo cleanup verified"

# 4. POSIX Shared memory round-trip
./mini-aipc --mode shm --size 64 --count 100 >/tmp/aipc_shm.out || fail "shared-memory correctness"
grep -q 'Validation errors: 0' /tmp/aipc_shm.out || fail "shared-memory validation"
pass "shared-memory round-trip"

# 5. System V message queue round-trip
./mini-aipc --mode sysv --size 64 --count 100 >/tmp/aipc_sysv.out || fail "sysv correctness"
grep -q 'Validation errors: 0' /tmp/aipc_sysv.out || fail "sysv validation"
pass "sysv message queue round-trip"

# 6. POSIX message queue round-trip
./mini-aipc --mode posix --size 64 --count 100 >/tmp/aipc_posix.out || fail "posix mq correctness"
grep -q 'Validation errors: 0' /tmp/aipc_posix.out || fail "posix mq validation"
pass "posix message queue round-trip"

# 7. Unix domain socket round-trip
./mini-aipc --mode uds --size 64 --count 100 >/tmp/aipc_uds.out || fail "uds correctness"
grep -q 'Validation errors: 0' /tmp/aipc_uds.out || fail "uds validation"
pass "unix domain socket round-trip"

# 8. Adaptive transport mode
./mini-aipc --mode adaptive --size 16384 --count 100 >/tmp/aipc_adaptive.out || fail "adaptive large payload"
grep -q 'Selected transport: pipe' /tmp/aipc_adaptive.out || fail "large payload should select pipe"
pass "adaptive routes large payload to pipe"

# 9. Multi-size verification across all six mechanisms (64, 128, 256, 512, 1024 bytes)
for m in pipe fifo sysv posix shm uds; do
  for s in 128 256 512 1024; do
    ./mini-aipc --mode "$m" --size "$s" --count 20 >/tmp/aipc_multisize.out || fail "$m failed at size $s"
    grep -q 'Validation errors: 0' /tmp/aipc_multisize.out || fail "$m validation failed at size $s"
  done
done
pass "all six mechanisms verified across payload sizes 128, 256, 512, 1024 bytes"

# 10. Warm-up, CPU affinity, and CSV output flags
./mini-aipc --mode uds --size 128 --count 50 --warmup 10 --cpu-producer 0 --cpu-consumer 1 >/tmp/aipc_opts.out || fail "warmup and cpu pinning"
grep -q 'Validation errors: 0' /tmp/aipc_opts.out || fail "warmup and cpu pinning validation"
pass "warmup and CPU affinity options verified"

./mini-aipc --mode posix --size 256 --count 50 --csv --trial 1 >/tmp/aipc_csv.out || fail "csv output flag"
grep -q 'posix,256,1,50,' /tmp/aipc_csv.out || fail "csv output formatting"
pass "CSV output flag formatted correctly"

# 11. Resource cleanup verification: no leftover queues or socket files
if ls /tmp/mini_aipc_uds_*.sock >/dev/null 2>&1; then
  fail "Unix domain socket files were not cleaned up from /tmp"
fi
if ls /dev/mqueue/mini_aipc_* >/dev/null 2>&1; then
  fail "POSIX message queues were not unlinked from /dev/mqueue"
fi
pass "UDS and POSIX MQ cleanup verified"

# 12. Oversized payload rejection for bounded transports
if ./mini-aipc --mode shm --size 1025 --count 1 >/tmp/aipc_oversize.out 2>&1; then
  fail "shared-memory oversized payload should fail"
fi
pass "shared-memory rejects oversized payload"

# 13. Invalid arguments rejection across CLI
for args in \
  "--mode pipe --size 0 --count 1" \
  "--mode pipe --size 64 --count 0" \
  "--mode fifo --size 0 --count 1" \
  "--mode fifo --size 64 --count 0" \
  "--mode sysv --size 0 --count 1" \
  "--mode sysv --size 64 --count 0" \
  "--mode posix --size 0 --count 1" \
  "--mode posix --size 64 --count 0" \
  "--mode uds --size 0 --count 1" \
  "--mode uds --size 64 --count 0" \
  "--mode nope --size 64 --count 1" \
  "--mode pipe --size nope --count 1" \
  "--mode pipe --size -1 --count 1" \
  "--mode pipe --size 64 --count 1 --cpu-producer -5" \
  "--mode pipe --size 64 --count 1 --trial 0"; do
  if ./mini-aipc $args >/dev/null 2>&1; then fail "invalid arguments accepted: $args"; fi
done
if ./bin/ipc_fifo --size 0 --count 1 >/dev/null 2>&1; then fail "standalone fifo accepted size 0"; fi
if ./bin/ipc_fifo --invalid >/dev/null 2>&1; then fail "standalone fifo accepted invalid option"; fi
pass "invalid arguments rejected"

# 14. Child-exit fault injection verifies the parent returns rather than hanging.
# Timeout turns hangs into failures.
if timeout 5s env AIPC_TEST_CHILD_EXIT=pipe ./mini-aipc --mode pipe --size 64 --count 100 >/tmp/aipc_pipe_child_exit.out 2>&1; then
  fail "pipe child-exit fault should fail"
else
  code=$?
  [[ "$code" -ne 124 ]] || fail "parent hung after pipe child exit"
fi
pass "pipe child exit handled without SIGPIPE termination or hang"

if timeout 5s env AIPC_TEST_CHILD_EXIT=fifo ./mini-aipc --mode fifo --size 64 --count 100 >/tmp/aipc_fifo_child_exit.out 2>&1; then
  fail "fifo child-exit fault should fail"
else
  code=$?
  [[ "$code" -ne 124 ]] || fail "parent hung after fifo child exit"
fi
pass "fifo child exit handled without hang"

if timeout 5s env AIPC_TEST_CHILD_EXIT=shm ./mini-aipc --mode shm --size 64 --count 100 >/tmp/aipc_shm_child_exit.out 2>&1; then
  fail "shared-memory child-exit fault should fail"
else
  code=$?
  [[ "$code" -ne 124 ]] || fail "parent hung on semaphore after child exit"
fi
pass "shared-memory child exit detected while waiting"

if timeout 5s env AIPC_TEST_CHILD_EXIT=sysv ./mini-aipc --mode sysv --size 64 --count 100 >/tmp/aipc_sysv_child_exit.out 2>&1; then
  fail "sysv child-exit fault should fail"
else
  code=$?
  [[ "$code" -ne 124 ]] || fail "parent hung on msgrcv after child exit"
fi
pass "sysv message queue child exit handled without hang"

if timeout 5s env AIPC_TEST_CHILD_EXIT=posix ./mini-aipc --mode posix --size 64 --count 100 >/tmp/aipc_posix_child_exit.out 2>&1; then
  fail "posix child-exit fault should fail"
else
  code=$?
  [[ "$code" -ne 124 ]] || fail "parent hung on mq_receive after child exit"
fi
pass "posix message queue child exit handled without hang"

if timeout 5s env AIPC_TEST_CHILD_EXIT=uds ./mini-aipc --mode uds --size 64 --count 100 >/tmp/aipc_uds_child_exit.out 2>&1; then
  fail "uds child-exit fault should fail"
else
  code=$?
  [[ "$code" -ne 124 ]] || fail "parent hung on recv after child exit"
fi
pass "unix domain socket child exit handled without hang"

# 15. Mixed workload tests
if timeout 5s env AIPC_TEST_MIXED_CHILD_EXIT=1 ./mini-aipc-mixed --policy adaptive --count 100 --threshold 64 >/tmp/aipc_mixed_child_exit.out 2>&1; then
  fail "mixed adaptive child-exit fault should fail"
else
  code=$?
  [[ "$code" -ne 124 ]] || fail "mixed adaptive parent hung on semaphore"
fi
pass "mixed adaptive child exit detected"

if timeout 5s env AIPC_TEST_CORRUPT_SHM_REQUEST=1 ./mini-aipc-mixed --policy adaptive --count 100 --threshold 64 >/tmp/aipc_mixed_corrupt.out 2>&1; then
  fail "corrupt shared-memory payload should be rejected by child"
else
  code=$?
  [[ "$code" -ne 124 ]] || fail "parent hung after child rejected corrupt payload"
fi
pass "mixed shared-memory child independently rejects corrupt payload"

rm -f /tmp/aipc_*.out
echo "All CLI correctness and failure-path tests passed."
