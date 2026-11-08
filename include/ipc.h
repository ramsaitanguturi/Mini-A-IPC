#ifndef IPC_H
#define IPC_H

#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif

#include <errno.h>
#include <sched.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define SHM_MAX_PAYLOAD 1024U
#define DEFAULT_THRESHOLD 1024U

/*
 * Enumeration of all supported IPC transport mechanisms:
 * - TRANSPORT_PIPE: Anonymous pipes via pipe()
 * - TRANSPORT_SHM: POSIX shared memory with semaphores
 * - TRANSPORT_ADAPTIVE: Dynamic payload-size selector (shm vs pipe)
 * - TRANSPORT_FIFO: Named pipes via mkfifo()
 * - TRANSPORT_SYSV: System V message queue via msgget(), msgsnd(), msgrcv()
 * - TRANSPORT_POSIX: POSIX message queue via mq_open(), mq_send(), mq_receive()
 * - TRANSPORT_UDS: Unix domain socket via socket(AF_UNIX, SOCK_STREAM, 0)
 */
typedef enum {
    TRANSPORT_PIPE = 0,
    TRANSPORT_SHM,
    TRANSPORT_ADAPTIVE,
    TRANSPORT_FIFO,
    TRANSPORT_SYSV,
    TRANSPORT_POSIX,
    TRANSPORT_UDS
} transport_t;

/* Optional benchmark configuration for warm-up, CPU pinning, and sample collection */
typedef struct {
    size_t warmup;            /* Untimed warm-up exchanges before measurement (default 0) */
    int cpu_producer;         /* Producer CPU core (-1 = unpinned) */
    int cpu_consumer;         /* Consumer CPU core (-1 = unpinned) */
    uint64_t *samples_rtt_ns; /* Optional array of count uint64_t elements for per-exchange RTT */
} ipc_bench_opts_t;

const char *transport_name(transport_t transport);
transport_t select_transport(size_t payload_size, size_t threshold);

/* Standard run functions (existing signatures preserved for full backwards compatibility) */
int ipc_pipe_run(size_t payload_size, size_t count,
                 uint64_t *elapsed_ns, size_t *errors);
int ipc_shm_run(size_t payload_size, size_t count,
                uint64_t *elapsed_ns, size_t *errors);
int ipc_fifo_run(size_t payload_size, size_t count,
                 uint64_t *elapsed_ns, size_t *errors);
int ipc_sysv_run(size_t payload_size, size_t count,
                 uint64_t *elapsed_ns, size_t *errors);
int ipc_posix_run(size_t payload_size, size_t count,
                  uint64_t *elapsed_ns, size_t *errors);
int ipc_uds_run(size_t payload_size, size_t count,
                uint64_t *elapsed_ns, size_t *errors);

/* Extended run functions with options for benchmarking */
int ipc_pipe_run_opts(size_t payload_size, size_t count, const ipc_bench_opts_t *opts,
                      uint64_t *elapsed_ns, size_t *errors);
int ipc_shm_run_opts(size_t payload_size, size_t count, const ipc_bench_opts_t *opts,
                     uint64_t *elapsed_ns, size_t *errors);
int ipc_fifo_run_opts(size_t payload_size, size_t count, const ipc_bench_opts_t *opts,
                      uint64_t *elapsed_ns, size_t *errors);
int ipc_sysv_run_opts(size_t payload_size, size_t count, const ipc_bench_opts_t *opts,
                      uint64_t *elapsed_ns, size_t *errors);
int ipc_posix_run_opts(size_t payload_size, size_t count, const ipc_bench_opts_t *opts,
                       uint64_t *elapsed_ns, size_t *errors);
int ipc_uds_run_opts(size_t payload_size, size_t count, const ipc_bench_opts_t *opts,
                     uint64_t *elapsed_ns, size_t *errors);

uint64_t monotonic_ns(void);

/*
 * Sets CPU affinity for the calling process to the specified CPU core.
 * Uses Linux sched_setaffinity(). Returns 0 on success, or -1 on warning/failure.
 * If cpu < 0, CPU pinning is skipped.
 */
static inline int set_cpu_affinity(int cpu)
{
    if (cpu < 0) return 0;
    cpu_set_t cpuset;
    CPU_ZERO(&cpuset);
    CPU_SET(cpu, &cpuset);
    if (sched_setaffinity(0, sizeof(cpu_set_t), &cpuset) != 0) {
        fprintf(stderr, "warning: sched_setaffinity(cpu=%d) failed: %s\n",
                cpu, strerror(errno));
        return -1;
    }
    return 0;
}

#endif
