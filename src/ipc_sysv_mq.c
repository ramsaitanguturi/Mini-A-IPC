#include "ipc.h"

#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ipc.h>
#include <sys/msg.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

/*
 * System V Message Queue IPC Implementation
 *
 * Classical System V message queues use a kernel-maintained linked list
 * of message structures identified by an integer msqid.
 *
 * System calls used:
 * - msgget(): Allocates or accesses a message queue identifier.
 * - msgsnd(): Appends a message of specified type to the queue.
 * - msgrcv(): Reads and removes a message of specified type from the queue.
 * - msgctl(): Performs control operations, including IPC_RMID for removal.
 *
 * Synchronization protocol:
 * - Parent sends request with mtype = MSG_TYPE_REQ (1).
 * - Child blocks on msgrcv() for mtype = MSG_TYPE_REQ.
 * - Child sends response with mtype = MSG_TYPE_RESP (2).
 * - Parent blocks on msgrcv() for mtype = MSG_TYPE_RESP.
 * - SIGCHLD handler without SA_RESTART interrupts blocking msgrcv() if child exits prematurely.
 */

#define MSG_TYPE_REQ  1L
#define MSG_TYPE_RESP 2L

/* Message structure required by msgsnd() and msgrcv() */
struct sysv_msg {
    long mtype;
    unsigned char mtext[1]; /* Variable-length payload */
};

/* Global flag set by SIGCHLD handler to detect child death without hanging */
static volatile sig_atomic_t g_sysv_child_exited = 0;

static void sysv_sigchld_handler(int sig)
{
    (void)sig;
    g_sysv_child_exited = 1;
}

int ipc_sysv_run_opts(size_t payload_size, size_t count, const ipc_bench_opts_t *opts,
                      uint64_t *elapsed_ns, size_t *errors)
{
    int msqid = -1;
    pid_t child = -1;
    struct sysv_msg *send_msg = NULL;
    struct sysv_msg *recv_msg = NULL;
    size_t i;
    int status = 0;
    uint64_t start, end;
    struct sigaction sa, old_sa;
    int sigchld_changed = 0;
    size_t alloc_size;

    if (!payload_size || !count || !elapsed_ns || !errors) {
        errno = EINVAL;
        return -1;
    }

    alloc_size = sizeof(long) + payload_size;
    send_msg = malloc(alloc_size);
    recv_msg = malloc(alloc_size);
    if (!send_msg || !recv_msg) goto fail;

    send_msg->mtype = MSG_TYPE_REQ;
    for (i = 0; i < payload_size; ++i)
        send_msg->mtext[i] = (unsigned char)((i * 31U + 7U) & 0xffU);
    recv_msg->mtype = MSG_TYPE_RESP;
    memset(recv_msg->mtext, 0, payload_size);

    /*
     * Create a private System V message queue using IPC_PRIVATE.
     * IPC_PRIVATE guarantees that a brand new, unique queue is allocated.
     * Permissions 0600 ensure only the owner process and its children can access it.
     */
    msqid = msgget(IPC_PRIVATE, IPC_CREAT | IPC_EXCL | 0600);
    if (msqid < 0) goto fail;

    /*
     * Install SIGCHLD handler without SA_RESTART so that blocking msgrcv()
     * calls are promptly interrupted with EINTR if the child process dies.
     */
    g_sysv_child_exited = 0;
    memset(&sa, 0, sizeof(sa));
    sa.sa_handler = sysv_sigchld_handler;
    sigemptyset(&sa.sa_mask);
    sa.sa_flags = 0; /* No SA_RESTART: allow EINTR on child exit */
    if (sigaction(SIGCHLD, &sa, &old_sa) < 0) goto fail;
    sigchld_changed = 1;

    child = fork();
    if (child < 0) goto fail;

    if (child == 0) {
        /* Child process (Consumer / Server) */
        struct sysv_msg *c_msg = malloc(alloc_size);
        const char *fault = getenv("AIPC_TEST_CHILD_EXIT");
        size_t total_exchanges = (opts ? opts->warmup : 0) + count;
        size_t j;

        if (opts && opts->cpu_consumer >= 0)
            set_cpu_affinity(opts->cpu_consumer);

        if (fault != NULL && strcmp(fault, "sysv") == 0) {
            free(c_msg);
            _exit(77);
        }

        if (!c_msg) _exit(2);

        for (j = 0; j < total_exchanges; ++j) {
            /* Receive request of type MSG_TYPE_REQ from parent */
            ssize_t n = msgrcv(msqid, c_msg, payload_size, MSG_TYPE_REQ, 0);
            if (n < 0 || (size_t)n != payload_size) {
                free(c_msg);
                _exit(3);
            }

            /* Send echo acknowledgement with type MSG_TYPE_RESP to parent */
            c_msg->mtype = MSG_TYPE_RESP;
            if (msgsnd(msqid, c_msg, payload_size, 0) < 0) {
                free(c_msg);
                _exit(4);
            }
        }

        free(c_msg);
        _exit(0);
    }

    /* Parent process (Producer / Client) */
    if (opts && opts->cpu_producer >= 0)
        set_cpu_affinity(opts->cpu_producer);

    *errors = 0;

    /* Untimed warm-up exchanges to populate cache and pipeline */
    if (opts && opts->warmup > 0) {
        for (i = 0; i < opts->warmup; ++i) {
            send_msg->mtype = MSG_TYPE_REQ;
            if (msgsnd(msqid, send_msg, payload_size, 0) < 0) {
                ++*errors;
                break;
            }
            while (msgrcv(msqid, recv_msg, payload_size, MSG_TYPE_RESP, 0) < 0) {
                if (errno == EINTR) {
                    if (g_sysv_child_exited) { ++*errors; break; }
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

        send_msg->mtype = MSG_TYPE_REQ;
        if (msgsnd(msqid, send_msg, payload_size, 0) < 0) {
            ++*errors;
            break;
        }

        while (msgrcv(msqid, recv_msg, payload_size, MSG_TYPE_RESP, 0) < 0) {
            if (errno == EINTR) {
                if (g_sysv_child_exited) { ++*errors; break; }
                continue;
            }
            ++*errors;
            break;
        }
        if (*errors != 0) break;

        if (memcmp(send_msg->mtext, recv_msg->mtext, payload_size) != 0) {
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
     * Explicitly destroy System V message queue via msgctl(IPC_RMID).
     * System V IPC objects are persistent in the kernel until destroyed or rebooted.
     */
    if (msqid >= 0) {
        msgctl(msqid, IPC_RMID, NULL);
        msqid = -1;
    }

    free(send_msg);
    free(recv_msg);
    if (sigchld_changed) sigaction(SIGCHLD, &old_sa, NULL);

    if (!WIFEXITED(status) || WEXITSTATUS(status) != 0 || *errors != 0) {
        errno = EIO;
        return -1;
    }
    return 0;

fail:
    {
        int saved_errno = errno;
        if (msqid >= 0) msgctl(msqid, IPC_RMID, NULL);
        if (child > 0) {
            kill(child, SIGTERM);
            waitpid(child, NULL, 0);
        }
        free(send_msg);
        free(recv_msg);
        if (sigchld_changed) sigaction(SIGCHLD, &old_sa, NULL);
        errno = saved_errno;
        return -1;
    }
}

int ipc_sysv_run(size_t payload_size, size_t count,
                 uint64_t *elapsed_ns, size_t *errors)
{
    return ipc_sysv_run_opts(payload_size, count, NULL, elapsed_ns, errors);
}
