#include "ipc.h"

#include <errno.h>
#include <stdio.h>
#include <signal.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static int write_all(int fd, const void *buffer, size_t length)
{
    const unsigned char *p = buffer;
    size_t done = 0;

    while (done < length) {
        ssize_t n = write(fd, p + done, length - done);
        if (n < 0) {
            if (errno == EINTR) continue;
            return -1;
        }
        if (n == 0) return -1;
        done += (size_t)n;
    }
    return 0;
}

static int read_all(int fd, void *buffer, size_t length)
{
    unsigned char *p = buffer;
    size_t done = 0;

    while (done < length) {
        ssize_t n = read(fd, p + done, length - done);
        if (n < 0) {
            if (errno == EINTR) continue;
            return -1;
        }
        if (n == 0) return -1; /* Unexpected EOF */
        done += (size_t)n;
    }
    return 0;
}

uint64_t monotonic_ns(void)
{
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) return 0;
    return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}

int ipc_pipe_run_opts(size_t payload_size, size_t count, const ipc_bench_opts_t *opts,
                      uint64_t *elapsed_ns, size_t *errors)
{
    int request_pipe[2] = {-1, -1};
    int response_pipe[2] = {-1, -1};
    pid_t child;
    unsigned char *send_buffer = NULL;
    unsigned char *receive_buffer = NULL;
    size_t i;
    int status = 0;
    uint64_t start, end;
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

    if (pipe(request_pipe) < 0 || pipe(response_pipe) < 0) goto fail;

    memset(&ignore_pipe, 0, sizeof(ignore_pipe));
    ignore_pipe.sa_handler = SIG_IGN;
    sigemptyset(&ignore_pipe.sa_mask);
    if (sigaction(SIGPIPE, &ignore_pipe, &old_pipe) < 0) goto fail;
    sigpipe_changed = 1;

    child = fork();
    if (child < 0) goto fail;

    if (child == 0) {
        unsigned char *child_buffer = malloc(payload_size);
        const char *fault = getenv("AIPC_TEST_CHILD_EXIT");
        size_t total_exchanges = (opts ? opts->warmup : 0) + count;
        size_t j;

        if (opts && opts->cpu_consumer >= 0)
            set_cpu_affinity(opts->cpu_consumer);

        close(request_pipe[1]);
        close(response_pipe[0]);

        if (fault != NULL && strcmp(fault, "pipe") == 0) _exit(77);
        if (!child_buffer) _exit(2);
        for (j = 0; j < total_exchanges; ++j) {
            if (read_all(request_pipe[0], child_buffer, payload_size) < 0 ||
                write_all(response_pipe[1], child_buffer, payload_size) < 0) {
                free(child_buffer);
                _exit(3);
            }
        }
        free(child_buffer);
        close(request_pipe[0]);
        close(response_pipe[1]);
        _exit(0);
    }

    if (opts && opts->cpu_producer >= 0)
        set_cpu_affinity(opts->cpu_producer);

    close(request_pipe[0]); request_pipe[0] = -1;
    close(response_pipe[1]); response_pipe[1] = -1;

    *errors = 0;

    /* Untimed warm-up exchanges */
    if (opts && opts->warmup > 0) {
        for (i = 0; i < opts->warmup; ++i) {
            if (write_all(request_pipe[1], send_buffer, payload_size) < 0 ||
                read_all(response_pipe[0], receive_buffer, payload_size) < 0) {
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

    start = monotonic_ns();
    for (i = 0; i < count; ++i) {
        uint64_t iter_start = 0;
        if (opts && opts->samples_rtt_ns)
            iter_start = monotonic_ns();

        if (write_all(request_pipe[1], send_buffer, payload_size) < 0 ||
            read_all(response_pipe[0], receive_buffer, payload_size) < 0) {
            ++*errors;
            break;
        }
        if (memcmp(send_buffer, receive_buffer, payload_size) != 0)
            ++*errors;

        if (opts && opts->samples_rtt_ns) {
            uint64_t iter_end = monotonic_ns();
            opts->samples_rtt_ns[i] = iter_end >= iter_start ? iter_end - iter_start : 0;
        }
    }
    end = monotonic_ns();
    *elapsed_ns = end >= start ? end - start : 0;

exchange_done:
    close(request_pipe[1]); request_pipe[1] = -1;
    close(response_pipe[0]); response_pipe[0] = -1;
    while (waitpid(child, &status, 0) < 0) {
        if (errno == EINTR) continue;
        goto fail;
    }
    free(send_buffer); free(receive_buffer);
    if (sigpipe_changed) sigaction(SIGPIPE, &old_pipe, NULL);

    if (!WIFEXITED(status) || WEXITSTATUS(status) != 0 || *errors != 0) {
        errno = EIO;
        return -1;
    }
    return 0;

fail:
    {
        int saved_errno = errno;
        if (request_pipe[0] >= 0) close(request_pipe[0]);
        if (request_pipe[1] >= 0) close(request_pipe[1]);
        if (response_pipe[0] >= 0) close(response_pipe[0]);
        if (response_pipe[1] >= 0) close(response_pipe[1]);
        free(send_buffer); free(receive_buffer);
        if (sigpipe_changed) sigaction(SIGPIPE, &old_pipe, NULL);
        errno = saved_errno;
        return -1;
    }
}

int ipc_pipe_run(size_t payload_size, size_t count,
                 uint64_t *elapsed_ns, size_t *errors)
{
    return ipc_pipe_run_opts(payload_size, count, NULL, elapsed_ns, errors);
}
