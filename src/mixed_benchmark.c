#include "ipc.h"

#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <semaphore.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define SMALL_SIZE 64U
#define LARGE_SIZE 16384U

typedef struct {
    sem_t empty_req, full_req, empty_resp, full_resp;
    size_t request_length;
    size_t response_length;
    unsigned char request[SHM_MAX_PAYLOAD];
    unsigned char response[SHM_MAX_PAYLOAD];
} mailbox_t;

static uint64_t mixed_monotonic_ns(void)
{
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) return 0;
    return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}

static int write_all(int fd, const void *buf, size_t n)
{
    const unsigned char *p = buf;
    size_t done = 0;
    while (done < n) {
        ssize_t k = write(fd, p + done, n - done);
        if (k < 0 && errno == EINTR) continue;
        if (k <= 0) return -1;
        done += (size_t)k;
    }
    return 0;
}
static int read_all(int fd, void *buf, size_t n)
{
    unsigned char *p = buf;
    size_t done = 0;
    while (done < n) {
        ssize_t k = read(fd, p + done, n - done);
        if (k < 0 && errno == EINTR) continue;
        if (k <= 0) return -1;
        done += (size_t)k;
    }
    return 0;
}
static int wait_sem(sem_t *s)
{
    while (sem_wait(s) < 0) { if (errno == EINTR) continue; return -1; }
    return 0;
}

static int wait_sem_monitor(sem_t *s, pid_t *child, int *child_reaped)
{
    for (;;) {
        struct timespec deadline;
        if (clock_gettime(CLOCK_REALTIME, &deadline) < 0) return -1;
        deadline.tv_nsec += 100000000L;
        if (deadline.tv_nsec >= 1000000000L) { deadline.tv_sec++; deadline.tv_nsec -= 1000000000L; }
        if (sem_timedwait(s, &deadline) == 0) return 0;
        if (errno == EINTR) continue;
        if (errno != ETIMEDOUT) return -1;
        if (*child > 0) {
            int st;
            pid_t w = waitpid(*child, &st, WNOHANG);
            if (w == *child) { *child = -1; *child_reaped = 1; errno = ECHILD; return -1; }
            if (w < 0 && errno != EINTR) return -1;
        }
    }
}

static void fill_payload(unsigned char *p, size_t n, size_t seq)
{
    size_t i;
    for (i = 0; i < n; ++i)
        p[i] = (unsigned char)((i * 31U + seq * 17U + 7U) & 0xffU);
}
static void reap(pid_t pid, int terminate)
{
    int st;
    if (pid <= 0) return;
    if (terminate) (void)kill(pid, SIGTERM);
    while (waitpid(pid, &st, 0) < 0 && errno == EINTR) {}
}

static int run_mixed(const char *policy, size_t count, size_t threshold,
                     uint64_t *elapsed, size_t *errors, size_t *small_count,
                     size_t *large_count)
{
    int req[2] = {-1,-1}, resp[2] = {-1,-1}, fd = -1, result = -1;
    char shmname[64] = {0};
    mailbox_t *box = MAP_FAILED;
    int sems = 0, status = 0, child_reaped = 0;
    pid_t child = -1;
    size_t *sizes = NULL, i;
    unsigned char *buffer = NULL, *returned = NULL;
    struct sigaction ign, old;
    int sig_changed = 0;
    uint64_t start, end;

    if (!count || !elapsed || !errors || !small_count || !large_count) {
        errno = EINVAL; return -1;
    }
    *errors = *small_count = *large_count = 0;
    sizes = malloc(count * sizeof(*sizes));
    buffer = malloc(LARGE_SIZE);
    returned = malloc(LARGE_SIZE);
    if (!sizes || !buffer || !returned) goto cleanup;

    *small_count = count * 80 / 100;
    if (*small_count == 0) *small_count = 1;
    if (*small_count > count) *small_count = count;
    *large_count = count - *small_count;
    for (i = 0; i < *small_count; ++i) sizes[i] = SMALL_SIZE;
    for (; i < count; ++i) sizes[i] = LARGE_SIZE;

    /* Deterministic Fisher-Yates shuffle: same exact sequence for both policies. */
    unsigned int seed = 0xA1C2026U;
    for (i = count; i > 1; --i) {
        size_t j;
        seed = seed * 1664525U + 1013904223U;
        j = (size_t)(seed % i);
        size_t tmp = sizes[i - 1]; sizes[i - 1] = sizes[j]; sizes[j] = tmp;
    }

    if (pipe(req) < 0 || pipe(resp) < 0) goto cleanup;
    snprintf(shmname, sizeof(shmname), "/mini_aipc_mix_%ld", (long)getpid());
    fd = shm_open(shmname, O_CREAT | O_EXCL | O_RDWR, 0600);
    if (fd < 0 || ftruncate(fd, (off_t)sizeof(*box)) < 0) goto cleanup;
    box = mmap(NULL, sizeof(*box), PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (box == MAP_FAILED) goto cleanup;
    memset(box, 0, sizeof(*box));
    if (sem_init(&box->empty_req, 1, 1) < 0) goto cleanup;
sems = 1;
    if (sem_init(&box->full_req, 1, 0) < 0) goto cleanup;
sems = 2;
    if (sem_init(&box->empty_resp, 1, 1) < 0) goto cleanup;
sems = 3;
    if (sem_init(&box->full_resp, 1, 0) < 0) goto cleanup;
sems = 4;

    memset(&ign, 0, sizeof(ign)); ign.sa_handler = SIG_IGN; sigemptyset(&ign.sa_mask);
    if (sigaction(SIGPIPE, &ign, &old) < 0) goto cleanup;
    sig_changed = 1;

    child = fork();
    if (child < 0) goto cleanup;
    if (child == 0) {
        close(req[1]); close(resp[0]);
        if (getenv("AIPC_TEST_MIXED_CHILD_EXIT") != NULL) _exit(77);
        for (i = 0; i < count; ++i) {
            size_t n = sizes[i];
            if (strcmp(policy, "adaptive") == 0 && n <= threshold && n <= SHM_MAX_PAYLOAD) {
                unsigned char expected[SHM_MAX_PAYLOAD];
                if (wait_sem_monitor(&box->full_req, &child, &child_reaped) < 0) _exit(21);
                if (box->request_length != n) _exit(22);
                fill_payload(expected, n, i);
                /* The consumer independently validates before acknowledging. */
                if (memcmp(box->request, expected, n) != 0) _exit(26);
                memcpy(box->response, box->request, n);
                box->response_length = n;
                if (sem_post(&box->empty_req) < 0 || wait_sem(&box->empty_resp) < 0 ||
                    sem_post(&box->full_resp) < 0) _exit(23);
            } else {
                uint32_t wire_len;
                if (read_all(req[0], &wire_len, sizeof(wire_len)) < 0 || wire_len != n) _exit(24);
                if (read_all(req[0], buffer, n) < 0 ||
                    write_all(resp[1], &wire_len, sizeof(wire_len)) < 0 ||
                    write_all(resp[1], buffer, n) < 0) _exit(25);
            }
        }
        _exit(0);
    }

    close(req[0]); req[0] = -1; close(resp[1]); resp[1] = -1;
    start = mixed_monotonic_ns();
    for (i = 0; i < count; ++i) {
        size_t n = sizes[i];
        fill_payload(buffer, n, i);
        if (strcmp(policy, "adaptive") == 0 && n <= threshold && n <= SHM_MAX_PAYLOAD) {
            if (wait_sem_monitor(&box->empty_req, &child, &child_reaped) < 0) { ++*errors; break; }
            memcpy(box->request, buffer, n); box->request_length = n;
            if (getenv("AIPC_TEST_CORRUPT_SHM_REQUEST") != NULL && n > 0)
                box->request[0] ^= 0xffU;
            if (sem_post(&box->full_req) < 0 || wait_sem_monitor(&box->full_resp, &child, &child_reaped) < 0) { ++*errors; break; }
            if (box->response_length != n || memcmp(box->response, buffer, n) != 0) ++*errors;
            if (sem_post(&box->empty_resp) < 0) { ++*errors; break; }
        } else {
            uint32_t wire_len = (uint32_t)n, response_len = 0;
            if (write_all(req[1], &wire_len, sizeof(wire_len)) < 0 ||
                write_all(req[1], buffer, n) < 0 ||
                read_all(resp[0], &response_len, sizeof(response_len)) < 0 ||
                response_len != wire_len || read_all(resp[0], returned, n) < 0) {
                ++*errors; break;
            }
            if (memcmp(buffer, returned, n) != 0) ++*errors;
        }
    }
    end = mixed_monotonic_ns();
    *elapsed = end >= start ? end - start : 0;
    if (*errors) { errno = EIO; goto cleanup; }
    while (waitpid(child, &status, 0) < 0) {
        if (errno == EINTR) continue;
        goto cleanup;
    }
    child_reaped = 1; child = -1;
    if (!WIFEXITED(status) || WEXITSTATUS(status) != 0) { errno = ECHILD; goto cleanup; }
    result = 0;

cleanup:
    {
        int saved = errno;
        if (child > 0 && !child_reaped) reap(child, 1);
        if (req[0] >= 0) close(req[0]);
        if (req[1] >= 0) close(req[1]);
        if (resp[0] >= 0) close(resp[0]);
        if (resp[1] >= 0) close(resp[1]);
        if (box != MAP_FAILED) {
            if (sems >= 4) sem_destroy(&box->full_resp);
            if (sems >= 3) sem_destroy(&box->empty_resp);
            if (sems >= 2) sem_destroy(&box->full_req);
            if (sems >= 1) sem_destroy(&box->empty_req);
            munmap(box, sizeof(*box));
        }
        if (fd >= 0) close(fd);
        if (shmname[0]) shm_unlink(shmname);
        if (sig_changed) sigaction(SIGPIPE, &old, NULL);
        free(sizes); free(buffer); free(returned);
        errno = saved;
    }
    return result;
}

int main(int argc, char **argv)
{
    const char *policy = NULL;
    size_t count = 10000, threshold = DEFAULT_THRESHOLD, errors, small, large;
    int i;
    uint64_t elapsed = 0;
    for (i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--policy") && i + 1 < argc) policy = argv[++i];
        else if (!strcmp(argv[i], "--count") && i + 1 < argc) count = (size_t)strtoull(argv[++i], NULL, 10);
        else if (!strcmp(argv[i], "--threshold") && i + 1 < argc) threshold = (size_t)strtoull(argv[++i], NULL, 10);
        else { fprintf(stderr, "Usage: %s --policy pipe|adaptive [--count N] [--threshold BYTES]\n", argv[0]); return 2; }
    }
    if (!policy || (strcmp(policy,"pipe") && strcmp(policy,"adaptive")) || !count || count % 5 != 0) {
        fprintf(stderr, "Policy must be pipe|adaptive and count must be a positive multiple of 5\\n");
        return 2;
    }
    if (run_mixed(policy, count, threshold, &elapsed, &errors, &small, &large) < 0) {
        perror("mixed workload failed"); return 1;
    }
    printf("Policy: %s\nThreshold: %zu\nExchanges: %zu\nSmall messages: %zu\nLarge messages: %zu\nElapsed: %" PRIu64 " ns\nAverage latency: %.2f ns\nThroughput: %.2f exchanges/s\nValidation errors: %zu\n",
           policy, threshold, count, small, large, elapsed,
           (double)elapsed/count, elapsed ? (double)count*1e9/elapsed : 0.0, errors);
    return errors ? 1 : 0;
}
