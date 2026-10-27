#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CLIENT="$ROOT/aipc-client"
DEVICE="${AIPC_DEVICE:-/dev/aipc}"

if [[ ! -e "$DEVICE" ]]; then
  echo "SKIP: $DEVICE is absent. Build and load kernel/aipc_module.ko first." >&2
  exit 77
fi
if [[ ! -x "$CLIENT" ]]; then make -C "$ROOT" aipc-client; fi

# Requires an empty device at test start; the module has one global shared queue.
python3 - "$DEVICE" <<'PY'
import errno, os, sys
path = sys.argv[1]
fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
try:
    try:
        os.read(fd, 1)
    except BlockingIOError as e:
        assert e.errno == errno.EAGAIN
    else:
        raise SystemExit("FAIL: expected empty nonblocking read to return EAGAIN; start with an empty mailbox")
finally:
    os.close(fd)
print("PASS: empty nonblocking read returns EAGAIN")
PY

# A separate reader process and writer process demonstrate inter-process IPC.
msg="producer-consumer-$(date +%s%N)-$$"
expected="$ROOT/results/kernel-consumer.expected"
actual="$ROOT/results/kernel-consumer.actual"
printf '%s' "$msg" > "$expected"
"$CLIENT" read-exact "${#msg}" > "$actual" &
reader_pid=$!
sleep 0.1
"$CLIENT" write "$msg"
wait "$reader_pid"
cmp -s "$expected" "$actual"
rm -f "$expected" "$actual"
echo "PASS: independent producer and consumer exchange exact bytes"

# Fill the queue using nonblocking writes, prove full-buffer EAGAIN, then drain
# it completely and prove the empty-buffer condition again. Data is binary-safe.
python3 - "$DEVICE" <<'PY'
import errno, os, sys
path = sys.argv[1]
fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
chunk = b'K' * 4096
written = 0
try:
    while True:
        try:
            n = os.write(fd, chunk)
            if n <= 0:
                raise SystemExit("FAIL: nonblocking write made no progress")
            written += n
        except BlockingIOError as e:
            if e.errno != errno.EAGAIN:
                raise
            break
    if written <= 0:
        raise SystemExit("FAIL: could not fill buffer")
    try:
        os.write(fd, b'X')
    except BlockingIOError as e:
        assert e.errno == errno.EAGAIN
    else:
        raise SystemExit("FAIL: write to full buffer did not return EAGAIN")
    drained = 0
    while True:
        try:
            data = os.read(fd, 8192)
            if not data:
                break
            drained += len(data)
        except BlockingIOError as e:
            if e.errno != errno.EAGAIN:
                raise
            break
    if drained != written:
        raise SystemExit(f"FAIL: buffer integrity mismatch written={written} drained={drained}")
    try:
        os.read(fd, 1)
    except BlockingIOError as e:
        assert e.errno == errno.EAGAIN
    else:
        raise SystemExit("FAIL: expected EAGAIN after draining buffer")
finally:
    os.close(fd)
print(f"PASS: full/empty limits and byte integrity ({written} bytes) ")
PY

echo "PASS: kernel device tests completed"
