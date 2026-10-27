# Kernel-space Mini A-IPC implementation

## Scope and architecture

`kernel/aipc_module.c` is a real Linux loadable kernel module. It registers a character device and creates `/dev/aipc` through `alloc_chrdev_region()`, `cdev_add()`, and `device_create()`. The device is a shared, bounded byte-stream mailbox backed by a kernel-managed ring buffer. Writers enqueue bytes and readers dequeue them; it is not a message-framed protocol, so applications that need message boundaries must define framing above this interface.

The implementation supplies `open`, `read`, `write`, `poll`, and `release`. A mutex protects the ring's head, tail, and used-byte count. Reader and writer wait queues provide blocking producer-consumer behavior; `O_NONBLOCK` operations return `-EAGAIN` when they cannot make progress. User-copy faults, allocation failures, invalid capacity, and interrupted waits are handled with error returns. The default capacity is 64 KiB and can be changed at module load using `capacity=N`.

## Build and load (Linux/WSL with a matching kernel build tree)

```bash
make
make kernel-module
sudo insmod kernel/aipc_module.ko
lsmod | grep aipc_module
ls -l /dev/aipc
sudo dmesg | tail -n 30
```

If `/lib/modules/$(uname -r)/build` is missing, install headers/build tools matching the running Linux kernel. On WSL, build and load from the Linux environment, not Windows PowerShell; the running kernel must support external modules. Some managed or restricted kernels do not permit module loading.

Unload after closing all client processes:

```bash
sudo rmmod aipc_module
sudo dmesg | tail -n 30
```

Build the user client with `make aipc-client`. Examples:

```bash
./aipc-client roundtrip 'hello from kernel space'
# Terminal A: blocks until bytes are available
./aipc-client read 5
# Terminal B: writes five bytes into the shared mailbox
./aipc-client write hello
```

The device is shared across all opens. The round-trip test assumes no other process concurrently consumes or writes the mailbox. Device permissions are determined by the system's device-node policy; use appropriate privileges rather than making the device world-writable.

## Tests

```bash
make kernel-test
```

The device test exits with status 77 (skip) when `/dev/aipc` is absent. Run it only after loading the module. Also test manually with multiple independent producers and consumers, buffer exhaustion, nonblocking opens, client termination, and repeated load/unload cycles. Review `dmesg` for warnings, faults, or lockup reports after every stress run.

## Current limitations and fair comparison

This first kernel implementation is a byte-stream ring buffer, not a drop-in equivalent to the existing pipe and POSIX shared-memory request/response benchmarks. It currently has no per-message metadata, per-client queues, configurable adaptive policy inside the kernel, ioctl statistics, or dedicated kernel benchmark harness. The existing adaptive selector remains a user-space baseline. Do not claim that the kernel transport outperforms pipes/shared memory until a matched workload, equivalent payload semantics, repeated trials, CPU usage, mean latency, and P99 latency have been measured. Label any measurements as local results, not as results from the reference paper.

## Safety notes

Only load a module you have reviewed, in a disposable test VM/WSL environment. A kernel bug can crash the system. The ring buffer is bounded; the mutex protects shared state; waits release the mutex before sleeping. Do not unload while actively testing or while clients are open. This prototype is educational and not a production IPC driver.

## Follow-up validation and fixes

### Read-copy fault safety

`aipc_read()` now peeks the requested bytes into a temporary kernel buffer and calls `copy_to_user()` before advancing the ring-buffer head. The mutex remains held during this copy so a second reader cannot consume those same bytes before the first reader commits the update. If the user copy fails, the function returns `-EFAULT` and leaves the ring-buffer state unchanged. This prioritizes correctness; a slow/faulting user page can hold the mutex longer, so contention should be measured.

### Independent producer and consumer

`aipc-client read-exact N` blocks until exactly N bytes have been read, while `aipc-client write TEXT` is a separate producer process. The device is a global byte stream, not a message queue: run tests with a clean mailbox and do not run unrelated producers/consumers concurrently with correctness tests.

```bash
# Terminal A: independent consumer
./aipc-client read-exact 17 > /tmp/aipc-received
# Terminal B: independent producer (18 bytes)
./aipc-client write 'producer-consumer'
cmp /tmp/aipc-received <(printf 'producer-consumer')
```

The test script exercises an empty nonblocking read, independent producer/consumer exchange, filling the queue until `EAGAIN`, checking that a further write returns `EAGAIN`, draining all bytes, and checking empty-buffer behavior. Start `make kernel-test` with an empty mailbox.

### Stress and exploratory benchmark

```bash
sudo ITERATIONS=20 ./tests/kernel/test_load_unload.sh
python3 ./bench/benchmark_kernel_mailbox.py --trials 7 --messages 1000
```

The stress script requires root and a built module; close all clients first. The benchmark writes an exploratory CSV at `results/kernel_mailbox_throughput.csv`. It measures wall-clock throughput for one independent producer and consumer. It does **not** provide per-message mean/P99 latency, CPU utilization, or a matched pipes/shared-memory comparison. Do not use its results to claim that the kernel module is faster than the existing transports. The mailbox must be drained before each run; use an isolated test machine and inspect kernel logs afterward.

## Evidence checklist for submission

Record these from the actual target environment; do not fabricate or manually fill in successful results:

- `uname -a`, `uname -r`, distribution/version, CPU and RAM, and kernel header/build-tree path.
- Full `make kernel-module` output and the resulting module's `modinfo kernel/aipc_module.ko` output.
- `insmod`, `lsmod`, `/dev/aipc` metadata, `dmesg`, and `rmmod` output.
- `make test`, `make kernel-test`, and repeated load/unload test output, including skipped or failed tests.
- Raw benchmark CSVs, trial count, payload sizes, workload description, summary statistics, and any warnings.
- A clear note that this kernel mailbox is currently a separate byte-stream transport; adaptive selection remains in user space. Kernel-space adaptive selection and a matched kernel-vs-pipe-vs-shared-memory evaluation are future work.
