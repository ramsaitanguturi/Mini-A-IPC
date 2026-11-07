# FIFO (Named Pipe) IPC Explanation & Viva Guide

This document provides a comprehensive, beginner-friendly explanation of the **FIFO (Named Pipe)** Inter-Process Communication (IPC) mechanism implemented in **Mini A-IPC**, along with an architecture walkthrough and 10 OS viva questions with answers.

---

## 1. What is a FIFO?

A **FIFO** (First-In, First-Out), commonly known as a **Named Pipe**, is a unidirectional IPC channel provided by Unix/POSIX operating systems.

- Data written to the write end is read from the read end in the exact order it was written (**First-In, First-Out**).
- Unlike anonymous pipes, a FIFO exists as an entry in the filesystem (a special device node) and has a file path name (e.g., `/tmp/mini_aipc_req_1234.fifo`).
- Although it appears in the filesystem directory tree, **FIFO data is not written to the disk**. The data is buffered entirely in kernel memory.

---

## 2. Why is FIFO Needed?

Anonymous pipes created with `pipe()` have a major limitation:
- They do not have a name or filesystem presence.
- They can only be shared between processes that have an inherited relationship (e.g., parent and child created via `fork()`).

**FIFOs solve this problem:**
- Because a FIFO has a filename, any independent processes with appropriate file permissions can open it by name to communicate—even if they were started from different terminals or by different users.
- In our project, FIFOs also provide a clean, educational comparison against anonymous pipes and shared memory.

---

## 3. What `mkfifo()` Does

The `mkfifo()` system call creates a FIFO special file in the filesystem:

```c
int mkfifo(const char *pathname, mode_t mode);
```

- **Arguments:**
  - `pathname`: The file path where the FIFO node should appear (e.g., `/tmp/mini_aipc_req_1234.fifo`).
  - `mode`: Permission bits (e.g., `0666`), modified by the process's `umask`.
- **Under the Hood:**
  - `mkfifo()` creates an inode with file type `S_IFIFO`.
  - It creates a directory entry in the specified directory.
  - It does **not** allocate data blocks on the disk storage.
  - If the path already exists, `mkfifo()` fails with `EEXIST`.

---

## 4. What `open()` Does with FIFOs (Blocking & Synchronization)

Unlike standard regular files, calling `open()` on a FIFO has special synchronization behavior:

- **Opening for Reading (`O_RDONLY`):**
  The `open()` call **blocks** until another process opens the same FIFO for writing.
- **Opening for Writing (`O_WRONLY`):**
  The `open()` call **blocks** until another process opens the same FIFO for reading.

> **Key OS Concept:** This blocking behavior acts as an automatic synchronization barrier (rendezvous) between the sender and receiver. Neither process proceeds past `open()` until both ends are ready.

---

## 5. What `read()` and `write()` Do

- **`write()`:** Copies bytes from user-space memory into the kernel's FIFO buffer (typically 64 KiB on Linux). If the kernel buffer is full, `write()` blocks until the reader drains data. If all readers have closed their descriptors, `write()` triggers a `SIGPIPE` signal and returns `-1` with `errno = EPIPE`.
- **`read()`:** Copies bytes from the kernel FIFO buffer into user-space memory. If the buffer is empty, `read()` blocks until new data is written. When all writers close their descriptors, `read()` returns `0` (EOF).
- **Partial Transfers & `EINTR`:** Neither system call is guaranteed to transfer all requested bytes in a single invocation, and both can be interrupted by signals. Therefore, robust code must wrap them in loops (`write_all` and `read_all`).

---

## 6. Why Two FIFO Files Are Used

A FIFO is **strictly unidirectional** (half-duplex). Bytes flow only from the writer to the reader.

If parent and child attempted full-duplex communication using only **one FIFO**:
1. Parent writes a request into `my_fifo`.
2. Parent immediately tries to read the child's response from `my_fifo`.
3. **Race Condition:** The parent might immediately read its own request back before the child ever sees it!

To achieve reliable bidirectional request-response communication:
- **`req_fifo` (Request FIFO):** Parent writes requests; Child reads requests.
- **`resp_fifo` (Response FIFO):** Child writes responses; Parent reads responses.

```
+--------+       Request FIFO (Parent -> Child)       +-------+
|        | >>> [ Parent writes ] -> [ Child reads ] >>>|       |
| Parent |                                            | Child |
|        | <<< [ Parent reads ] <- [ Child writes ] <<<|       |
+--------+      Response FIFO (Child -> Parent)       +-------+
```

---

## 7. How Parent and Child Communicate (Step-by-Step)

1. **Path Generation & Cleanup:** Parent generates unique paths (`/tmp/mini_aipc_req_<PID>.fifo` and `/tmp/mini_aipc_resp_<PID>.fifo`) and calls `unlink()` to remove any stale files.
2. **FIFO Creation:** Parent calls `mkfifo()` for both paths.
3. **Signal Setup:** Parent sets `SIGPIPE` handler to `SIG_IGN` to prevent abrupt process termination if the peer exits.
4. **Forking:** Parent calls `fork()` to create the child process.
5. **Deadlock-Free Opening:**
   - **Child:** Opens `req_fifo` with `O_RDONLY`, then opens `resp_fifo` with `O_WRONLY`.
   - **Parent:** Opens `req_fifo` with `O_WRONLY`, then opens `resp_fifo` with `O_RDONLY`.
   - *Result:* Both processes rendezvous on `req_fifo` first, then on `resp_fifo` second. Neither blocks waiting for the other in reverse order.
6. **Data Transfer Loop:**
   - Parent writes `payload_size` bytes to `req_fifo`.
   - Child reads `payload_size` bytes from `req_fifo`.
   - Child echoes the bytes back into `resp_fifo`.
   - Parent reads the response from `resp_fifo` and verifies data integrity.
7. **Termination & Cleanup:**
   - Both processes close their respective file descriptors.
   - Child calls `_exit(0)`.
   - Parent calls `waitpid()` to reap the child.
   - Parent calls `unlink()` on both FIFO paths to remove them from `/tmp`.

---

## 8. FIFO vs. Anonymous Pipes

| Feature | Anonymous Pipe (`pipe`) | Named Pipe (`mkfifo`) |
| :--- | :--- | :--- |
| **Filesystem Presence** | None (invisible, kernel-only) | Yes (visible special file in directory) |
| **Creation System Call** | `pipe(int fd[2])` | `mkfifo(const char *path, mode_t mode)` |
| **File Descriptors** | Opened immediately upon creation | Opened explicitly using `open()` |
| **Process Relationship** | Related processes only (parent/child) | Any processes with filesystem access |
| **Lifetime** | Ceases when all fds are closed | Inode persists until `unlink()` is called |
| **Data Storage** | Kernel memory buffer | Kernel memory buffer (no disk I/O) |

---

## 9. Advantages and Disadvantages

### Advantages
- **Simplicity:** Uses standard file descriptor semantics (`open`, `read`, `write`, `close`).
- **Universality:** Communicates between related or completely unrelated processes.
- **Inspectable:** Can be tested and manipulated from the shell using standard Unix utilities (`cat > /tmp/test.fifo`, `tail -f /tmp/test.fifo`).
- **Synchronization:** `open()` blocks automatically until both peers connect.

### Disadvantages
- **Filesystem Cleanup:** Requires explicit `unlink()`; crashed processes can leave orphaned FIFO nodes in `/tmp`.
- **Context Switching Overhead:** Slower than shared memory because every message requires system calls and kernel-space copying.
- **Deadlock Potential:** If processes open two FIFOs in opposite or circular order, both processes will hang indefinitely.

---

## 10. Code Walkthrough: `src/ipc_fifo.c`

Here is an explanation of every function in [`src/ipc_fifo.c`](../src/ipc_fifo.c):

### 1. `write_all(int fd, const void *buffer, size_t length)`
- Loops over `write()` until all `length` bytes are transmitted.
- Handles partial writes by incrementing the buffer pointer and reducing remaining count.
- Handles `EINTR` (interrupted system calls) by retrying without failing.
- Returns `0` on complete success, or `-1` on error or EOF.

### 2. `read_all(int fd, void *buffer, size_t length)`
- Loops over `read()` until exactly `length` bytes are received.
- Handles partial reads and `EINTR`.
- Returns `0` on complete success, or `-1` on unexpected EOF or error.

### 3. `ipc_fifo_run(size_t payload_size, size_t count, uint64_t *elapsed_ns, size_t *errors)`
- Main orchestration function exported for `mini-aipc` and `bin/ipc_fifo`.
- Validates parameters (`payload_size`, `count`, `elapsed_ns`, `errors`).
- Allocates memory buffers and fills `send_buffer` with a deterministic test pattern.
- Formulates unique FIFO paths using `getpid()`.
- Calls `mkfifo()` to create `req_fifo` and `resp_fifo`.
- Ignores `SIGPIPE` to catch peer termination cleanly via `EPIPE`.
- Calls `fork()`:
  - **Child:** Opens `req_fifo` for reading, `resp_fifo` for writing. Reads requests, echoes them back to `resp_fifo`, frees buffer, closes descriptors, and exits.
  - **Parent:** Opens `req_fifo` for writing, `resp_fifo` for reading. Writes request, reads response, measures time with `monotonic_ns()`, and verifies payload with `memcmp()`.
- Closes file descriptors, calls `waitpid()` to reap the child, and calls `unlink()` to remove the FIFO files.
- In case of failure at any stage, jumps to `fail:` label to clean up descriptors, kill/reap child, remove FIFO files, and restore signal handlers.

### 4. `monotonic_ns(void)` (in `#ifdef IPC_FIFO_STANDALONE`)
- Queries `clock_gettime(CLOCK_MONOTONIC, &ts)` and returns total elapsed time in nanoseconds.
- Used when building `bin/ipc_fifo` as an independent executable.

### 5. `main(int argc, char **argv)` (in `#ifdef IPC_FIFO_STANDALONE`)
- Standalone CLI entry point for `bin/ipc_fifo`.
- When run without arguments: executes a 1-exchange demonstration (64 bytes), verifies integrity, and prints output.
- When run with `--size BYTES --count N`: runs benchmark exchanges with the requested parameters.
- Rejects invalid arguments with exit code 2.

---

## 11. Communication Architecture Diagram

```
+--------------------------------------------------------------------------+
|                               Parent Process                             |
|                                                                          |
|  1. mkfifo(/tmp/mini_aipc_req_<pid>.fifo)                                |
|  2. mkfifo(/tmp/mini_aipc_resp_<pid>.fifo)                               |
|  3. fork() -------------------------------------+                        |
|  4. open(req_fifo, O_WRONLY)                    |                        |
|  5. open(resp_fifo, O_RDONLY)                   |                        |
+-------------------------------------------------|------------------------+
              |                        |          |
              | write(payload)         |          |
              v                        |          |
+--------------------------------+     |          |
| /tmp/mini_aipc_req_<pid>.fifo  |     |          |
| (Kernel-buffered named pipe)   |     |          |
+--------------------------------+     |          |
              |                        |          |
              | read(payload)          |          |
              v                        |          v
+--------------------------------------------------------------------------+
|                               Child Process                              |
|                                                                          |
|  1. open(req_fifo, O_RDONLY)                                             |
|  2. open(resp_fifo, O_WRONLY)                                            |
|  3. read_all(req_fifo, buf, size)                                        |
|  4. write_all(resp_fifo, buf, size) (echo response)                      |
|  5. close() & _exit(0)                                                   |
+--------------------------------------------------------------------------+
                                       |
                                       | write(response)
                                       v
                     +---------------------------------+
                     | /tmp/mini_aipc_resp_<pid>.fifo  |
                     | (Kernel-buffered named pipe)    |
                     +---------------------------------+
                                       |
                                       | read(response)
                                       v
+--------------------------------------------------------------------------+
|                               Parent Process                             |
|                                                                          |
|  6. read_all(resp_fifo, buf, size)                                       |
|  7. memcmp(send_buf, recv_buf) == 0 (Validate Integrity)                 |
|  8. close(req_fd), close(resp_fd)                                        |
|  9. waitpid(child)                                                       |
| 10. unlink(req_fifo), unlink(resp_fifo)                                  |
+--------------------------------------------------------------------------+
```

---

## 12. 10 OS Viva Questions & Answers

### Q1: What is a Named Pipe (FIFO) in Linux?
**Answer:** A Named Pipe (FIFO) is a unidirectional IPC channel that has a directory entry in the filesystem. Processes open it like a regular file using standard paths, but data is buffered strictly in kernel memory according to FIFO (First-In, First-Out) semantics without writing to disk.

### Q2: How does a FIFO differ from an Anonymous Pipe?
**Answer:** An anonymous pipe is created in memory via `pipe()` and has no filesystem name, so it can only be used by related processes (like parent and child after `fork()`). A FIFO is created via `mkfifo()`, has a filesystem name, and allows any unrelated processes with appropriate permissions to communicate.

### Q3: Does `mkfifo()` allocate disk blocks for storing message data?
**Answer:** No. `mkfifo()` creates an inode of type `S_IFIFO` and a directory entry, but allocates zero data blocks on disk. All data transferred through the FIFO is buffered in kernel memory.

### Q4: What is the default blocking behavior of `open()` on a FIFO?
**Answer:** Opening a FIFO for reading (`O_RDONLY`) blocks until another process opens it for writing. Opening a FIFO for writing (`O_WRONLY`) blocks until another process opens it for reading. This behavior automatically synchronizes both processes at connection time.

### Q5: How can a deadlock happen when using two FIFOs, and how did you prevent it?
**Answer:** A deadlock occurs if both processes try to open opposite write ends first (e.g., Parent opens FIFO 1 for writing while Child opens FIFO 2 for writing; both block forever waiting for readers). We prevent this by enforcing a strict matching opening order: Parent opens `req_fifo` (WR) then `resp_fifo` (RD), while Child opens `req_fifo` (RD) then `resp_fifo` (WR). Both rendezvous on `req_fifo` first, then `resp_fifo`.

### Q6: Why do we need two separate FIFO files for request-response communication?
**Answer:** A FIFO is unidirectional. If both parent and child read and write to the same FIFO, a race condition occurs where the parent might read its own request back before the child reads it. Using two FIFOs (`req_fifo` and `resp_fifo`) isolates request and response traffic.

### Q7: Why do we use `read_all` and `write_all` loops instead of single `read()` and `write()` calls?
**Answer:** System calls can transfer fewer bytes than requested (partial transfers) due to buffer constraints or can be interrupted by signals (`EINTR`). The loop guarantees that all requested bytes are fully sent or received before proceeding.

### Q8: What is `SIGPIPE` and why did you ignore it?
**Answer:** `SIGPIPE` is sent to a process that attempts to write to a pipe or FIFO whose read end is closed. By default, `SIGPIPE` terminates the process. We set `SIGPIPE` to `SIG_IGN` using `sigaction()` so that `write()` returns `-1` with `errno = EPIPE`, allowing the program to handle errors gracefully rather than crashing.

### Q9: What does `unlink()` do and what happens if you fail to call it?
**Answer:** `unlink()` removes the FIFO's directory entry from the filesystem. If you do not call `unlink()`, the FIFO special file remains on disk (e.g. in `/tmp`), causing filesystem clutter and potential `EEXIST` errors on subsequent runs.

### Q10: How does FIFO performance compare to Shared Memory?
**Answer:** FIFO communication requires data to be copied twice (user space -> kernel buffer -> user space) and involves context switches and system call overhead for every transfer. POSIX Shared Memory maps common memory into both processes' address spaces, allowing zero-copy data access, which makes shared memory significantly faster for small payloads or high exchange frequencies.

