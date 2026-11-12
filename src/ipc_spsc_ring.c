#include "spsc_ring.h"

#include <errno.h>
#include <fcntl.h>
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

static void spsc_pause(size_t spin_count)
{
    if (spin_count < 16) {
        #if defined(__x86_64__) || defined(_M_X64) || defined(__i386__)
        __builtin_ia32_pause();
        #endif
    } else if (spin_count < 64) {
        sched_yield();
    } else {
        struct timespec ts = {0, 1000}; /* 1 microsecond sleep */
        nanosleep(&ts, NULL);
    }
}

static int spsc_enqueue(spsc_ring_t *ring, const unsigned char *data, size_t len, uint32_t seq, pid_t child)
{
    size_t head = atomic_load_explicit(&ring->head, memory_order_relaxed);
    size_t spins = 0;

    for (;;) {
        size_t tail = atomic_load_explicit(&ring->tail, memory_order_acquire);
        if (head - tail < SPSC_RING_CAPACITY) {
            break;
        }
        if (child > 0 && (spins & 0x3FF) == 0) {
            int st;
            if (waitpid(child, &st, WNOHANG) == child) {
                errno = ECHILD;
                return -1;
            }
        }
        spsc_pause(spins++);
    }

    spsc_slot_t *slot = &ring->slots[head % SPSC_RING_CAPACITY];
    memcpy(slot->data, data, len);
    slot->length = (uint32_t)len;
    slot->sequence = seq;

    atomic_store_explicit(&ring->head, head + 1, memory_order_release);
    return 0;
}

static int spsc_dequeue(spsc_ring_t *ring, unsigned char *out_buf, size_t *out_len, uint32_t *out_seq, pid_t child)
{
    size_t tail = atomic_load_explicit(&ring->tail, memory_order_relaxed);
    size_t spins = 0;

    for (;;) {
        size_t head = atomic_load_explicit(&ring->head, memory_order_acquire);
        if (head > tail) {
            break;
        }
        if (child > 0 && (spins & 0x3FF) == 0) {
            int st;
            if (waitpid(child, &st, WNOHANG) == child) {
                errno = ECHILD;
                return -1;
            }
        }
        spsc_pause(spins++);
    }

    spsc_slot_t *slot = &ring->slots[tail % SPSC_RING_CAPACITY];
    *out_len = slot->length;
    *out_seq = slot->sequence;
    memcpy(out_buf, slot->data, slot->length);

    atomic_store_explicit(&ring->tail, tail + 1, memory_order_release);
    return 0;
}

static void reap_spsc_child(pid_t child)
{
    int st;
    if (child <= 0) return;
    (void)kill(child, SIGTERM);
    while (waitpid(child, &st, 0) < 0 && errno == EINTR) {}
}

int ipc_spsc_run_opts(size_t payload_size, size_t count, const ipc_bench_opts_t *opts,
                      uint64_t *elapsed_ns, size_t *errors)
{
    char name[64] = {0};
    int fd = -1, result = -1, status = 0;
    spsc_dual_mailbox_t *box = MAP_FAILED;
    pid_t child = -1;
    unsigned char *expected = NULL;
    unsigned char *recv_buf = NULL;
    size_t i;
    uint64_t start = 0, end = 0;
    int child_reaped = 0;

    if (!payload_size || payload_size > SPSC_MAX_PAYLOAD || !count ||
        !elapsed_ns || !errors) {
        errno = (payload_size > SPSC_MAX_PAYLOAD) ? EMSGSIZE : EINVAL;
        return -1;
    }

    *elapsed_ns = 0;
    *errors = 0;
    snprintf(name, sizeof(name), "/mini_aipc_spsc_%ld", (long)getpid());

    fd = shm_open(name, O_CREAT | O_EXCL | O_RDWR, 0600);
    if (fd < 0) goto cleanup;
    if (ftruncate(fd, (off_t)sizeof(*box)) < 0) goto cleanup;

    box = mmap(NULL, sizeof(*box), PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (box == MAP_FAILED) goto cleanup;

    memset(box, 0, sizeof(*box));
    atomic_init(&box->req_ring.head, 0);
    atomic_init(&box->req_ring.tail, 0);
    atomic_init(&box->resp_ring.head, 0);
    atomic_init(&box->resp_ring.tail, 0);

    expected = malloc(payload_size);
    recv_buf = malloc(SPSC_MAX_PAYLOAD);
    if (!expected || !recv_buf) goto cleanup;

    for (i = 0; i < payload_size; ++i)
        expected[i] = (unsigned char)((i * 31U + 7U) & 0xffU);

    child = fork();
    if (child < 0) goto cleanup;

    if (child == 0) {
        size_t total_exchanges = (opts ? opts->warmup : 0) + count;
        size_t j;
        unsigned char child_buf[SPSC_MAX_PAYLOAD];
        size_t req_len = 0;
        uint32_t seq = 0;

        if (opts && opts->cpu_consumer >= 0)
            set_cpu_affinity(opts->cpu_consumer);

        for (j = 0; j < total_exchanges; ++j) {
            if (spsc_dequeue(&box->req_ring, child_buf, &req_len, &seq, -1) < 0)
                _exit(10);
            if (req_len != payload_size)
                _exit(11);
            if (spsc_enqueue(&box->resp_ring, child_buf, req_len, seq, -1) < 0)
                _exit(12);
        }
        _exit(0);
    }

    if (opts && opts->cpu_producer >= 0)
        set_cpu_affinity(opts->cpu_producer);

    /* Untimed warm-up exchanges */
    if (opts && opts->warmup > 0) {
        for (i = 0; i < opts->warmup; ++i) {
            size_t resp_len = 0;
            uint32_t seq = 0;
            if (spsc_enqueue(&box->req_ring, expected, payload_size, (uint32_t)i, child) < 0) {
                ++*errors; goto exchange_done;
            }
            if (spsc_dequeue(&box->resp_ring, recv_buf, &resp_len, &seq, child) < 0) {
                ++*errors; goto exchange_done;
            }
            if (resp_len != payload_size || memcmp(recv_buf, expected, payload_size) != 0)
                ++*errors;
        }
    }

    start = monotonic_ns();
    for (i = 0; i < count; ++i) {
        uint64_t iter_start = 0;
        size_t resp_len = 0;
        uint32_t seq = 0;

        if (opts && opts->samples_rtt_ns)
            iter_start = monotonic_ns();

        if (spsc_enqueue(&box->req_ring, expected, payload_size, (uint32_t)i, child) < 0) {
            ++*errors; goto exchange_done;
        }
        if (spsc_dequeue(&box->resp_ring, recv_buf, &resp_len, &seq, child) < 0) {
            ++*errors; goto exchange_done;
        }
        if (resp_len != payload_size || memcmp(recv_buf, expected, payload_size) != 0)
            ++*errors;

        if (opts && opts->samples_rtt_ns) {
            uint64_t iter_end = monotonic_ns();
            opts->samples_rtt_ns[i] = iter_end >= iter_start ? iter_end - iter_start : 0;
        }
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
        if (child > 0 && !child_reaped) {
            reap_spsc_child(child);
            child = -1;
        }
        if (box != MAP_FAILED) {
            munmap(box, sizeof(*box));
        }
        if (fd >= 0) close(fd);
        if (name[0] != '\0') shm_unlink(name);
        free(expected);
        free(recv_buf);
        errno = saved_errno;
    }
    return result;
}

int ipc_spsc_run(size_t payload_size, size_t count, uint64_t *elapsed_ns, size_t *errors)
{
    return ipc_spsc_run_opts(payload_size, count, NULL, elapsed_ns, errors);
}

