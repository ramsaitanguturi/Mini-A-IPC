# Mini-A-IPC: Detailed Technical Specifications of Six IPC Implementations

## 1. Overview

This document provides a comprehensive technical audit and API specification for each of the six classical userspace IPC implementations provided in `src/`.

---

## 2. Implementation Audits

### 2.1 Anonymous Pipes (`src/ipc_pipe.c`)
- **Mechanism**: Unidirectional byte stream created via `pipe()`. Two distinct pipes (`request_pipe` and `response_pipe`) establish full-duplex communication between parent (producer) and child (consumer).
- **File Descriptor Management**:
  - Immediately following `fork()`, unused file descriptors are closed (`close(request_pipe[1])` and `close(response_pipe[0])` in child; `close(request_pipe[0])` and `close(response_pipe[1])` in parent).
  - Explicitly prevents file descriptor leaks and zombie descriptor retention.
- **Signal Handling**:
  - Installs `SIG_IGN` for `SIGPIPE` prior to `fork()` so that broken pipe conditions return `-1` with `errno = EPIPE` rather than abnormally terminating the process.
  - Signal state is restored to original mask upon benchmark completion.
- **Partial I/O Loops**:
  - Wrapped with helper functions `read_all()` and `write_all()` that loop until the complete payload size is transferred or an unrecoverable error occurs.
  - Transparently retries on `EINTR`.
- **Fault Detection**: Detects premature child exit via `waitpid(child, &status, 0)` and reports `EIO` if child exited with non-zero status.

### 2.2 Named Pipes / FIFO (`src/ipc_fifo.c`)
- **Mechanism**: Filesystem FIFO special files created in `/tmp` via `mkfifo()`.
- **Security & Permissions**:
  - Named pipes are created with mode `0600` (`S_IRUSR | S_IWUSR`), strictly restricting access to the owner process and preventing unauthorized local process tampering.
  - Uses unique filesystem paths derived from process ID: `/tmp/mini_aipc_req_<pid>.fifo` and `/tmp/mini_aipc_resp_<pid>.fifo`.
- **Deadlock Prevention on Open**:
  - In POSIX, opening a FIFO for `O_RDONLY` blocks until another process opens it for `O_WRONLY` (and vice versa).
  - To prevent mutual blocking deadlocks, parent and child open complementary ends in strict order:
    - Child opens `req_fifo` for `O_RDONLY`, then `resp_fifo` for `O_WRONLY`.
    - Parent opens `req_fifo` for `O_WRONLY`, then `resp_fifo` for `O_RDONLY`.
- **Cleanup**: Unlinks FIFO filesystem nodes both upon normal exit and in all error paths.

### 2.3 POSIX Shared Memory (`src/ipc_shm.c`)
- **Mechanism**: Memory-mapped RAM segment created via `shm_open()` and mapped into process address space using `mmap(MAP_SHARED)`.
- **Synchronization**:
  - Four POSIX unnamed semaphores (`sem_t`) initialized with `pshared = 1`: `request_empty`, `request_full`, `response_empty`, `response_full`.
  - Cache-line separation (`_Alignas(64)`) isolates producer and consumer synchronization state to eliminate false sharing.
- **Payload Capacity**:
  - Enforces `SHM_MAX_PAYLOAD` (1,024 bytes). Payloads exceeding this limit return `-1` with `errno = EMSGSIZE`.
- **Child Death Detection**:
  - Implements `sem_wait_monitor_child()` using `sem_timedwait()` with 100 ms timeout intervals and non-blocking `waitpid(..., WNOHANG)` checks to ensure parent never hangs if the child process crashes.
- **Cleanup**: Segment unmapped via `munmap()` and unlinked from `/dev/shm` via `shm_unlink()`.

### 2.4 System V Message Queues (`src/ipc_sysv_mq.c`)
- **Mechanism**: Kernel-managed message queues accessed via integer queue identifiers (`msqid`).
- **Creation & Permissions**:
  - Created using `msgget(IPC_PRIVATE, IPC_CREAT | IPC_EXCL | 0600)`.
  - `IPC_PRIVATE` guarantees allocation of a new, unique queue inaccessible to unprivileged external processes.
- **Message Types**:
  - Uses `mtype = 1L` for parent-to-child requests (`MSG_TYPE_REQ`).
  - Uses `mtype = 2L` for child-to-parent responses (`MSG_TYPE_RESP`).
  - Child selectively dequeues `MSG_TYPE_REQ` and parent selectively dequeues `MSG_TYPE_RESP`.
- **Child Death Detection**:
  - Installs a `SIGCHLD` handler *without* `SA_RESTART`, ensuring that any blocking `msgrcv()` call is immediately interrupted with `EINTR` upon child exit.
- **Cleanup**: Queue destroyed via `msgctl(msqid, IPC_RMID, NULL)` in both normal and error exit paths.

### 2.5 POSIX Message Queues (`src/ipc_posix_mq.c`)
- **Mechanism**: Priority-based structured messaging accessible via virtual filesystem `/dev/mqueue`.
- **Configuration & Attributes**:
  - Created via `mq_open()` with `O_CREAT | O_EXCL | O_RDWR` and permissions `0600`.
  - Sets `attr.mq_maxmsg = 10` (unprivileged Linux default) and `attr.mq_msgsize = payload_size`.
  - Enforces proper buffer sizing matching `attr.mq_msgsize` on `mq_receive()` to avoid `EMSGSIZE`.
- **Resource Management**:
  - Both request and response queues are unlinked immediately after creation or prior to closure using `mq_unlink()`.
  - Descriptors closed via `mq_close()`.

### 2.6 Unix Domain Sockets (`src/ipc_uds.c`)
- **Mechanism**: Local stream socket pair (`AF_UNIX`, `SOCK_STREAM`).
- **Connection Handshake**:
  - Server (child) binds to `/tmp/mini_aipc_uds_<pid>.sock` and enters `listen(1)` prior to client connection.
  - Client (parent) connects via `connect()`.
- **Framing & Partial I/O**:
  - Employs `send_all()` and `recv_all()` loops to guarantee full payload transfer across stream byte boundaries.
  - Detects peer disconnection via EOF (`recv() == 0`) or `EPIPE`.
- **Cleanup**: Closes socket descriptors and unlinks the socket inode from `/tmp`.

---

## 3. Comparative Summary Matrix

| Metric | Pipe | FIFO | POSIX SHM | System V MQ | POSIX MQ | Unix Domain Skt |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **API Paradigm** | File descriptors | Filesystem FIFO | Memory Mapping | IPC Key / IDs | POSIX Descriptors | BSD Socket API |
| **Transfer Type** | Byte Stream | Byte Stream | Structured Mailbox| Typed Messages | Priority Messages | Byte Stream |
| **Data Copying** | Double copy | Double copy | Zero copy (RAM) | Double copy | Double copy | Double copy |
| **Max Payload** | Unlimited (Chunked)| Unlimited (Chunked)| 1,024 Bytes | System `msgmax` | Configured `msgsize`| Unlimited (Chunked)|
| **Multiplexing** | `poll`, `select` | `poll`, `select` | Not native (sem) | Not native | `mq_notify`, `poll` | `poll`, `epoll` |
| **Multi-Process** | Related (fork) | Unrelated | Unrelated | Unrelated | Unrelated | Unrelated |
