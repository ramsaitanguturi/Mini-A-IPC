#include "ipc.h"

#include <errno.h>
#include <inttypes.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void usage(const char *program)
{
    fprintf(stderr,
        "Usage: %s --mode pipe|shm|fifo|sysv|posix|uds|adaptive --size BYTES --count N [OPTIONS]\n"
        "Options:\n"
        "  --warmup N            Number of untimed warm-up exchanges (default: 0)\n"
        "  --cpu-producer CORE   Pin producer (parent) to CPU core\n"
        "  --cpu-consumer CORE   Pin consumer (child) to CPU core\n"
        "  --trial N             Trial number for benchmark reporting (default: 1)\n"
        "  --csv                 Output result as a CSV line\n"
        "Examples:\n"
        "  %s --mode pipe --size 64 --count 10000\n"
        "  %s --mode fifo --size 64 --count 10000\n"
        "  %s --mode sysv --size 64 --count 10000\n"
        "  %s --mode posix --size 64 --count 10000\n"
        "  %s --mode shm --size 64 --count 10000\n"
        "  %s --mode uds --size 64 --count 10000\n"
        "  %s --mode adaptive --size 16384 --count 10000\n",
        program, program, program, program, program, program, program, program);
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

static int parse_int(const char *s, int *out)
{
    char *end = NULL;
    long v;
    errno = 0;
    v = strtol(s, &end, 10);
    if (errno || !s[0] || !end || *end != '\0')
        return -1;
    *out = (int)v;
    return 0;
}

static int compare_uint64(const void *a, const void *b)
{
    uint64_t ua = *(const uint64_t *)a;
    uint64_t ub = *(const uint64_t *)b;
    if (ua < ub) return -1;
    if (ua > ub) return 1;
    return 0;
}

/*
 * Calculate zero-based array index for a given percentile using
 * overflow-safe integer arithmetic.
 *
 * Nearest-rank formula:
 *   P99:   k = count - count / 100
 *   P99.9: k = count - count / 1000
 *
 * Zero-based index = k - 1 (for count >= 1).
 *
 * This avoids multiplication (e.g. count * 99 or count * 999), preventing
 * integer overflow even for the largest valid exchange counts up to SIZE_MAX.
 */
static size_t nearest_rank_index(double percentile, size_t count)
{
    if (count == 0) return 0;
    size_t k;
    if (percentile == 99.0) {
        k = count - count / 100;
    } else if (percentile == 99.9) {
        k = count - count / 1000;
    } else {
        double rank = ceil((percentile / 100.0) * (double)count - 1e-9);
        k = (size_t)rank;
    }
    if (k < 1) k = 1;
    if (k > count) k = count;
    return k - 1;
}

int main(int argc, char **argv)
{
    const char *mode = NULL;
    size_t size = 0, count = 0, errors = 0;
    size_t warmup = 0;
    int cpu_producer = -1;
    int cpu_consumer = -1;
    int trial = 1;
    int csv_output = 0;
    uint64_t elapsed_ns = 0;
    transport_t requested, selected;
    ipc_bench_opts_t opts;
    uint64_t *samples = NULL;
    int i, rc;

    for (i = 1; i < argc; ++i) {
        if (strcmp(argv[i], "--mode") == 0 && i + 1 < argc) {
            mode = argv[++i];
        } else if (strcmp(argv[i], "--size") == 0 && i + 1 < argc) {
            if (parse_size(argv[++i], &size) < 0) { usage(argv[0]); return 2; }
        } else if (strcmp(argv[i], "--count") == 0 && i + 1 < argc) {
            if (parse_size(argv[++i], &count) < 0) { usage(argv[0]); return 2; }
        } else if (strcmp(argv[i], "--warmup") == 0 && i + 1 < argc) {
            if (parse_size(argv[++i], &warmup) < 0) { usage(argv[0]); return 2; }
        } else if (strcmp(argv[i], "--cpu-producer") == 0 && i + 1 < argc) {
            if (parse_int(argv[++i], &cpu_producer) < 0 || cpu_producer < 0) { usage(argv[0]); return 2; }
        } else if (strcmp(argv[i], "--cpu-consumer") == 0 && i + 1 < argc) {
            if (parse_int(argv[++i], &cpu_consumer) < 0 || cpu_consumer < 0) { usage(argv[0]); return 2; }
        } else if (strcmp(argv[i], "--trial") == 0 && i + 1 < argc) {
            if (parse_int(argv[++i], &trial) < 0 || trial < 1) { usage(argv[0]); return 2; }
        } else if (strcmp(argv[i], "--csv") == 0) {
            csv_output = 1;
        } else {
            usage(argv[0]);
            return 2;
        }
    }

    if (!mode || !size || !count) { usage(argv[0]); return 2; }

    if (strcmp(mode, "pipe") == 0) requested = TRANSPORT_PIPE;
    else if (strcmp(mode, "shm") == 0) requested = TRANSPORT_SHM;
    else if (strcmp(mode, "fifo") == 0) requested = TRANSPORT_FIFO;
    else if (strcmp(mode, "sysv") == 0) requested = TRANSPORT_SYSV;
    else if (strcmp(mode, "posix") == 0) requested = TRANSPORT_POSIX;
    else if (strcmp(mode, "uds") == 0) requested = TRANSPORT_UDS;
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

    /* Validate count to prevent integer overflow before allocation */
    if (count == 0 || count > SIZE_MAX / sizeof(uint64_t)) {
        fprintf(stderr, "Error: Invalid exchange count %zu (exceeds memory limits)\n", count);
        return 2;
    }

    /* Allocate samples buffer for exact percentile calculations */
    samples = malloc(count * sizeof(uint64_t));
    if (samples == NULL) {
        fprintf(stderr, "Error: Failed to allocate memory for %zu latency samples\n", count);
        return 1;
    }

    opts.warmup = warmup;
    opts.cpu_producer = cpu_producer;
    opts.cpu_consumer = cpu_consumer;
    opts.samples_rtt_ns = samples;

    if (!csv_output) {
        printf("Requested mode: %s\n", transport_name(requested));
        printf("Selected transport: %s\n", transport_name(selected));
        printf("Payload: %zu bytes | Exchanges: %zu\n", size, count);
    }

    if (selected == TRANSPORT_SHM)
        rc = ipc_shm_run_opts(size, count, &opts, &elapsed_ns, &errors);
    else if (selected == TRANSPORT_FIFO)
        rc = ipc_fifo_run_opts(size, count, &opts, &elapsed_ns, &errors);
    else if (selected == TRANSPORT_SYSV)
        rc = ipc_sysv_run_opts(size, count, &opts, &elapsed_ns, &errors);
    else if (selected == TRANSPORT_POSIX)
        rc = ipc_posix_run_opts(size, count, &opts, &elapsed_ns, &errors);
    else if (selected == TRANSPORT_UDS)
        rc = ipc_uds_run_opts(size, count, &opts, &elapsed_ns, &errors);
    else
        rc = ipc_pipe_run_opts(size, count, &opts, &elapsed_ns, &errors);

    if (rc < 0) {
        perror("IPC run failed");
        free(samples);
        return 1;
    }

    /* Compute latency statistics across recorded round-trip samples */
    double avg_rtt_us = 0.0, p50_rtt_us = 0.0, p99_rtt_us = 0.0, p999_rtt_us = 0.0;
    double min_rtt_us = 0.0, max_rtt_us = 0.0;
    double throughput = elapsed_ns ? ((double)count * 1e9 / (double)elapsed_ns) : 0.0;

    if (count > 0)
        avg_rtt_us = ((double)elapsed_ns / (double)count) / 1000.0;

    if (samples != NULL && count > 0) {
        qsort(samples, count, sizeof(uint64_t), compare_uint64);
        min_rtt_us = (double)samples[0] / 1000.0;
        max_rtt_us = (double)samples[count - 1] / 1000.0;

        /*
         * P50: Conventional median.
         * For odd sample count: middle element at index count / 2.
         * For even sample count: average of two middle elements at
         * index count / 2 - 1 and index count / 2.
         */
        if (count % 2 == 1) {
            p50_rtt_us = (double)samples[count / 2] / 1000.0;
        } else {
            p50_rtt_us = ((double)samples[count / 2 - 1] + (double)samples[count / 2]) / 2000.0;
        }

        /*
         * P99 and P99.9: Standard nearest-rank method with zero-based indexing.
         * For small samples (count < 1000), ceil(0.999 * count) == count,
         * so P99.9 mathematically evaluates to the maximum observed sample.
         */
        size_t idx_p99 = nearest_rank_index(99.0, count);
        p99_rtt_us = (double)samples[idx_p99] / 1000.0;

        size_t idx_p999 = nearest_rank_index(99.9, count);
        p999_rtt_us = (double)samples[idx_p999] / 1000.0;
    }

    if (csv_output) {
        /*
         * Output CSV row matching comparative_benchmark.csv format:
         * mechanism,payload_bytes,trial,count,avg_rtt_us,p50_rtt_us,p99_rtt_us,p999_rtt_us,min_rtt_us,max_rtt_us,throughput_msg_sec
         */
        printf("%s,%zu,%d,%zu,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.2f\n",
               transport_name(selected), size, trial, count,
               avg_rtt_us, p50_rtt_us, p99_rtt_us, p999_rtt_us,
               min_rtt_us, max_rtt_us, throughput);
    } else {
        printf("Elapsed: %" PRIu64 " ns\n", elapsed_ns);
        printf("Average round-trip latency: %.2f ns\n",
               (double)elapsed_ns / (double)count);
        printf("Throughput: %.2f exchanges/s\n", throughput);
        printf("Validation errors: %zu\n", errors);
        printf("P50 latency: %.2f us\n", p50_rtt_us);
        printf("P99 latency: %.2f us\n", p99_rtt_us);
        printf("P99.9 latency: %.2f us\n", p999_rtt_us);
        printf("Min latency: %.2f us\n", min_rtt_us);
        printf("Max latency: %.2f us\n", max_rtt_us);
    }

    free(samples);
    return errors ? 1 : 0;
}
