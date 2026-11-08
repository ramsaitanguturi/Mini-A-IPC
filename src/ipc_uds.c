#include "ipc.h"

#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

/*
 * Unix Domain Socket (UDS) IPC Implementation
 *
 * Unix domain sockets provide full-duplex, stream- or datagram-oriented IPC
 * within the local operating system kernel using the standard BSD socket API.
 * For this implementation, SOCK_STREAM (connection-oriented, reliable byte stream)
 * is used, matching the paper's HPC evaluation of classical IPC mechanisms.
 *
 * System calls used:
 * - socket(AF_UNIX, SOCK_STREAM, 0): Creates a local Unix domain stream socket endpoint.
 * - bind(): Assigns a filesystem pathname (/tmp/mini_aipc_uds_<pid>.sock) to the server socket.
 * - listen(): Marks the socket as passive, ready to accept incoming client connections.
 * - accept(): Extracts the first connection request on the listening queue and creates a connected socket.
 * - connect(): Establishes an active connection from client (parent) to server (child).
 * - send() / recv(): Transfers request and response payload bytes over the full-duplex connection.
 * - close(): Tears down socket endpoints.
 * - unlink(): Removes the socket node from the filesystem.
 *
 * Synchronization flow:
 * - Parent creates listening socket, binds to temporary path, and starts listen(1).
 * - fork() creates child.
 * - Child acts as server: calls accept() to obtain connected descriptor conn_fd.
 * - Parent acts as client: creates client_fd and calls connect() to the server path.
 * - Parent sends requests; child echoes back responses.
 * - Any unexpected child exit causes parent recv() to return 0 (EOF) or send() to fail with EPIPE.
 */

/* Helper function to reliably send all bytes across a stream socket */
static int send_all(int fd, const void *buffer, size_t length)
{
    const unsigned char *p = buffer;
    size_t done = 0;

    while (done < length) {
        ssize_t n = send(fd, p + done, length - done, 0);
        if (n < 0) {
            if (errno == EINTR) continue;
            return -1;
        }
        if (n == 0) return -1;
        done += (size_t)n;
    }
    return 0;
}

/* Helper function to reliably receive all bytes across a stream socket */
static int recv_all(int fd, void *buffer, size_t length)
{
    unsigned char *p = buffer;
    size_t done = 0;

    while (done < length) {
        ssize_t n = recv(fd, p + done, length - done, 0);
        if (n < 0) {
            if (errno == EINTR) continue;
            return -1;
        }
        if (n == 0) return -1; /* Unexpected EOF: peer closed connection */
        done += (size_t)n;
    }
    return 0;
}

int ipc_uds_run_opts(size_t payload_size, size_t count, const ipc_bench_opts_t *opts,
                     uint64_t *elapsed_ns, size_t *errors)
{
    char sock_path[108] = {0};
    int listen_fd = -1;
    int client_fd = -1;
    pid_t child = -1;
    unsigned char *send_buffer = NULL;
    unsigned char *receive_buffer = NULL;
    size_t i;
    int status = 0;
    uint64_t start, end;
    struct sockaddr_un addr;
    struct sigaction ignore_pipe, old_pipe;
    int sigpipe_changed = 0;

    if (!payload_size || !count || !elapsed_ns || !errors) {
        errno = EINVAL;
        return -1;
    }

    send_buffer = malloc(payload_size);
    receive_buffer = malloc(payload_size);
    if (!send_buffer || !receive_buffer) goto fail;

    for (i = 0; i < payload_size; ++i)
        send_buffer[i] = (unsigned char)((i * 31U + 7U) & 0xffU);
    memset(receive_buffer, 0, payload_size);

    /* Form unique Unix domain socket path in /tmp based on PID */
    snprintf(sock_path, sizeof(sock_path), "/tmp/mini_aipc_uds_%d.sock", (int)getpid());
    unlink(sock_path);

    /*
     * Create the listening socket endpoint for the server.
     * Binding and listening prior to fork() guarantees that the socket file
     * is already active and accepting connections when the client connects.
     */
    listen_fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (listen_fd < 0) goto fail;

    memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;
    snprintf(addr.sun_path, sizeof(addr.sun_path), "%s", sock_path);

    if (bind(listen_fd, (struct sockaddr *)&addr, sizeof(addr)) < 0)
        goto fail;

    if (listen(listen_fd, 1) < 0)
        goto fail;

    /* Ignore SIGPIPE so write/send errors return EPIPE instead of killing the process */
    memset(&ignore_pipe, 0, sizeof(ignore_pipe));
    ignore_pipe.sa_handler = SIG_IGN;
    sigemptyset(&ignore_pipe.sa_mask);
    if (sigaction(SIGPIPE, &ignore_pipe, &old_pipe) < 0) goto fail;
    sigpipe_changed = 1;

    child = fork();
    if (child < 0) goto fail;

    if (child == 0) {
        /* Child process acts as Server */
        int conn_fd = -1;
        unsigned char *child_buffer = NULL;
        const char *fault = getenv("AIPC_TEST_CHILD_EXIT");
        size_t total_exchanges = (opts ? opts->warmup : 0) + count;
        size_t j;

        if (opts && opts->cpu_consumer >= 0)
            set_cpu_affinity(opts->cpu_consumer);

        /* Accept incoming connection from parent client */
        conn_fd = accept(listen_fd, NULL, NULL);
        close(listen_fd); /* Close listening socket in child */
        if (conn_fd < 0) _exit(1);

        /* Fault injection test hook */
        if (fault != NULL && strcmp(fault, "uds") == 0) {
            close(conn_fd);
            _exit(77);
        }

        child_buffer = malloc(payload_size);
        if (!child_buffer) {
            close(conn_fd);
            _exit(2);
        }

        /* Echo requests back to parent */
        for (j = 0; j < total_exchanges; ++j) {
            if (recv_all(conn_fd, child_buffer, payload_size) < 0 ||
                send_all(conn_fd, child_buffer, payload_size) < 0) {
                free(child_buffer);
                close(conn_fd);
                _exit(3);
            }
        }

        free(child_buffer);
        close(conn_fd);
        _exit(0);
    }

    /* Parent process acts as Client */
    if (opts && opts->cpu_producer >= 0)
        set_cpu_affinity(opts->cpu_producer);

    /* Parent does not need listening socket; child handles incoming accept() */
    close(listen_fd);
    listen_fd = -1;

    client_fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (client_fd < 0) goto fail;

    if (connect(client_fd, (struct sockaddr *)&addr, sizeof(addr)) < 0)
        goto fail;

    *errors = 0;

    /* Untimed warm-up exchanges */
    if (opts && opts->warmup > 0) {
        for (i = 0; i < opts->warmup; ++i) {
            if (send_all(client_fd, send_buffer, payload_size) < 0 ||
                recv_all(client_fd, receive_buffer, payload_size) < 0) {
                ++*errors;
                break;
            }
            if (memcmp(send_buffer, receive_buffer, payload_size) != 0) {
                ++*errors;
                break;
            }
        }
        if (*errors != 0) goto exchange_done;
    }

    /* Timed round-trip measurement loop */
    start = monotonic_ns();
    for (i = 0; i < count; ++i) {
        uint64_t iter_start = 0;
        if (opts && opts->samples_rtt_ns)
            iter_start = monotonic_ns();

        if (send_all(client_fd, send_buffer, payload_size) < 0 ||
            recv_all(client_fd, receive_buffer, payload_size) < 0) {
            ++*errors;
            break;
        }

        if (memcmp(send_buffer, receive_buffer, payload_size) != 0) {
            ++*errors;
            break;
        }

        if (opts && opts->samples_rtt_ns) {
            uint64_t iter_end = monotonic_ns();
            opts->samples_rtt_ns[i] = iter_end >= iter_start ? iter_end - iter_start : 0;
        }
    }
    end = monotonic_ns();
    *elapsed_ns = end >= start ? end - start : 0;

exchange_done:
    close(client_fd); client_fd = -1;

    while (waitpid(child, &status, 0) < 0) {
        if (errno == EINTR) continue;
        goto fail;
    }

    /* Clean up socket file from filesystem */
    unlink(sock_path);
    free(send_buffer);
    free(receive_buffer);
    if (sigpipe_changed) sigaction(SIGPIPE, &old_pipe, NULL);

    if (!WIFEXITED(status) || WEXITSTATUS(status) != 0 || *errors != 0) {
        errno = EIO;
        return -1;
    }
    return 0;

fail:
    {
        int saved_errno = errno;
        if (listen_fd >= 0) close(listen_fd);
        if (client_fd >= 0) close(client_fd);
        if (sock_path[0]) unlink(sock_path);
        if (child > 0) {
            kill(child, SIGTERM);
            waitpid(child, NULL, 0);
        }
        free(send_buffer);
        free(receive_buffer);
        if (sigpipe_changed) sigaction(SIGPIPE, &old_pipe, NULL);
        errno = saved_errno;
        return -1;
    }
}

int ipc_uds_run(size_t payload_size, size_t count,
                uint64_t *elapsed_ns, size_t *errors)
{
    return ipc_uds_run_opts(payload_size, count, NULL, elapsed_ns, errors);
}
