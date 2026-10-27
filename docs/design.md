# Design

## Processes and transports

Each benchmark run creates one child process. The parent sends a request and receives the same bytes back. Keeping the process alive for all exchanges avoids charging process creation to every message.

### Pipe mode

Two anonymous pipes are used because a conventional pipe is unidirectional:
- request pipe: parent writes, child reads
- response pipe: child writes, parent reads

`read_all` and `write_all` handle partial transfers and interruptions.

### Shared-memory mode

A POSIX shared-memory object is created with `shm_open`, sized with `ftruncate`, and mapped with `mmap(MAP_SHARED)`. Four process-shared semaphores coordinate request and response slot ownership. The mailbox is limited to 1024-byte payloads.

### Adaptive mode

The selector chooses shared memory when `size <= 1024`; otherwise it chooses pipes. This is a simple payload-size rule. It does not implement EWMA telemetry or hysteresis.
