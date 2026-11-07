#include "ipc.h"

#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

/* Helper function to write all bytes to a file descriptor */
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

/* Helper function to read all bytes from a file descriptor */
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

/*
 * Runs count request/response exchanges using two named pipes (FIFOs).
 * req_fifo:  Parent writes requests, Child reads requests.
 * resp_fifo: Child writes responses, Parent reads responses.
 */
int ipc_fifo_run(size_t payload_size, size_t count,
                 uint64_t *elapsed_ns, size_t *errors)
{
    char req_fifo[64] = {0};
    char resp_fifo[64] = {0};
    int req_fd = -1;
    int resp_fd = -1;
    pid_t child = -1;
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

    /* Initialize send buffer with deterministic test pattern */
    for (i = 0; i < payload_size; ++i)
        send_buffer[i] = (unsigned char)((i * 31U + 7U) & 0xffU);
    memset(receive_buffer, 0, payload_size);

    /* Form unique FIFO paths in /tmp based on current PID */
    snprintf(req_fifo, sizeof(req_fifo), "/tmp/mini_aipc_req_%d.fifo", (int)getpid());
    snprintf(resp_fifo, sizeof(resp_fifo), "/tmp/mini_aipc_resp_%d.fifo", (int)getpid());

    /* Remove any existing FIFO files with the same name */
    unlink(req_fifo);
    unlink(resp_fifo);

    /* Create the two named pipes with user-only permissions */
    if (mkfifo(req_fifo, 0600) < 0 || mkfifo(resp_fifo, 0600) < 0)
        goto fail;

    /* Ignore SIGPIPE so write errors return EPIPE instead of terminating */
    memset(&ignore_pipe, 0, sizeof(ignore_pipe));
    ignore_pipe.sa_handler = SIG_IGN;
    sigemptyset(&ignore_pipe.sa_mask);
    if (sigaction(SIGPIPE, &ignore_pipe, &old_pipe) < 0) goto fail;
    sigpipe_changed = 1;

    child = fork();
    if (child < 0) goto fail;

    if (child == 0) {
        /* Child process */
        int c_req_fd = -1;
        int c_resp_fd = -1;
        unsigned char *child_buffer = NULL;
        const char *fault = getenv("AIPC_TEST_CHILD_EXIT");
        size_t j;

        /* Open req_fifo for reading, then resp_fifo for writing */
        c_req_fd = open(req_fifo, O_RDONLY);
        if (c_req_fd < 0) _exit(1);

        c_resp_fd = open(resp_fifo, O_WRONLY);
        if (c_resp_fd < 0) {
            close(c_req_fd);
            _exit(1);
        }

        /* Test hook for child exit fault injection */
        if (fault != NULL && strcmp(fault, "fifo") == 0) {
            close(c_req_fd);
            close(c_resp_fd);
            _exit(77);
        }

        child_buffer = malloc(payload_size);
        if (!child_buffer) {
            close(c_req_fd);
            close(c_resp_fd);
            _exit(2);
        }

        /* Echo requests back to parent */
        for (j = 0; j < count; ++j) {
            if (read_all(c_req_fd, child_buffer, payload_size) < 0 ||
                write_all(c_resp_fd, child_buffer, payload_size) < 0) {
                free(child_buffer);
                close(c_req_fd);
                close(c_resp_fd);
                _exit(3);
            }
        }

        free(child_buffer);
        close(c_req_fd);
        close(c_resp_fd);
        _exit(0);
    }

    /* Parent process: open req_fifo for writing, then resp_fifo for reading */
    req_fd = open(req_fifo, O_WRONLY);
    if (req_fd < 0) goto fail;

    resp_fd = open(resp_fifo, O_RDONLY);
    if (resp_fd < 0) goto fail;

    *errors = 0;
    start = monotonic_ns();
    for (i = 0; i < count; ++i) {
        if (write_all(req_fd, send_buffer, payload_size) < 0 ||
            read_all(resp_fd, receive_buffer, payload_size) < 0) {
            ++*errors;
            break;
        }
        if (memcmp(send_buffer, receive_buffer, payload_size) != 0)
            ++*errors;
    }
    end = monotonic_ns();
    *elapsed_ns = end >= start ? end - start : 0;

    close(req_fd); req_fd = -1;
    close(resp_fd); resp_fd = -1;

    while (waitpid(child, &status, 0) < 0) {
        if (errno == EINTR) continue;
        goto fail;
    }

    /* Clean up FIFO files and resources */
    unlink(req_fifo);
    unlink(resp_fifo);
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
        if (req_fd >= 0) close(req_fd);
        if (resp_fd >= 0) close(resp_fd);
        if (req_fifo[0]) unlink(req_fifo);
        if (resp_fifo[0]) unlink(resp_fifo);
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

#ifdef IPC_FIFO_STANDALONE
static int parse_fifo_size(const char *s, size_t *out)
{
    char *end = NULL;
    unsigned long long v;
    if (s[0] == '-') return -1;
    errno = 0;
    v = strtoull(s, &end, 10);
    if (errno || !s[0] || !end || *end != '\0' || v == 0 || v > SIZE_MAX)
        return -1;
    *out = (size_t)v;
    return 0;
}

uint64_t monotonic_ns(void)
{
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) return 0;
    return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}

int main(int argc, char **argv)
{
    size_t size = 64;
    size_t count = 1;
    uint64_t elapsed_ns = 0;
    size_t errors = 0;

    if (argc == 1) {
        printf("=== Mini A-IPC: Standalone FIFO (Named Pipe) Demonstration ===\n");
    } else if (argc == 5 && strcmp(argv[1], "--size") == 0 && strcmp(argv[3], "--count") == 0) {
        if (parse_fifo_size(argv[2], &size) < 0 || parse_fifo_size(argv[4], &count) < 0) {
            fprintf(stderr, "Error: size and count must be positive integers\n");
            return 2;
        }
    } else {
        fprintf(stderr, "Usage: %s [--size BYTES --count N]\n", argv[0]);
        return 2;
    }

    if (ipc_fifo_run(size, count, &elapsed_ns, &errors) < 0) {
        perror("FIFO communication failed");
        return 1;
    }

    printf("FIFO IPC completed: %zu exchanges, %zu bytes each.\n", count, size);
    printf("Elapsed: %" PRIu64 " ns\n", elapsed_ns);
    printf("Average round-trip latency: %.2f ns\n", (double)elapsed_ns / (double)count);
    printf("Validation errors: %zu\n", errors);
    printf("Response validated successfully: data integrity verified.\n");
    printf("FIFO cleanup complete.\n");
    return errors ? 1 : 0;
}
#endif

