# Experimental methodology

## Research question

How do a pipe and a semaphore-coordinated shared-memory mailbox compare for request/response messages, and what happens when a payload-size selector routes small messages to shared memory and larger messages to pipes?

## Workloads

Run 64-byte and 1024-byte tests in all applicable modes, and 16384-byte tests using pipes and adaptive mode. Shared memory rejects payloads above 1024 bytes.

## Metrics

- Elapsed time for all exchanges
- Average round-trip latency = elapsed nanoseconds / number of exchanges
- Throughput = exchanges / elapsed seconds
- Validation errors

## Procedure

1. Build with `make clean && make`.
2. Run each configuration at least five times.
3. Record each actual output with the trial number and environment details.
4. Compare the same payload size and exchange count.
5. Do not invent measurements or claim the simple implementation reproduces the paper's absolute results.

## Limitations

This program uses a semaphore mailbox rather than the paper's lock-free SPSC ring buffer. It omits UNIX domain sockets and the paper's online workload observer. WSL scheduling and virtualization can affect timing.
