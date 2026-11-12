#!/usr/bin/env python3
"""
Mini A-IPC System-Call Profile Parser

Distinguishes:
  1. Communication-path syscalls (IPC data transfer / lockstep synchronization)
  2. Setup and cleanup syscalls (channel initialization, process creation, resource unlinking)
  3. Other / unclassified syscalls (unrelated program output like write(stdout), dynamic loader reads, runtime)

Supports both:
  - Detailed trace logs (strace -f -o) -> exact classification isolating fd 1/2 program output
  - Summary logs (strace -c) -> explicit "estimate" labeling when read/write cannot be separated

Classification Architecture and Methodology:
  - File Descriptor Inspection:
    Extracts the numerical file descriptor from read/write syscall arguments.
    Standard output (fd 1) and standard error (fd 2) are isolated as program output ('other').
  - Dynamic Loader Segregation:
    Reads matching ELF headers or library/config paths ('/usr/lib', '/etc/') are classified
    as dynamic linker startup overhead ('other'), preventing them from inflating IPC counts.
  - IPC Communication Identification:
    For pipe and fifo, genuine IPC data exchanges occur across dynamically allocated descriptors
    (fd >= 3), executing strictly 2 reads and 2 writes per request-response exchange (4.00 calls/exchange).
    For Unix domain sockets, communication occurs via sendto/recvfrom or socket fd streams.
    For shared memory, user-space memcpy transfers data without system calls; only futex transitions
    are recorded as communication synchronization.

Limitations of this Classification Model:
  1. Absence of Full Stateful Inode/FD Table:
     The parser does not maintain an exhaustive kernel-like descriptor table tracking pipe2,
     openat, and socket return values across fork() and dup(). If an auxiliary file is opened
     during runtime on fd >= 3 and read without an ELF or /etc/ signature, it could theoretically
     be attributed to IPC stream communication.
  2. Argument String Truncation:
     Detailed strace logs with truncated argument buffers (e.g. -s default of 32 bytes) might cut off
     library path signatures if not matched early in the buffer string.
  3. Summary Mode Aggregation Loss:
     When strace is run in summary mode (-c), kernel-level aggregation merges all read and write calls
     regardless of descriptor. In this mode, descriptor disambiguation is mathematically impossible;
     such results are explicitly classified as 'estimate' to maintain scientific rigor.
  4. Asynchronous and Interrupted Calls:
     Unfinished system calls (<unfinished ...> and <... resumed>) are reconstructed linearly per PID.
     High-concurrency drops or signal interrupts could introduce minor attribution variance.
"""

import sys
import re

SETUP_SYSCALLS = {
    "pipe2", "pipe", "mknodat", "mknod", "openat", "open", "close", "unlink",
    "unlinkat", "msgget", "msgctl", "mq_open", "mq_unlink", "mmap", "munmap",
    "ftruncate", "clone", "clone3", "wait4", "waitpid", "socket", "bind",
    "listen", "accept", "accept4", "connect", "shm_open", "shm_unlink"
}

COMM_KEYS_SUMMARY = {
    "pipe": ["read", "write"],
    "fifo": ["read", "write"],
    "sysv": ["msgsnd", "msgrcv"],
    "posix": ["mq_timedsend", "mq_send", "mq_timedreceive", "mq_receive"],
    "shm": ["futex"],
    "uds": ["sendto", "recvfrom", "send", "recv"],
}

def is_summary_log(lines):
    for line in lines[:20]:
        if "% time" in line or "usecs/call" in line:
            return True
        if line.strip().startswith("------"):
            return True
    return False

def parse_summary_log(lines, mechanism, payload_bytes, exchanges):
    calls = {}
    total_calls = 0

    for line in lines:
        parts = line.strip().split()
        if not parts or parts[0].startswith("%") or parts[0].startswith("-"):
            continue
        try:
            name = parts[-1]
            if len(parts) >= 6:
                cnt = int(parts[-3])
            elif len(parts) == 5:
                cnt = int(parts[-2])
            else:
                continue
        except (ValueError, IndexError):
            continue

        if name == "total":
            total_calls = cnt
        else:
            calls[name] = cnt

    if total_calls == 0 and calls:
        total_calls = sum(calls.values())

    comm_keys = COMM_KEYS_SUMMARY.get(mechanism, [])
    comm_syscalls = sum(calls.get(k, 0) for k in comm_keys)

    # Setup and cleanup calls
    setup_syscalls = sum(calls.get(k, 0) for k in SETUP_SYSCALLS)

    # Other calls: runtime, unclassified, and program output
    other_syscalls = max(0, total_calls - comm_syscalls - setup_syscalls)

    # In summary mode, read/write includes program output and loader reads for pipe/fifo
    classification = "estimate"

    exchanges_int = int(exchanges) if exchanges else 0
    total_per_ex = total_calls / exchanges_int if exchanges_int else 0.0
    comm_per_ex = comm_syscalls / exchanges_int if exchanges_int else 0.0

    comm_details = "+".join(f"{k}({calls[k]})" for k in comm_keys if k in calls) or "none"
    setup_details = "+".join(f"{k}({calls[k]})" for k in sorted(SETUP_SYSCALLS) if k in calls) or "none"
    other_details = f"unclassified({other_syscalls})"

    detail_str = f"comm: {comm_details}={comm_syscalls}; setup: {setup_details}={setup_syscalls}; other: {other_details}"

    return (f"{mechanism},{payload_bytes},{exchanges},{total_calls},"
            f"{total_per_ex:.2f},{comm_syscalls},{comm_per_ex:.2f},"
            f"{setup_syscalls},{other_syscalls},{classification},\"{detail_str}\"")

def parse_detailed_log(lines, mechanism, payload_bytes, exchanges):
    completed = []
    in_flight = {}

    for line in lines:
        line = line.strip()
        if not line or line.startswith("---") or line.startswith("+++"):
            continue

        # Check for resumed syscall line: 'PID <... SYSCALL resumed> ARGS) = RES'
        m_res = re.match(r"^(\d+)\s+<\.\.\.\s+(\w+)\s+resumed>(.*)", line)
        if m_res:
            pid, sc, rest = m_res.group(1), m_res.group(2), m_res.group(3)
            prefix = in_flight.pop((pid, sc), "")
            completed.append((pid, sc, f"{prefix}{rest}"))
            continue

        # Check for syscall initiation: 'PID SYSCALL(ARGS'
        m_call = re.match(r"^(\d+)\s+(\w+)\((.*)", line)
        if m_call:
            pid, sc, rest = m_call.group(1), m_call.group(2), m_call.group(3)
            if rest.endswith("<unfinished ...>"):
                in_flight[(pid, sc)] = rest[:-len("<unfinished ...>")]
            else:
                completed.append((pid, sc, rest))

    # Any lingering unfinished calls
    for (pid, sc), rest in in_flight.items():
        completed.append((pid, sc, rest))

    comm_calls = 0
    setup_calls = 0
    other_calls = 0
    comm_counts = {}
    setup_counts = {}
    other_counts = {}

    for pid, sc, args in completed:
        is_comm = False
        is_other = False

        if sc in ("read", "write"):
            # Extract file descriptor
            m_fd = re.match(r"^(\d+)", args)
            fd = int(m_fd.group(1)) if m_fd else -1

            # Standard output or standard error is unrelated program output
            if fd in (1, 2):
                is_other = True
                lbl = "write(stdout/err)" if sc == "write" else "read(stdin)"
                other_counts[lbl] = other_counts.get(lbl, 0) + 1
            # Dynamic loader reading shared libraries or configuration
            elif sc == "read" and ("ELF" in args or "/usr/lib" in args or "/etc/" in args):
                is_other = True
                other_counts["read(loader)"] = other_counts.get("read(loader)", 0) + 1
            # Stream pipe / FIFO data exchange
            elif mechanism in ("pipe", "fifo"):
                is_comm = True
            # Socket stream read / write
            elif mechanism == "uds" and fd > 2:
                is_comm = True
            else:
                is_other = True
                other_counts[sc] = other_counts.get(sc, 0) + 1

        elif mechanism == "sysv" and sc in ("msgsnd", "msgrcv"):
            is_comm = True
        elif mechanism == "posix" and sc in ("mq_timedsend", "mq_send", "mq_timedreceive", "mq_receive"):
            is_comm = True
        elif mechanism == "shm" and sc == "futex":
            is_comm = True
        elif mechanism == "uds" and sc in ("sendto", "recvfrom", "send", "recv"):
            is_comm = True

        if is_comm:
            comm_calls += 1
            comm_counts[sc] = comm_counts.get(sc, 0) + 1
        elif is_other:
            other_calls += 1
        elif sc in SETUP_SYSCALLS:
            setup_calls += 1
            setup_counts[sc] = setup_counts.get(sc, 0) + 1
        else:
            other_calls += 1
            other_counts[sc] = other_counts.get(sc, 0) + 1

    total_calls = len(completed)
    classification = "exact"

    exchanges_int = int(exchanges) if exchanges else 0
    total_per_ex = total_calls / exchanges_int if exchanges_int else 0.0
    comm_per_ex = comm_calls / exchanges_int if exchanges_int else 0.0

    comm_details = "+".join(f"{k}({v})" for k, v in sorted(comm_counts.items())) or "none"
    setup_details = "+".join(f"{k}({v})" for k, v in sorted(setup_counts.items())) or "none"
    other_details = "+".join(f"{k}({v})" for k, v in sorted(other_counts.items())) or "none"

    detail_str = f"comm: {comm_details}={comm_calls}; setup: {setup_details}={setup_calls}; other: {other_details}={other_calls}"

    return (f"{mechanism},{payload_bytes},{exchanges},{total_calls},"
            f"{total_per_ex:.2f},{comm_calls},{comm_per_ex:.2f},"
            f"{setup_calls},{other_calls},{classification},\"{detail_str}\"")

def parse_strace(filename, mechanism, payload_bytes, exchanges):
    with open(filename, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    if is_summary_log(lines):
        return parse_summary_log(lines, mechanism, payload_bytes, exchanges)
    else:
        return parse_detailed_log(lines, mechanism, payload_bytes, exchanges)

if __name__ == "__main__":
    if len(sys.argv) < 5:
        sys.exit(1)
    row = parse_strace(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
    print(row)
