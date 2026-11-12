#!/usr/bin/env python3
"""
Mini A-IPC Kernel Mailbox Unified Benchmark Runner (/dev/aipc)

Evaluates the kernel-space circular ring buffer character device.
Supports two distinct workloads:
  1. Matched Request-Response Round-Trip (Ping-Pong):
     Parent and child processes exchange exact payloads over /dev/aipc in lockstep,
     recording high-resolution per-exchange round-trip latency (P50, P90, P95, P99, stddev)
     and throughput matching the user-space IPC evaluation protocol.
  2. Bulk Unidirectional Streaming:
     Producer writes continuous payload stream while consumer drains it,
     evaluating maximum raw kernel buffer streaming throughput (MB/s).

Error handling and safety:
  - Validates /dev/aipc presence and access permissions.
  - Returns clear BLOCKED status when device is absent without crashing.
  - Implements process cleanup timeouts to prevent deadlocks.
"""

import argparse
import csv
import math
import os
import signal
import statistics
import sys
import time


def check_device(device_path):
    if not os.path.exists(device_path):
        return False, f"Device node {device_path} does not exist. (Kernel module not loaded)"
    try:
        fd = os.open(device_path, os.O_RDWR | os.O_NONBLOCK)
        os.close(fd)
        return True, "Device accessible"
    except PermissionError:
        return False, f"Permission denied accessing {device_path}. (Root/group privileges required)"
    except Exception as e:
        return False, f"Error opening {device_path}: {e}"


def run_roundtrip_exchange(device_path, payload_size, count, warmup, trial):
    """
    Executes count request-response round-trips between parent (producer) and child (consumer)
    using /dev/aipc with ping-pong synchronization.
    """
    # Deterministic test pattern
    test_pattern = bytes((i * 31 + 7) & 0xFF for i in range(payload_size))

    # Pipe for child-ready synchronization before starting benchmark
    ready_r, ready_w = os.pipe()

    pid = os.fork()
    if pid == 0:
        # Child process: Consumer / Echo responder
        os.close(ready_r)
        try:
            fd = os.open(device_path, os.O_RDWR)
        except Exception as e:
            os.write(ready_w, b"ERR")
            os.close(ready_w)
            sys.exit(1)

        # Notify parent that child is ready and listening
        os.write(ready_w, b"OK")
        os.close(ready_w)

        total_exchanges = warmup + count
        try:
            for _ in range(total_exchanges):
                # Read request from /dev/aipc
                received = bytearray()
                while len(received) < payload_size:
                    chunk = os.read(fd, payload_size - len(received))
                    if not chunk:
                        raise EOFError("Unexpected EOF on /dev/aipc in child")
                    received.extend(chunk)

                # Echo response back to /dev/aipc
                written = 0
                while written < payload_size:
                    n = os.write(fd, received[written:])
                    if n <= 0:
                        raise IOError("Failed to write to /dev/aipc in child")
                    written += n
        finally:
            os.close(fd)
            os._exit(0)

    # Parent process: Producer / Measurement coordinator
    os.close(ready_w)
    status_buf = os.read(ready_r, 4)
    os.close(ready_r)
    if status_buf != b"OK":
        os.waitpid(pid, 0)
        raise RuntimeError("Child failed to initialize on /dev/aipc")

    fd = os.open(device_path, os.O_RDWR)
    samples_ns = []
    errors = 0
    total_start = 0
    total_end = 0

    try:
        # Warm-up phase (untimed)
        for _ in range(warmup):
            written = 0
            while written < payload_size:
                written += os.write(fd, test_pattern[written:])
            received = bytearray()
            while len(received) < payload_size:
                chunk = os.read(fd, payload_size - len(received))
                received.extend(chunk)

        # Timed measurement phase
        total_start = time.perf_counter_ns()
        for _ in range(count):
            req_start = time.perf_counter_ns()

            # Write request
            written = 0
            while written < payload_size:
                written += os.write(fd, test_pattern[written:])

            # Read response
            received = bytearray()
            while len(received) < payload_size:
                chunk = os.read(fd, payload_size - len(received))
                if not chunk:
                    raise EOFError("Unexpected EOF on /dev/aipc in parent")
                received.extend(chunk)

            req_end = time.perf_counter_ns()
            samples_ns.append(req_end - req_start)

            if received != test_pattern:
                errors += 1

        total_end = time.perf_counter_ns()

    finally:
        os.close(fd)
        os.waitpid(pid, 0)

    elapsed_ns = total_end - total_start
    return samples_ns, elapsed_ns, errors


def run_bulk_streaming(device_path, payload_size, count, trial):
    """
    Executes bulk unidirectional transfer: producer streams total_bytes, consumer drains it.
    """
    total_bytes = payload_size * count
    chunk = b"A" * payload_size

    consumer_code = f"""
import os, sys
fd = os.open('{device_path}', os.O_RDONLY)
drained = 0
while drained < {total_bytes}:
    data = os.read(fd, min(65536, {total_bytes} - drained))
    if not data: break
    drained += len(data)
os.close(fd)
"""
    # Run consumer in background
    import subprocess
    consumer = subprocess.Popen([sys.executable, "-c", consumer_code])
    time.sleep(0.05)  # Allow consumer to open and block

    start_ns = time.perf_counter_ns()
    fd = os.open(device_path, os.O_WRONLY)
    try:
        written_total = 0
        while written_total < total_bytes:
            to_write = min(payload_size, total_bytes - written_total)
            n = os.write(fd, chunk[:to_write])
            written_total += n
    finally:
        os.close(fd)

    consumer.wait(timeout=30)
    end_ns = time.perf_counter_ns()
    elapsed_ns = end_ns - start_ns

    elapsed_s = elapsed_ns / 1e9
    throughput_mb_s = (total_bytes / (1024.0 * 1024.0)) / elapsed_s if elapsed_s else 0.0
    throughput_msg_s = count / elapsed_s if elapsed_s else 0.0

    return elapsed_ns, throughput_msg_s, throughput_mb_s


def main():
    parser = argparse.ArgumentParser(description="Mini A-IPC Kernel Mailbox Benchmark")
    parser.add_argument("--device", default="/dev/aipc", help="Device path (default: /dev/aipc)")
    parser.add_argument("--mode", choices=["roundtrip", "bulk", "check"], default="roundtrip")
    parser.add_argument("--size", type=int, default=64, help="Payload size in bytes")
    parser.add_argument("--count", type=int, default=10000, help="Number of exchanges / messages")
    parser.add_argument("--warmup", type=int, default=500, help="Number of warm-up exchanges")
    parser.add_argument("--trial", type=int, default=1, help="Trial index")
    parser.add_argument("--csv", action="store_true", help="Output legacy CSV format")
    parser.add_argument("--csv-extended", action="store_true", help="Output extended research CSV format")
    args = parser.parse_args()

    # Pre-flight device check
    ready, msg = check_device(args.device)
    if args.mode == "check":
        if ready:
            print(f"READY: {msg}")
            sys.exit(0)
        else:
            print(f"BLOCKED: {msg}", file=sys.stderr)
            sys.exit(1)

    if not ready:
        print(f"BLOCKED: {msg}", file=sys.stderr)
        # Emit BLOCKED row if CSV was requested so automation captures failure reason cleanly
        if args.csv_extended:
            print(f"kernel,kernel-mailbox,{args.size},{args.trial},{args.count},0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0,1")
        elif args.csv:
            print(f"kernel-mailbox,{args.size},{args.trial},{args.count},0.0,0.0,0.0,0.0,0.0,0.0,0.0")
        sys.exit(77)

    if args.mode == "roundtrip":
        try:
            samples_ns, elapsed_ns, errors = run_roundtrip_exchange(
                args.device, args.size, args.count, args.warmup, args.trial
            )
        except Exception as e:
            print(f"ERROR: Round-trip benchmark failed: {e}", file=sys.stderr)
            sys.exit(1)

        samples_us = sorted(s / 1000.0 for s in samples_ns)
        n = len(samples_us)
        avg_rtt_us = (sum(samples_us) / n) if n else 0.0
        min_rtt_us = samples_us[0] if n else 0.0
        max_rtt_us = samples_us[-1] if n else 0.0
        p50_rtt_us = statistics.median(samples_us) if n else 0.0

        # Percentiles using nearest-rank formula
        def p_rank(pct):
            idx = int(math.ceil((pct / 100.0) * n)) - 1
            idx = max(0, min(n - 1, idx))
            return samples_us[idx]

        p90_rtt_us = p_rank(90.0) if n else 0.0
        p95_rtt_us = p_rank(95.0) if n else 0.0
        p99_rtt_us = p_rank(99.0) if n else 0.0
        p999_rtt_us = p_rank(99.9) if n else 0.0
        stddev_rtt_us = statistics.stdev(samples_us) if n > 1 else 0.0

        elapsed_s = elapsed_ns / 1e9
        throughput_msg_sec = (args.count / elapsed_s) if elapsed_s else 0.0
        throughput_mb_sec = ((args.count * args.size) / (1024.0 * 1024.0)) / elapsed_s if elapsed_s else 0.0

        if args.csv_extended:
            # Matches src/main.c --csv-extended format:
            # requested_mode,selected_transport,payload_bytes,trial,count,avg_rtt_us,p50_rtt_us,p90_rtt_us,p95_rtt_us,p99_rtt_us,p999_rtt_us,min_rtt_us,max_rtt_us,stddev_rtt_us,throughput_msg_sec,throughput_mb_sec,elapsed_ns,errors
            print(f"kernel,kernel-mailbox,{args.size},{args.trial},{args.count},{avg_rtt_us:.3f},{p50_rtt_us:.3f},{p90_rtt_us:.3f},{p95_rtt_us:.3f},{p99_rtt_us:.3f},{p999_rtt_us:.3f},{min_rtt_us:.3f},{max_rtt_us:.3f},{stddev_rtt_us:.3f},{throughput_msg_sec:.2f},{throughput_mb_sec:.3f},{elapsed_ns},{errors}")
        elif args.csv:
            print(f"kernel-mailbox,{args.size},{args.trial},{args.count},{avg_rtt_us:.3f},{p50_rtt_us:.3f},{p99_rtt_us:.3f},{p999_rtt_us:.3f},{min_rtt_us:.3f},{max_rtt_us:.3f},{throughput_msg_sec:.2f}")
        else:
            print(f"Mode: kernel-mailbox (round-trip)")
            print(f"Payload: {args.size} bytes | Exchanges: {args.count}")
            print(f"Elapsed: {elapsed_ns} ns")
            print(f"Average round-trip latency: {avg_rtt_us * 1000.0:.2f} ns")
            print(f"Throughput: {throughput_msg_sec:.2f} exchanges/s ({throughput_mb_sec:.2f} MB/s)")
            print(f"Validation errors: {errors}")
            print(f"P50 latency: {p50_rtt_us:.2f} us")
            print(f"P90 latency: {p90_rtt_us:.2f} us")
            print(f"P95 latency: {p95_rtt_us:.2f} us")
            print(f"P99 latency: {p99_rtt_us:.2f} us")
            print(f"Stddev latency: {stddev_rtt_us:.2f} us")

    elif args.mode == "bulk":
        elapsed_ns, tput_msg, tput_mb = run_bulk_streaming(args.device, args.size, args.count, args.trial)
        if args.csv_extended:
            avg_us = (elapsed_ns / args.count) / 1000.0 if args.count else 0.0
            print(f"kernel-bulk,kernel-mailbox,{args.size},{args.trial},{args.count},{avg_us:.3f},0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,{tput_msg:.2f},{tput_mb:.3f},{elapsed_ns},0")
        elif args.csv:
            avg_us = (elapsed_ns / args.count) / 1000.0 if args.count else 0.0
            print(f"kernel-bulk,{args.size},{args.trial},{args.count},{avg_us:.3f},0.0,0.0,0.0,0.0,0.0,{tput_msg:.2f}")
        else:
            print(f"Kernel bulk streaming: {args.count} chunks of {args.size} B")
            print(f"Elapsed: {elapsed_ns / 1e6:.3f} ms | Throughput: {tput_mb:.2f} MB/s ({tput_msg:.2f} msg/s)")


if __name__ == "__main__":
    main()

