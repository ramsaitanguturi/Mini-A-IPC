# Viva guide: core questions

## What does `fork()` do?
It creates a child process. Both processes continue from the return point; the child receives 0 and the parent receives the child's PID.

## Why are two pipes used?
A pipe is a byte stream with a read end and a write end. Two pipes provide request and response directions.

## Why do read/write loops matter?
A system call may transfer fewer bytes than requested or be interrupted. The loops continue until the requested length is transferred or an error/EOF occurs.

## What do `shm_open()` and `mmap()` do?
`shm_open()` opens or creates a named POSIX shared-memory object. `ftruncate()` sets its size. `mmap()` maps the object into the process address space with shared visibility.

## Why use semaphores?
Shared memory only provides shared bytes; it does not automatically coordinate access. Semaphores ensure the consumer sees a published request and the producer does not reuse a slot prematurely.

## What is latency?
Here it is average round-trip time per request/response exchange, not one-way latency.

## What is throughput?
Completed exchanges per second during the measured interval.

## Is this a full replication of the paper?
No. It reproduces a small part of the motivation and comparison, but not the paper's lock-free ring buffer, atomic memory ordering, adaptive spin/park controller, UNIX socket mode, or complete experimental matrix.
