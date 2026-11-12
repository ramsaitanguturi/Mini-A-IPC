#include "ipc.h"

const char *transport_name(transport_t transport)
{
    switch (transport) {
    case TRANSPORT_PIPE: return "pipe";
    case TRANSPORT_SHM: return "shm";
    case TRANSPORT_ADAPTIVE: return "adaptive";
    case TRANSPORT_FIFO: return "fifo";
    case TRANSPORT_SYSV: return "sysv";
    case TRANSPORT_POSIX: return "posix";
    case TRANSPORT_UDS: return "uds";
    case TRANSPORT_SPSC: return "spsc";
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

void adaptive_controller_init(adaptive_controller_t *ctrl, size_t initial_threshold)
{
    if (!ctrl) return;
    ctrl->ewma_latency_shm_ns = 0.0;
    ctrl->ewma_latency_pipe_ns = 0.0;
    ctrl->threshold_bytes = initial_threshold ? initial_threshold : DEFAULT_THRESHOLD;
    ctrl->switch_count = 0;
    ctrl->current_active = TRANSPORT_SHM;
}

void update_transport_telemetry(adaptive_controller_t *ctrl, transport_t transport, uint64_t rtt_ns)
{
    if (!ctrl || rtt_ns == 0) return;
    const double alpha = 0.15; /* EWMA smoothing factor */
    if (transport == TRANSPORT_SHM) {
        if (ctrl->ewma_latency_shm_ns == 0.0)
            ctrl->ewma_latency_shm_ns = (double)rtt_ns;
        else
            ctrl->ewma_latency_shm_ns = alpha * (double)rtt_ns + (1.0 - alpha) * ctrl->ewma_latency_shm_ns;
    } else if (transport == TRANSPORT_PIPE) {
        if (ctrl->ewma_latency_pipe_ns == 0.0)
            ctrl->ewma_latency_pipe_ns = (double)rtt_ns;
        else
            ctrl->ewma_latency_pipe_ns = alpha * (double)rtt_ns + (1.0 - alpha) * ctrl->ewma_latency_pipe_ns;
    }
}

transport_t select_transport_adaptive(adaptive_controller_t *ctrl, size_t payload_size)
{
    if (payload_size > SHM_MAX_PAYLOAD)
        return TRANSPORT_PIPE;

    if (!ctrl)
        return select_transport(payload_size, DEFAULT_THRESHOLD);

    /* Hysteresis: require 8% performance delta to justify switching between transports */
    const double hysteresis = 1.08;
    if (ctrl->ewma_latency_shm_ns > 0.0 && ctrl->ewma_latency_pipe_ns > 0.0) {
        if (ctrl->current_active == TRANSPORT_SHM) {
            if (ctrl->ewma_latency_shm_ns > ctrl->ewma_latency_pipe_ns * hysteresis) {
                ctrl->current_active = TRANSPORT_PIPE;
                ctrl->switch_count++;
            }
        } else {
            if (ctrl->ewma_latency_pipe_ns > ctrl->ewma_latency_shm_ns * hysteresis) {
                ctrl->current_active = TRANSPORT_SHM;
                ctrl->switch_count++;
            }
        }
        return ctrl->current_active;
    }

    return select_transport(payload_size, ctrl->threshold_bytes);
}
