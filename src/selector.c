#include "ipc.h"

const char *transport_name(transport_t transport)
{
    switch (transport) {
    case TRANSPORT_PIPE: return "pipe";
    case TRANSPORT_SHM: return "shm";
    case TRANSPORT_ADAPTIVE: return "adaptive";
    default: return "unknown";
    }
}

/*
 * The mailbox is bounded. Small messages use shared memory; larger messages
 * use pipes. This is a simple size policy, not the paper's full adaptive
 * telemetry/hysteresis controller.
 */
transport_t select_transport(size_t payload_size, size_t threshold)
{
    if (payload_size <= threshold && payload_size <= SHM_MAX_PAYLOAD)
        return TRANSPORT_SHM;
    return TRANSPORT_PIPE;
}
