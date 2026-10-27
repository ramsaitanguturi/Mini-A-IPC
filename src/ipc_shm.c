#include "ipc.h"

#include <errno.h>
#include <fcntl.h>
#include <semaphore.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
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

int ipc_shm_run(size_t payload_size, size_t count,
                uint64_t *elapsed_ns, size_t *errors)
{
    char name[64];
    int fd = -1, initialized = 0, result = -1, status = 0;
    shared_mailbox_t *box = MAP_FAILED;
    pid_t child = -1;
    unsigned char *expected = NULL;
    size_t i;
    uint64_t start, end;

    if (!payload_size || payload_size > SHM_MAX_PAYLOAD || !count ||
        !elapsed_ns || !errors) {
        errno = payload_size > SHM_MAX_PAYLOAD ? EMSGSIZE : EINVAL;
        return -1;
    }

    snprintf(name, sizeof(name), "/mini_aipc_%ld", (long)getpid());
    fd = shm_open(name, O_CREAT | O_EXCL | O_RDWR, 0600);
    if (fd < 0) return -1;
    if (ftruncate(fd, (off_t)sizeof(*box)) < 0) goto cleanup;

    box = mmap(NULL, sizeof(*box), PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (box == MAP_FAILED) goto cleanup;
    memset(box, 0, sizeof(*box));

    if (sem_init(&box->request_empty, 1, 1) < 0 ||
        sem_init(&box->request_full, 1, 0) < 0 ||
        sem_init(&box->response_empty, 1, 1) < 0 ||
        sem_init(&box->response_full, 1, 0) < 0)
        goto cleanup;
    initialized = 1;

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
            if (box->request_length > SHM_MAX_PAYLOAD) _exit(5);
            memcpy(box->response, box->request, box->request_length);
            box->response_length = box->request_length;
            if (sem_post(&box->request_empty) < 0 ||
                sem_wait_retry(&box->response_empty) < 0 ||
                sem_post(&box->response_full) < 0) _exit(6);
        }
        _exit(0);
    }

    *errors = 0;
    start = monotonic_ns();
    for (i = 0; i < count; ++i) {
        if (sem_wait_retry(&box->request_empty) < 0) { ++*errors; break; }
        memcpy(box->request, expected, payload_size);
        box->request_length = payload_size;
        if (sem_post(&box->request_full) < 0 ||
            sem_wait_retry(&box->response_full) < 0) {
            ++*errors; break;
        }
        if (box->response_length != payload_size ||
            memcmp(box->response, expected, payload_size) != 0)
            ++*errors;
        if (sem_post(&box->response_empty) < 0) { ++*errors; break; }
    }
    end = monotonic_ns();
    *elapsed_ns = end >= start ? end - start : 0;

    if (waitpid(child, &status, 0) < 0) goto cleanup;
    if (!WIFEXITED(status) || WEXITSTATUS(status) != 0 || *errors != 0) {
        errno = EIO;
        goto cleanup;
    }
    result = 0;

cleanup:
    {
        int saved_errno = errno;
        if (child > 0 && result < 0) {
            /* Best-effort reap if the child was created. */
            waitpid(child, &status, WNOHANG);
        }
        if (initialized) {
            sem_destroy(&box->request_empty);
            sem_destroy(&box->request_full);
            sem_destroy(&box->response_empty);
            sem_destroy(&box->response_full);
        }
        if (box != MAP_FAILED) munmap(box, sizeof(*box));
        if (fd >= 0) close(fd);
        shm_unlink(name);
        free(expected);
        errno = saved_errno;
    }
    return result;
}
