#ifndef IPC_H
#define IPC_H

#include <stddef.h>
#include <stdint.h>

#define SHM_MAX_PAYLOAD 1024U
#define DEFAULT_THRESHOLD 1024U

typedef enum {
    TRANSPORT_PIPE = 0,
    TRANSPORT_SHM,
    TRANSPORT_ADAPTIVE
} transport_t;

const char *transport_name(transport_t transport);
transport_t select_transport(size_t payload_size, size_t threshold);

/* Runs count request/response exchanges. Returns 0 on success, -1 on error. */
int ipc_pipe_run(size_t payload_size, size_t count,
                 uint64_t *elapsed_ns, size_t *errors);

int ipc_shm_run(size_t payload_size, size_t count,
                uint64_t *elapsed_ns, size_t *errors);

uint64_t monotonic_ns(void);

#endif
