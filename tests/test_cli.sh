#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
make all

pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; exit 1; }

./mini-aipc --mode pipe --size 64 --count 100 >/tmp/aipc_pipe.out || fail "pipe correctness"
grep -q 'Validation errors: 0' /tmp/aipc_pipe.out || fail "pipe validation"
pass "pipe round-trip"

./mini-aipc --mode shm --size 64 --count 100 >/tmp/aipc_shm.out || fail "shared-memory correctness"
grep -q 'Validation errors: 0' /tmp/aipc_shm.out || fail "shared-memory validation"
pass "shared-memory round-trip"

./mini-aipc --mode adaptive --size 16384 --count 100 >/tmp/aipc_adaptive.out || fail "adaptive large payload"
grep -q 'Selected transport: pipe' /tmp/aipc_adaptive.out || fail "large payload should select pipe"
pass "adaptive routes large payload to pipe"

if ./mini-aipc --mode shm --size 1025 --count 1 >/tmp/aipc_oversize.out 2>&1; then
  fail "shared-memory oversized payload should fail"
fi
pass "shared-memory rejects oversized payload"

for args in \
  "--mode pipe --size 0 --count 1" \
  "--mode pipe --size 64 --count 0" \
  "--mode nope --size 64 --count 1" \
  "--mode pipe --size nope --count 1" \
  "--mode pipe --size -1 --count 1"; do
  if ./mini-aipc $args >/dev/null 2>&1; then fail "invalid arguments accepted: $args"; fi
done
pass "invalid arguments rejected"

# Child-exit fault injection verifies the parent returns rather than hanging
# on a broken pipe or an unposted semaphore. timeout turns hangs into failures.
if timeout 5s env AIPC_TEST_CHILD_EXIT=pipe ./mini-aipc --mode pipe --size 64 --count 100 >/tmp/aipc_pipe_child_exit.out 2>&1; then
  fail "pipe child-exit fault should fail"
else
  code=$?
  [[ "$code" -ne 124 ]] || fail "parent hung after pipe child exit"
fi
pass "pipe child exit handled without SIGPIPE termination or hang"

if timeout 5s env AIPC_TEST_CHILD_EXIT=shm ./mini-aipc --mode shm --size 64 --count 100 >/tmp/aipc_shm_child_exit.out 2>&1; then
  fail "shared-memory child-exit fault should fail"
else
  code=$?
  [[ "$code" -ne 124 ]] || fail "parent hung on semaphore after child exit"
fi
pass "shared-memory child exit detected while waiting"

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
