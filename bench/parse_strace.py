#!/usr/bin/env python3
import sys

def parse_strace(filename, mechanism, payload_bytes, exchanges):
    calls = {}
    total_calls = 0

    with open(filename, "r") as f:
        for line in f:
            parts = line.strip().split()
            if not parts:
                continue
            # Header or separator lines
            if parts[0].startswith("%") or parts[0].startswith("-"):
                continue

            # Check if this line has 6 columns (has errors column) or 5 columns (no errors)
            # Format with errors: [%time, seconds, usecs/call, calls, errors, syscall_name]
            # Format without errors: [%time, seconds, usecs/call, calls, syscall_name]
            name = parts[-1]
            if len(parts) >= 6:
                cnt = int(parts[-3])
            elif len(parts) == 5:
                cnt = int(parts[-2])
            else:
                continue

            if name == "total":
                total_calls = cnt
            else:
                calls[name] = cnt

    # Categorize communication-path syscalls vs setup/cleanup
    comm_keys = {
        "pipe": ["read", "write"],
        "fifo": ["read", "write"],
        "sysv": ["msgsnd", "msgrcv"],
        "posix": ["mq_timedsend", "mq_send", "mq_timedreceive", "mq_receive"],
        "shm": ["futex"],
        "uds": ["sendto", "recvfrom", "send", "recv"],
    }.get(mechanism, [])

    comm_syscalls = sum(calls.get(k, 0) for k in comm_keys)
    setup_cleanup = max(0, total_calls - comm_syscalls)

    exchanges = int(exchanges)
    total_per_ex = total_calls / exchanges if exchanges else 0.0
    comm_per_ex = comm_syscalls / exchanges if exchanges else 0.0

    # Build detail summary string
    comm_details = "+".join(f"{k}({calls[k]})" for k in comm_keys if k in calls)
    if not comm_details:
        comm_details = "none"

    setup_interesting = ["socket", "bind", "listen", "connect", "accept", "mknodat",
                         "openat", "close", "unlink", "msgget", "msgctl", "mq_open",
                         "mq_unlink", "mmap", "ftruncate", "clone", "wait4", "pipe2"]
    setup_details = "+".join(f"{k}({calls[k]})" for k in setup_interesting if k in calls)

    detail_str = f"comm: {comm_details}={comm_syscalls}; setup: {setup_details}"

    return (f"{mechanism},{payload_bytes},{exchanges},{total_calls},"
            f"{total_per_ex:.2f},{comm_syscalls},{comm_per_ex:.2f},"
            f"{setup_cleanup},\"{detail_str}\"")

if __name__ == "__main__":
    if len(sys.argv) < 5:
        sys.exit(1)
    row = parse_strace(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
    print(row)
