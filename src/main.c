#include "ipc.h"

#include <errno.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void usage(const char *program)
{
    fprintf(stderr,
        "Usage: %s --mode pipe|shm|adaptive --size BYTES --count N\n"
        "Examples:\n"
        "  %s --mode pipe --size 64 --count 10000\n"
        "  %s --mode shm --size 64 --count 10000\n"
        "  %s --mode adaptive --size 16384 --count 10000\n",
        program, program, program, program);
}

static int parse_size(const char *s, size_t *out)
{
    char *end = NULL;
    unsigned long long v;
    if (s[0] == '-') return -1;
    errno = 0;
    v = strtoull(s, &end, 10);
    if (errno || !s[0] || !end || *end != '\0' || v == 0 || v > SIZE_MAX)
        return -1;
    *out = (size_t)v;
    return 0;
}

int main(int argc, char **argv)
{
    const char *mode = NULL;
    size_t size = 0, count = 0, errors = 0;
    uint64_t elapsed_ns = 0;
    transport_t requested, selected;
    int i, rc;

    for (i = 1; i < argc; ++i) {
        if (strcmp(argv[i], "--mode") == 0 && i + 1 < argc) mode = argv[++i];
        else if (strcmp(argv[i], "--size") == 0 && i + 1 < argc) {
            if (parse_size(argv[++i], &size) < 0) { usage(argv[0]); return 2; }
        } else if (strcmp(argv[i], "--count") == 0 && i + 1 < argc) {
            if (parse_size(argv[++i], &count) < 0) { usage(argv[0]); return 2; }
        } else { usage(argv[0]); return 2; }
    }

    if (!mode || !size || !count) { usage(argv[0]); return 2; }

    if (strcmp(mode, "pipe") == 0) requested = TRANSPORT_PIPE;
    else if (strcmp(mode, "shm") == 0) requested = TRANSPORT_SHM;
    else if (strcmp(mode, "adaptive") == 0) requested = TRANSPORT_ADAPTIVE;
    else { usage(argv[0]); return 2; }

    size_t threshold = DEFAULT_THRESHOLD;
    const char *threshold_env = getenv("AIPC_THRESHOLD");
    if (threshold_env != NULL) {
        char *end = NULL;
        unsigned long long parsed;
        errno = 0;
        if (threshold_env[0] == '-' || threshold_env[0] == '\0') {
            fprintf(stderr, "Invalid AIPC_THRESHOLD value\n");
            return 2;
        }
        parsed = strtoull(threshold_env, &end, 10);
        if (errno != 0 || end == threshold_env || *end != '\0' || parsed > SIZE_MAX) {
            fprintf(stderr, "Invalid AIPC_THRESHOLD value\n");
            return 2;
        }
        threshold = (size_t)parsed;
    }

    selected = requested == TRANSPORT_ADAPTIVE
        ? select_transport(size, threshold) : requested;

    printf("Requested mode: %s\n", transport_name(requested));
    printf("Selected transport: %s\n", transport_name(selected));
    printf("Payload: %zu bytes | Exchanges: %zu\n", size, count);

    if (selected == TRANSPORT_SHM)
        rc = ipc_shm_run(size, count, &elapsed_ns, &errors);
    else
        rc = ipc_pipe_run(size, count, &elapsed_ns, &errors);

    if (rc < 0) {
        perror("IPC run failed");
        return 1;
    }

    printf("Elapsed: %" PRIu64 " ns\n", elapsed_ns);
    printf("Average round-trip latency: %.2f ns\n",
           (double)elapsed_ns / (double)count);
    printf("Throughput: %.2f exchanges/s\n",
           elapsed_ns ? ((double)count * 1e9 / (double)elapsed_ns) : 0.0);
    printf("Validation errors: %zu\n", errors);
    return errors ? 1 : 0;
}
