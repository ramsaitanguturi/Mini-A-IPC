#!/usr/bin/env python3
"""Exploratory independent-process throughput test for /dev/aipc.

This is not a matched pipe/shared-memory comparison and does not report latency.
It records wall-clock transfer time for one producer and one consumer.
"""
import argparse
import csv
import os
import subprocess
import sys
import time

PRODUCER = r'''import os, sys
path, total, chunk_size = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
fd = os.open(path, os.O_WRONLY)
chunk = b'A' * chunk_size
done = 0
while done < total:
    part = chunk[:min(len(chunk), total-done)]
    off = 0
    while off < len(part):
        n = os.write(fd, part[off:])
        if n <= 0: raise RuntimeError('write made no progress')
        off += n
    done += len(part)
os.close(fd)
'''
CONSUMER = r'''import os, sys
path, total = sys.argv[1], int(sys.argv[2])
fd = os.open(path, os.O_RDONLY)
done = 0
while done < total:
    data = os.read(fd, min(65536, total-done))
    if not data: raise RuntimeError('unexpected end of stream')
    done += len(data)
os.close(fd)
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--device', default='/dev/aipc')
    ap.add_argument('--trials', type=int, default=7)
    ap.add_argument('--messages', type=int, default=1000)
    ap.add_argument('--payloads', default='64,256,1024,4096,16384')
    ap.add_argument('--output', default='results/kernel_mailbox_throughput.csv')
    args = ap.parse_args()
    if not os.path.exists(args.device):
        sys.exit(f'ERROR: device {args.device} not found; load the module first')
    if args.trials < 1 or args.messages < 1:
        ap.error('--trials and --messages must be positive')
    payloads = [int(x) for x in args.payloads.split(',')]
    if any(x < 1 for x in payloads):
        ap.error('payload sizes must be positive')
    os.makedirs(os.path.dirname(args.output) or '.', exist_ok=True)
    with open(args.output, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['trial', 'transport', 'payload_bytes', 'messages', 'total_bytes', 'elapsed_ms', 'throughput_mib_s', 'environment_note'])
        for payload in payloads:
            total = payload * args.messages
            for trial in range(1, args.trials + 1):
                consumer = subprocess.Popen([sys.executable, '-c', CONSUMER, args.device, str(total)])
                time.sleep(0.02)  # allow consumer to open and block on an empty mailbox
                start = time.perf_counter_ns()
                producer = subprocess.run([sys.executable, '-c', PRODUCER, args.device, str(total), str(payload)], check=False)
                producer_rc = producer.returncode
                consumer_rc = consumer.wait()
                elapsed_ns = time.perf_counter_ns() - start
                if producer_rc or consumer_rc:
                    raise SystemExit(f'FAIL: payload={payload}, trial={trial}, producer={producer_rc}, consumer={consumer_rc}')
                elapsed_s = elapsed_ns / 1e9
                mib_s = (total / (1024 * 1024)) / elapsed_s if elapsed_s else 0.0
                writer.writerow([trial, 'kernel-mailbox', payload, args.messages, total, f'{elapsed_ns/1e6:.6f}', f'{mib_s:.6f}', 'exploratory; not matched to pipe/shm semantics'])
                f.flush()
                print(f'payload={payload} trial={trial}/{args.trials} elapsed_ms={elapsed_ns/1e6:.3f} throughput_MiB_s={mib_s:.3f}')
    print(f'Wrote {args.output}')

if __name__ == '__main__':
    main()
