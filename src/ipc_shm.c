#include "ipc.h"

#include <errno.h>
#include <fcntl.h>
#include <semaphore.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

typedef struct {
    sem_t request_empty;
    sem_t request_full;
    sem_t response_empty;
    sem_t response_full;
    size_t request_length;
    size_t response_length;
    unsigned char request[SHM_MAX_PAYLOAD];
    unsigned char response[SHM_MAX_PAYLOAD];
} shared_mailbox_t;

static int sem_wait_retry(sem_t *sem)
{
    while (sem_wait(sem) < 0) {
        if (errno == EINTR) continue;
        return -1;
    }
    return 0;
}

static void reap_child(pid_t child, int terminate)
{
    int status;
    if (child <= 0) return;
    if (terminate) (void)kill(child, SIGTERM);
    while (waitpid(child, &status, 0) < 0 && errno == EINTR) {}
}

int ipc_shm_run(size_t payload_size, size_t count,
                uint64_t *elapsed_ns, size_t *errors)
{
    char name[64] = {0};
    int fd = -1, sem_count = 0, result = -1, status = 0;
    shared_mailbox_t *box = MAP_FAILED;
    pid_t child = -1;
    unsigned char *expected = NULL;
    size_t i;
    uint64_t start = 0, end = 0;
    int child_reaped = 0;

    if (!payload_size || payload_size > SHM_MAX_PAYLOAD || !count ||
        !elapsed_ns || !errors) {
        errno = (payload_size > SHM_MAX_PAYLOAD) ? EMSGSIZE : EINVAL;
        return -1;
    }

    *elapsed_ns = 0;
    *errors = 0;
    snprintf(name, sizeof(name), "/mini_aipc_%ld", (long)getpid());

    fd = shm_open(name, O_CREAT | O_EXCL | O_RDWR, 0600);
    if (fd < 0) goto cleanup;
    if (ftruncate(fd, (off_t)sizeof(*box)) < 0) goto cleanup;

    box = mmap(NULL, sizeof(*box), PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (box == MAP_FAILED) goto cleanup;
    memset(box, 0, sizeof(*box));

    if (sem_init(&box->request_empty, 1, 1) < 0) goto cleanup;
    sem_count = 1;
    if (sem_init(&box->request_full, 1, 0) < 0) goto cleanup;
    sem_count = 2;
    if (sem_init(&box->response_empty, 1, 1) < 0) goto cleanup;
    sem_count = 3;
    if (sem_init(&box->response_full, 1, 0) < 0) goto cleanup;
    sem_count = 4;

    expected = malloc(payload_size);
    if (!expected) goto cleanup;
    for (i = 0; i < payload_size; ++i)
        expected[i] = (unsigned char)((i * 31U + 7U) & 0xffU);

    child = fork();
    if (child < 0) goto cleanup;

    if (child == 0) {
        size_t j;
        for (j = 0; j < count; ++j) {
            if (sem_wait_retry(&box->request_full) < 0) _exit(4);
            if (box->request_length == 0 ||
                box->request_length > SHM_MAX_PAYLOAD) _exit(5);

            memcpy(box->response, box->request, box->request_length);
            box->response_length = box->request_length;

            /* Release request slot, then publish response. */
            if (sem_post(&box->request_empty) < 0) _exit(6);
            if (sem_wait_retry(&box->response_empty) < 0) _exit(7);
            if (sem_post(&box->response_full) < 0) _exit(8);
        }
        _exit(0);
    }

    start = monotonic_ns();
    for (i = 0; i < count; ++i) {
        if (sem_wait_retry(&box->request_empty) < 0) { ++*errors; goto exchange_done; }
        memcpy(box->request, expected, payload_size);
        box->request_length = payload_size;
        if (sem_post(&box->request_full) < 0) { ++*errors; goto exchange_done; }

        if (sem_wait_retry(&box->response_full) < 0) { ++*errors; goto exchange_done; }
        if (box->response_length != payload_size ||
            memcmp(box->response, expected, payload_size) != 0)
            ++*errors;
        if (sem_post(&box->response_empty) < 0) { ++*errors; goto exchange_done; }
    }

exchange_done:
    end = monotonic_ns();
    *elapsed_ns = end >= start ? end - start : 0;

    if (*errors != 0) {
        errno = EIO;
        goto cleanup;
    }
    while (waitpid(child, &status, 0) < 0) {
        if (errno == EINTR) continue;
        goto cleanup;
    }
    child_reaped = 1;
    child = -1;
    if (!WIFEXITED(status) || WEXITSTATUS(status) != 0) {
        errno = ECHILD;
        goto cleanup;
    }
    result = 0;

cleanup:
    {
        int saved_errno = errno;
        /*
         * Never destroy process-shared semaphores while the child may still
         * be using them. On parent-side failure, terminate and reap first.
         */
        if (child > 0 && !child_reaped) {
            reap_child(child, 1);
            child = -1;
        }
        if (box != MAP_FAILED) {
            if (sem_count >= 4) sem_destroy(&box->response_full);
            if (sem_count >= 3) sem_destroy(&box->response_empty);
            if (sem_count >= 2) sem_destroy(&box->request_full);
            if (sem_count >= 1) sem_destroy(&box->request_empty);
            munmap(box, sizeof(*box));
        }
        if (fd >= 0) close(fd);
        if (name[0] != '\0') shm_unlink(name);
        free(expected);
        errno = saved_errno;
    }
    return result;
}
