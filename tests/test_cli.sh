#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
make

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
pass "adaptive routes oversized payload to pipe"

if ./mini-aipc --mode shm --size 1025 --count 1 >/tmp/aipc_oversize.out 2>&1; then
  fail "shared-memory oversized payload should fail"
fi
pass "shared-memory rejects oversized payload"

if ./mini-aipc --mode pipe --size 0 --count 1 >/tmp/aipc_zero_size.out 2>&1; then
  fail "zero size should fail"
fi
if ./mini-aipc --mode pipe --size 64 --count 0 >/tmp/aipc_zero_count.out 2>&1; then
  fail "zero count should fail"
fi
if ./mini-aipc --mode nope --size 64 --count 1 >/tmp/aipc_bad_mode.out 2>&1; then
  fail "invalid mode should fail"
fi
if ./mini-aipc --mode pipe --size nope --count 1 >/tmp/aipc_bad_size.out 2>&1; then
  fail "non-numeric size should fail"
fi
pass "invalid arguments rejected"

rm -f /tmp/aipc_pipe.out /tmp/aipc_shm.out /tmp/aipc_adaptive.out \
  /tmp/aipc_oversize.out /tmp/aipc_zero_size.out /tmp/aipc_zero_count.out \
  /tmp/aipc_bad_mode.out /tmp/aipc_bad_size.out
echo "All CLI correctness tests passed."
