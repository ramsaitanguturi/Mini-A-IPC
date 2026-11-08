#include "ipc.h"

#include <errno.h>
#include <fcntl.h>
#include <mqueue.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

/*
 * POSIX Message Queue IPC Implementation
 *
 * POSIX message queues provide priority-based, structured messaging with
 * file descriptor-like descriptors (mqd_t) and virtual filesystem entries (/dev/mqueue).
 *
 * System calls used:
 * - mq_open(): Creates or opens a named message queue.
 * - mq_send(): Enqueues a message into the specified queue.
 * - mq_receive(): Dequeues the oldest highest-priority message.
 * - mq_close(): Closes the message queue descriptor.
 * - mq_unlink(): Removes the queue name from the system so it is freed when closed.
 *
 * Queue configuration:
 * - mq_maxmsg = 10: Maximum number of unread messages buffered in the kernel queue.
 *                   10 is the standard unprivileged maximum on Linux (/proc/sys/fs/mqueue/msg_max).
 * - mq_msgsize = payload_size: Maximum size of each individual message in bytes.
 *                              POSIX requires that buffers passed to mq_receive() must
 *                              be at least this large, otherwise mq_receive fails with EMSGSIZE.
 *
 * Synchronization:
 * - req_mq:  Parent sends request, Child receives request.
 * - resp_mq: Child sends response, Parent receives response.
 * - SIGCHLD handler without SA_RESTART interrupts mq_receive() if child exits prematurely.
 */

/* Global flag set by SIGCHLD handler to detect child death without hanging */
static volatile sig_atomic_t g_posix_child_exited = 0;

static void posix_sigchld_handler(int sig)
{
    (void)sig;
    g_posix_child_exited = 1;
}

int ipc_posix_run_opts(size_t payload_size, size_t count, const ipc_bench_opts_t *opts,
                       uint64_t *elapsed_ns, size_t *errors)
{
    char req_name[64] = {0};
    char resp_name[64] = {0};
    mqd_t req_mq = (mqd_t)-1;
    mqd_t resp_mq = (mqd_t)-1;
    pid_t child = -1;
    unsigned char *send_buffer = NULL;
    unsigned char *receive_buffer = NULL;
    size_t i;
    int status = 0;
    uint64_t start, end;
    struct mq_attr attr;
    struct sigaction sa, old_sa;
    int sigchld_changed = 0;

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

    /* Form unique queue names in the POSIX IPC namespace based on PID */
    snprintf(req_name, sizeof(req_name), "/mini_aipc_req_%d", (int)getpid());
    snprintf(resp_name, sizeof(resp_name), "/mini_aipc_resp_%d", (int)getpid());

    /* Remove any leftover queues with the same names */
    mq_unlink(req_name);
    mq_unlink(resp_name);

    /*
     * Configure queue attributes:
     * - mq_maxmsg: 10 messages max (standard unprivileged Linux ceiling).
     * - mq_msgsize: Exactly sized to the requested payload size.
     */
    memset(&attr, 0, sizeof(attr));
    attr.mq_flags = 0;
    attr.mq_maxmsg = 10;
    attr.mq_msgsize = (long)payload_size;

    /*
     * Create request and response queues with read-write permissions (0600: user only).
     * O_EXCL ensures we exclusively create new queues.
     */
    req_mq = mq_open(req_name, O_CREAT | O_EXCL | O_RDWR, 0600, &attr);
    if (req_mq == (mqd_t)-1) goto fail;

    resp_mq = mq_open(resp_name, O_CREAT | O_EXCL | O_RDWR, 0600, &attr);
    if (resp_mq == (mqd_t)-1) goto fail;

    /*
     * Install SIGCHLD handler without SA_RESTART to wake parent if child dies.
     */
    g_posix_child_exited = 0;
    memset(&sa, 0, sizeof(sa));
    sa.sa_handler = posix_sigchld_handler;
    sigemptyset(&sa.sa_mask);
    sa.sa_flags = 0; /* Interrupt mq_receive on child death */
    if (sigaction(SIGCHLD, &sa, &old_sa) < 0) goto fail;
    sigchld_changed = 1;

    child = fork();
    if (child < 0) goto fail;

    if (child == 0) {
        /* Child process (Consumer / Server) */
        unsigned char *child_buffer = malloc(payload_size);
        const char *fault = getenv("AIPC_TEST_CHILD_EXIT");
        size_t total_exchanges = (opts ? opts->warmup : 0) + count;
        size_t j;

        if (opts && opts->cpu_consumer >= 0)
            set_cpu_affinity(opts->cpu_consumer);

        if (fault != NULL && strcmp(fault, "posix") == 0) {
            free(child_buffer);
            _exit(77);
        }

        if (!child_buffer) _exit(2);

        for (j = 0; j < total_exchanges; ++j) {
            /* Receive request from parent */
            ssize_t n = mq_receive(req_mq, (char *)child_buffer, payload_size, NULL);
            if (n < 0 || (size_t)n != payload_size) {
                free(child_buffer);
                _exit(3);
            }

            /* Send response back to parent */
            if (mq_send(resp_mq, (const char *)child_buffer, payload_size, 0) < 0) {
                free(child_buffer);
                _exit(4);
            }
        }

        free(child_buffer);
        mq_close(req_mq);
        mq_close(resp_mq);
        _exit(0);
    }

    /* Parent process (Producer / Client) */
    if (opts && opts->cpu_producer >= 0)
        set_cpu_affinity(opts->cpu_producer);

    *errors = 0;

    /* Untimed warm-up exchanges */
    if (opts && opts->warmup > 0) {
        for (i = 0; i < opts->warmup; ++i) {
            if (mq_send(req_mq, (const char *)send_buffer, payload_size, 0) < 0) {
                ++*errors;
                break;
            }
            while (mq_receive(resp_mq, (char *)receive_buffer, payload_size, NULL) < 0) {
                if (errno == EINTR) {
                    if (g_posix_child_exited) { ++*errors; break; }
                    continue;
                }
                ++*errors;
                break;
            }
            if (*errors != 0) break;
        }
        if (*errors != 0) goto exchange_done;
    }

    /* Timed round-trip measurement loop */
    start = monotonic_ns();
    for (i = 0; i < count; ++i) {
        uint64_t iter_start = 0;
        if (opts && opts->samples_rtt_ns)
            iter_start = monotonic_ns();

        if (mq_send(req_mq, (const char *)send_buffer, payload_size, 0) < 0) {
            ++*errors;
            break;
        }

        while (mq_receive(resp_mq, (char *)receive_buffer, payload_size, NULL) < 0) {
            if (errno == EINTR) {
                if (g_posix_child_exited) { ++*errors; break; }
                continue;
            }
            ++*errors;
            break;
        }
        if (*errors != 0) break;

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
    /* Reap child process */
    while (waitpid(child, &status, 0) < 0) {
        if (errno == EINTR) continue;
        goto fail;
    }

    /*
     * Clean up POSIX message queues:
     * mq_close() closes the local file descriptor.
     * mq_unlink() unlinks the name from /dev/mqueue so kernel resources are freed.
     */
    mq_close(req_mq);  req_mq = (mqd_t)-1;
    mq_close(resp_mq); resp_mq = (mqd_t)-1;
    mq_unlink(req_name);
    mq_unlink(resp_name);

    free(send_buffer);
    free(receive_buffer);
    if (sigchld_changed) sigaction(SIGCHLD, &old_sa, NULL);

    if (!WIFEXITED(status) || WEXITSTATUS(status) != 0 || *errors != 0) {
        errno = EIO;
        return -1;
    }
    return 0;

fail:
    {
        int saved_errno = errno;
        if (req_mq != (mqd_t)-1) mq_close(req_mq);
        if (resp_mq != (mqd_t)-1) mq_close(resp_mq);
        if (req_name[0]) mq_unlink(req_name);
        if (resp_name[0]) mq_unlink(resp_name);
        if (child > 0) {
            kill(child, SIGTERM);
            waitpid(child, NULL, 0);
        }
        free(send_buffer);
        free(receive_buffer);
        if (sigchld_changed) sigaction(SIGCHLD, &old_sa, NULL);
        errno = saved_errno;
        return -1;
    }
}

int ipc_posix_run(size_t payload_size, size_t count,
                  uint64_t *elapsed_ns, size_t *errors)
{
    return ipc_posix_run_opts(payload_size, count, NULL, elapsed_ns, errors);
}
