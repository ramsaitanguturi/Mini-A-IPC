#ifndef SPSC_RING_H
#define SPSC_RING_H

#include "ipc.h"
#include <stdatomic.h>

#define SPSC_RING_CAPACITY 64U
#define SPSC_MAX_PAYLOAD 1024U

#ifndef CACHE_LINE_SIZE
#define CACHE_LINE_SIZE 64
#endif

/* Individual slot in the ring buffer, cache-line aligned */
typedef struct {
    _Alignas(CACHE_LINE_SIZE) uint32_t length;
    uint32_t sequence;
    unsigned char data[SPSC_MAX_PAYLOAD];
} spsc_slot_t;

/* Single-Producer Single-Consumer lock-free ring buffer */
typedef struct {
    /* Cache line 0: Producer index (written by producer with release, read by consumer with acquire) */
    _Alignas(CACHE_LINE_SIZE) atomic_size_t head;

    /* Cache line 1: Consumer index (written by consumer with release, read by producer with acquire) */
    _Alignas(CACHE_LINE_SIZE) atomic_size_t tail;

    /* Cache line 2+: Ring buffer slots */
    _Alignas(CACHE_LINE_SIZE) spsc_slot_t slots[SPSC_RING_CAPACITY];
} spsc_ring_t;

/* Dual-channel mailbox for bidirectional request-response exchanges */
typedef struct {
    spsc_ring_t req_ring;
    spsc_ring_t resp_ring;
} spsc_dual_mailbox_t;

/* Run function for experimental SPSC ring-buffer transport */
int ipc_spsc_run(size_t payload_size, size_t count, uint64_t *elapsed_ns, size_t *errors);
int ipc_spsc_run_opts(size_t payload_size, size_t count, const ipc_bench_opts_t *opts,
                      uint64_t *elapsed_ns, size_t *errors);

#endif /* SPSC_RING_H */
