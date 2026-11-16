#include "ipc.h"

#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <limits.h>
#include <math.h>
#include <mqueue.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ipc.h>
#include <sys/msg.h>
#include <sys/resource.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <unistd.h>

#define EXIT_PASS 0
#define EXIT_FAIL 1
#define EXIT_INVALID 2
#define EXIT_UNSUPPORTED 3
#define EXIT_BLOCKED 4

#define CONC_MAGIC 0x41495043U
#define CONC_SENTINEL 0xDEADBEEFU

typedef enum {
    WORKLOAD_RTT = 0,
    WORKLOAD_CONCURRENCY,
    WORKLOAD_UNIDIRECTIONAL,
    WORKLOAD_SELECTOR_OVERHEAD
} workload_t;

typedef struct {
    uint32_t magic;
    uint32_t producer_id;
    uint64_t seq;
    uint32_t payload_bytes;
    uint32_t checksum;
} conc_msg_hdr_t;

typedef struct {
    size_t received;
    size_t errors;
} consumer_report_t;

typedef struct {
    double avg_ns;
    double stddev_ns;
    double min_ns;
    double p50_ns;
    double p90_ns;
    double p95_ns;
    double p99_ns;
    double p999_ns;
    double max_ns;
} latency_stats_t;

typedef struct {
    double user_cpu_s;
    double sys_cpu_s;
    double total_cpu_s;
    double cpu_util_pct;
    double cpu_us_per_msg;
    long parent_peak_rss_kb;
    long child_peak_rss_kb;
    long combined_peak_rss_kb;
    long minor_faults;
    long major_faults;
    long vol_ctx_switches;
    long invol_ctx_switches;
    int ctx_switches_supported;
    int minor_faults_supported;
} os_metrics_t;

static void usage(const char *prog)
{
    fprintf(stderr,
        "Usage: %s --mode pipe|fifo|sysv|posix|shm|uds|adaptive [OPTIONS]\n"
        "Options:\n"
        "  --workload rtt|concurrency|unidirectional|selector_overhead (default: rtt)\n"
        "  --size BYTES              Payload size in bytes\n"
        "  --count N                 Number of timed messages/exchanges\n"
        "  --warmup N                Untimed warm-up exchanges (default: 0)\n"
        "  --producers M             Producer process count (default: 1)\n"
        "  --consumers N             Consumer process count (default: 1)\n"
        "  --trial T                 Trial number (default: 1)\n"
        "  --threshold BYTES         Adaptive threshold (default: %u)\n"
        "  --cpu-producer CORE       Producer CPU core (-1 = unpinned)\n"
        "  --cpu-consumer CORE       Consumer CPU core (-1 = unpinned)\n"
        "  --experiment-id ID        Experiment identifier string\n"
        "  --samples-out PATH        Optional path to write raw per-exchange ns samples\n",
        prog, DEFAULT_THRESHOLD);
}

static int parse_size_arg(const char *s, size_t *out, int allow_zero)
{
    char *end = NULL;
    unsigned long long v;
    if (!s || s[0] == '\0' || s[0] == '-') return -1;
    errno = 0;
    v = strtoull(s, &end, 10);
    if (errno || !end || *end != '\0' || v > SIZE_MAX) return -1;
    if (!allow_zero && v == 0) return -1;
    *out = (size_t)v;
    return 0;
}

static int parse_int_arg(const char *s, int *out)
{
    char *end = NULL;
    long v;
    if (!s || s[0] == '\0') return -1;
    errno = 0;
    v = strtol(s, &end, 10);
    if (errno || !end || *end != '\0' || v < INT_MIN || v > INT_MAX) return -1;
    *out = (int)v;
    return 0;
}

static int parse_mode(const char *s, transport_t *out)
{
    if (!s) return -1;
    if (strcmp(s, "pipe") == 0) *out = TRANSPORT_PIPE;
    else if (strcmp(s, "fifo") == 0) *out = TRANSPORT_FIFO;
    else if (strcmp(s, "sysv") == 0) *out = TRANSPORT_SYSV;
    else if (strcmp(s, "posix") == 0) *out = TRANSPORT_POSIX;
    else if (strcmp(s, "shm") == 0) *out = TRANSPORT_SHM;
    else if (strcmp(s, "uds") == 0) *out = TRANSPORT_UDS;
    else if (strcmp(s, "adaptive") == 0) *out = TRANSPORT_ADAPTIVE;
    else return -1;
    return 0;
}

static int compare_u64(const void *a, const void *b)
{
    uint64_t ua = *(const uint64_t *)a;
    uint64_t ub = *(const uint64_t *)b;
    return (ua > ub) - (ua < ub);
}

/* Overflow-safe nearest-rank index for common percentiles. */
static size_t nearest_rank_idx(size_t count, size_t denom_complement)
{
    if (count == 0) return 0;
    size_t k = count - count / denom_complement;
    if (k < 1) k = 1;
    if (k > count) k = count;
    return k - 1;
}

static void compute_latency_stats(uint64_t *samples, size_t count, uint64_t elapsed_ns,
                                  latency_stats_t *st)
{
    memset(st, 0, sizeof(*st));
    if (!count) return;

    st->avg_ns = (double)elapsed_ns / (double)count;
    if (!samples) return;

    long double sum = 0.0L;
    for (size_t i = 0; i < count; ++i)
        sum += (long double)samples[i];
    long double mean_s = sum / (long double)count;

    if (count > 1) {
        long double sq = 0.0L;
        for (size_t i = 0; i < count; ++i) {
            long double d = (long double)samples[i] - mean_s;
            sq += d * d;
        }
        st->stddev_ns = (double)sqrtl(sq / (long double)(count - 1));
    }

    qsort(samples, count, sizeof(uint64_t), compare_u64);
    st->min_ns = (double)samples[0];
    st->max_ns = (double)samples[count - 1];
    if (count % 2 == 1) {
        st->p50_ns = (double)samples[count / 2];
    } else {
        st->p50_ns = ((double)samples[count / 2 - 1] + (double)samples[count / 2]) / 2.0;
    }
    st->p90_ns = (double)samples[nearest_rank_idx(count, 10)];
    st->p95_ns = (double)samples[nearest_rank_idx(count, 20)];
    st->p99_ns = (double)samples[nearest_rank_idx(count, 100)];
    st->p999_ns = (double)samples[nearest_rank_idx(count, 1000)];
}

static double tv_to_sec(struct timeval tv)
{
    return (double)tv.tv_sec + (double)tv.tv_usec / 1e6;
}

static void compute_os_metrics(const struct rusage *self_before,
                               const struct rusage *child_before,
                               const struct rusage *self_after,
                               const struct rusage *child_after,
                               double proc_wall_s,
                               size_t total_ops,
                               os_metrics_t *om)
{
    memset(om, 0, sizeof(*om));
    double su = tv_to_sec(self_after->ru_utime) - tv_to_sec(self_before->ru_utime);
    double ss = tv_to_sec(self_after->ru_stime) - tv_to_sec(self_before->ru_stime);
    double cu = tv_to_sec(child_after->ru_utime) - tv_to_sec(child_before->ru_utime);
    double cs = tv_to_sec(child_after->ru_stime) - tv_to_sec(child_before->ru_stime);
    if (su < 0) su = 0;
    if (ss < 0) ss = 0;
    if (cu < 0) cu = 0;
    if (cs < 0) cs = 0;

    om->user_cpu_s = su + cu;
    om->sys_cpu_s = ss + cs;
    om->total_cpu_s = om->user_cpu_s + om->sys_cpu_s;
    om->cpu_util_pct = (proc_wall_s > 0.0) ? (om->total_cpu_s / proc_wall_s) * 100.0 : 0.0;
    om->cpu_us_per_msg = (total_ops > 0) ? (om->total_cpu_s * 1e6) / (double)total_ops : 0.0;

    om->parent_peak_rss_kb = self_after->ru_maxrss;
    om->child_peak_rss_kb = child_after->ru_maxrss;
    om->combined_peak_rss_kb = om->parent_peak_rss_kb + om->child_peak_rss_kb;

    om->minor_faults = (self_after->ru_minflt - self_before->ru_minflt) +
                       (child_after->ru_minflt - child_before->ru_minflt);
    om->major_faults = (self_after->ru_majflt - self_before->ru_majflt) +
                       (child_after->ru_majflt - child_before->ru_majflt);
    om->vol_ctx_switches = (self_after->ru_nvcsw - self_before->ru_nvcsw) +
                           (child_after->ru_nvcsw - child_before->ru_nvcsw);
    om->invol_ctx_switches = (self_after->ru_nivcsw - self_before->ru_nivcsw) +
                             (child_after->ru_nivcsw - child_before->ru_nivcsw);

#if defined(__linux__)
    om->ctx_switches_supported = 1;
    om->minor_faults_supported = 1;
#else
    om->ctx_switches_supported = 0;
    om->minor_faults_supported = 0;
#endif
}

static uint32_t fnv1a_32(const unsigned char *data, size_t len)
{
    uint32_t h = 2166136261U;
    for (size_t i = 0; i < len; ++i) {
        h ^= (uint32_t)data[i];
        h *= 16777619U;
    }
    return h;
}

static void fill_conc_message(unsigned char *buf, size_t size, uint32_t prod_id, uint64_t seq)
{
    if (size >= sizeof(conc_msg_hdr_t)) {
        conc_msg_hdr_t hdr;
        size_t body_len = size - sizeof(conc_msg_hdr_t);
        unsigned char *body = buf + sizeof(conc_msg_hdr_t);
        for (size_t i = 0; i < body_len; ++i) {
            body[i] = (unsigned char)((i * 31U + (size_t)seq * 17U + prod_id * 13U + 7U) & 0xffU);
        }
        hdr.magic = CONC_MAGIC;
        hdr.producer_id = prod_id;
        hdr.seq = seq;
        hdr.payload_bytes = (uint32_t)size;
        hdr.checksum = fnv1a_32(body, body_len);
        memcpy(buf, &hdr, sizeof(hdr));
    } else {
        for (size_t i = 0; i < size; ++i)
            buf[i] = (unsigned char)((i * 31U + 7U) & 0xffU);
    }
}

static int validate_conc_message(const unsigned char *buf, size_t size, int *is_sentinel)
{
    *is_sentinel = 0;
    if (size >= sizeof(conc_msg_hdr_t)) {
        conc_msg_hdr_t hdr;
        memcpy(&hdr, buf, sizeof(hdr));
        if (hdr.magic == CONC_SENTINEL) {
            *is_sentinel = 1;
            return 0;
        }
        if (hdr.magic != CONC_MAGIC || hdr.payload_bytes != (uint32_t)size)
            return -1;
        size_t body_len = size - sizeof(conc_msg_hdr_t);
        const unsigned char *body = buf + sizeof(conc_msg_hdr_t);
        if (fnv1a_32(body, body_len) != hdr.checksum)
            return -1;
        for (size_t i = 0; i < body_len; ++i) {
            unsigned char exp = (unsigned char)((i * 31U + (size_t)hdr.seq * 17U +
                                                 hdr.producer_id * 13U + 7U) & 0xffU);
            if (body[i] != exp) return -1;
        }
        return 0;
    }
    for (size_t i = 0; i < size; ++i) {
        if (buf[i] != (unsigned char)((i * 31U + 7U) & 0xffU)) return -1;
    }
    return 0;
}

static int write_exact(int fd, const void *buf, size_t len)
{
    const unsigned char *p = buf;
    size_t done = 0;
    while (done < len) {
        ssize_t n = write(fd, p + done, len - done);
        if (n < 0) {
            if (errno == EINTR) continue;
            return -1;
        }
        if (n == 0) return -1;
        done += (size_t)n;
    }
    return 0;
}

static int read_exact(int fd, void *buf, size_t len)
{
    unsigned char *p = buf;
    size_t done = 0;
    while (done < len) {
        ssize_t n = read(fd, p + done, len - done);
        if (n < 0) {
            if (errno == EINTR) continue;
            return -1;
        }
        if (n == 0) return 1; /* EOF */
        done += (size_t)n;
    }
    return 0;
}

static int send_exact(int fd, const void *buf, size_t len)
{
    const unsigned char *p = buf;
    size_t done = 0;
    while (done < len) {
        ssize_t n = send(fd, p + done, len - done, 0);
        if (n < 0) {
            if (errno == EINTR) continue;
            return -1;
        }
        if (n == 0) return -1;
        done += (size_t)n;
    }
    return 0;
}

static int recv_exact(int fd, void *buf, size_t len)
{
    unsigned char *p = buf;
    size_t done = 0;
    while (done < len) {
        ssize_t n = recv(fd, p + done, len - done, 0);
        if (n < 0) {
            if (errno == EINTR) continue;
            return -1;
        }
        if (n == 0) return 1; /* EOF */
        done += (size_t)n;
    }
    return 0;
}

static int assign_worker_cpu(int base_cpu, int other_base, size_t idx, size_t n_consumers,
                             int is_producer)
{
    if (base_cpu < 0) return 0;
    long ncpus = sysconf(_SC_NPROCESSORS_ONLN);
    if (ncpus <= 0) ncpus = 1;
    int core;
    if (!is_producer) {
        core = (int)(((size_t)base_cpu + idx) % (size_t)ncpus);
    } else if (idx == 0) {
        core = base_cpu % (int)ncpus;
    } else {
        int anchor = (other_base >= 0) ? other_base : base_cpu;
        core = (int)(((size_t)anchor + n_consumers + idx - 1) % (size_t)ncpus);
    }
    return set_cpu_affinity(core);
}

static int run_concurrency_workload(transport_t mode, size_t size, size_t count,
                                    size_t producers, size_t consumers,
                                    int cpu_producer, int cpu_consumer,
                                    uint64_t *elapsed_ns, size_t *completed,
                                    size_t *errors, char *reason, size_t reason_cap)
{
    int data_pipe[2] = {-1, -1};
    int ready_pipe[2] = {-1, -1};
    int go_pipe[2] = {-1, -1};
    int report_pipe[2] = {-1, -1};
    char fifo_path[96] = {0};
    char mq_name[64] = {0};
    mqd_t mq = (mqd_t)-1;
    int msqid = -1;
    int *uds_listen_fds = NULL;
    char (*uds_paths)[108] = NULL;
    pid_t *prod_pids = NULL;
    pid_t *cons_pids = NULL;
    int rc = EXIT_FAIL;
    struct sigaction ignore_pipe, old_pipe;
    int sigpipe_changed = 0;

    *elapsed_ns = 0;
    *completed = 0;
    *errors = 0;

    if (mode == TRANSPORT_SHM) {
        snprintf(reason, reason_cap,
                 "POSIX shared memory mailbox (src/ipc_shm.c) is a single-slot SPSC 1P/1C design");
        return EXIT_UNSUPPORTED;
    }
    if (mode == TRANSPORT_ADAPTIVE) {
        snprintf(reason, reason_cap,
                 "Adaptive selector policy (src/selector.c) applies to 1P/1C transfers only");
        return EXIT_UNSUPPORTED;
    }
    if ((mode == TRANSPORT_PIPE || mode == TRANSPORT_FIFO) &&
        (consumers > 1 || (producers > 1 && size > (size_t)PIPE_BUF))) {
        snprintf(reason, reason_cap,
                 "Byte-stream %s guarantees atomic multi-writer writes only for size<=PIPE_BUF (%d B) and 1 consumer",
                 transport_name(mode), (int)PIPE_BUF);
        return EXIT_UNSUPPORTED;
    }

    memset(&ignore_pipe, 0, sizeof(ignore_pipe));
    ignore_pipe.sa_handler = SIG_IGN;
    sigemptyset(&ignore_pipe.sa_mask);
    if (sigaction(SIGPIPE, &ignore_pipe, &old_pipe) == 0) sigpipe_changed = 1;

    if (pipe(ready_pipe) < 0 || pipe(go_pipe) < 0 || pipe(report_pipe) < 0) {
        snprintf(reason, reason_cap, "barrier pipe creation failed: %s", strerror(errno));
        goto cleanup;
    }

    prod_pids = calloc(producers, sizeof(pid_t));
    cons_pids = calloc(consumers, sizeof(pid_t));
    if (!prod_pids || !cons_pids) {
        snprintf(reason, reason_cap, "malloc failed for pid arrays");
        goto cleanup;
    }

    /* Setup transport before fork */
    if (mode == TRANSPORT_PIPE) {
        if (pipe(data_pipe) < 0) {
            snprintf(reason, reason_cap, "pipe() failed: %s", strerror(errno));
            goto cleanup;
        }
    } else if (mode == TRANSPORT_FIFO) {
        snprintf(fifo_path, sizeof(fifo_path), "/tmp/mini_aipc_conc_%ld.fifo", (long)getpid());
        unlink(fifo_path);
        if (mkfifo(fifo_path, 0600) < 0) {
            snprintf(reason, reason_cap, "mkfifo() failed: %s", strerror(errno));
            goto cleanup;
        }
    } else if (mode == TRANSPORT_POSIX) {
        struct mq_attr attr;
        memset(&attr, 0, sizeof(attr));
        attr.mq_maxmsg = 10;
        attr.mq_msgsize = (long)size;
        snprintf(mq_name, sizeof(mq_name), "/mini_aipc_cmq_%ld", (long)getpid());
        mq_unlink(mq_name);
        mq = mq_open(mq_name, O_CREAT | O_EXCL | O_RDWR, 0600, &attr);
        if (mq == (mqd_t)-1) {
            int e = errno;
            snprintf(reason, reason_cap, "mq_open(msgsize=%zu) failed: %s", size, strerror(e));
            rc = (e == ENOSYS) ? EXIT_BLOCKED : ((e == EINVAL || e == EMSGSIZE) ? EXIT_UNSUPPORTED : EXIT_FAIL);
            goto cleanup;
        }
    } else if (mode == TRANSPORT_SYSV) {
        msqid = msgget(IPC_PRIVATE, IPC_CREAT | IPC_EXCL | 0600);
        if (msqid < 0) {
            int e = errno;
            snprintf(reason, reason_cap, "msgget() failed: %s", strerror(e));
            rc = (e == ENOSYS) ? EXIT_BLOCKED : EXIT_FAIL;
            goto cleanup;
        }
        /* Probe OS MSGMAX with a quick non-blocking probe or accept failure in worker */
    } else if (mode == TRANSPORT_UDS) {
        uds_listen_fds = malloc(consumers * sizeof(int));
        uds_paths = calloc(consumers, sizeof(*uds_paths));
        if (!uds_listen_fds || !uds_paths) {
            snprintf(reason, reason_cap, "malloc failed for UDS sockets");
            goto cleanup;
        }
        for (size_t c = 0; c < consumers; ++c) uds_listen_fds[c] = -1;
        for (size_t c = 0; c < consumers; ++c) {
            struct sockaddr_un addr;
            snprintf(uds_paths[c], sizeof(uds_paths[c]),
                     "/tmp/mini_aipc_cu_%ld_%zu.sock", (long)getpid(), c);
            unlink(uds_paths[c]);
            uds_listen_fds[c] = socket(AF_UNIX, SOCK_STREAM, 0);
            if (uds_listen_fds[c] < 0) {
                snprintf(reason, reason_cap, "socket() failed: %s", strerror(errno));
                goto cleanup;
            }
            memset(&addr, 0, sizeof(addr));
            addr.sun_family = AF_UNIX;
            snprintf(addr.sun_path, sizeof(addr.sun_path), "%s", uds_paths[c]);
            if (bind(uds_listen_fds[c], (struct sockaddr *)&addr, sizeof(addr)) < 0 ||
                listen(uds_listen_fds[c], (int)(producers + 8)) < 0) {
                snprintf(reason, reason_cap, "bind/listen failed: %s", strerror(errno));
                goto cleanup;
            }
        }
    }

    /* Fork consumers first */
    for (size_t c = 0; c < consumers; ++c) {
        pid_t pid = fork();
        if (pid < 0) {
            snprintf(reason, reason_cap, "fork consumer failed: %s", strerror(errno));
            goto cleanup;
        }
        if (pid == 0) {
            consumer_report_t rep = {0, 0};
            unsigned char *buf = malloc(size + sizeof(long));
            char b;
            close(ready_pipe[0]);
            close(go_pipe[1]);
            close(report_pipe[0]);
            assign_worker_cpu(cpu_consumer, cpu_producer, c, consumers, 0);
            if (!buf) _exit(2);

            if (mode == TRANSPORT_PIPE) {
                close(data_pipe[1]);
                if (write_exact(ready_pipe[1], "R", 1) < 0) _exit(3);
                while (read(go_pipe[0], &b, 1) > 0) {}
                for (;;) {
                    int r = read_exact(data_pipe[0], buf, size);
                    if (r == 1) break;
                    if (r < 0) { ++rep.errors; break; }
                    int sent_flag = 0;
                    if (validate_conc_message(buf, size, &sent_flag) < 0) ++rep.errors;
                    else if (!sent_flag) ++rep.received;
                }
                close(data_pipe[0]);
            } else if (mode == TRANSPORT_FIFO) {
                int fd = open(fifo_path, O_RDONLY | O_NONBLOCK);
                if (fd < 0) _exit(4);
                if (write_exact(ready_pipe[1], "R", 1) < 0) _exit(3);
                while (read(go_pipe[0], &b, 1) > 0) {}
                int flags = fcntl(fd, F_GETFL, 0);
                if (flags >= 0) fcntl(fd, F_SETFL, flags & ~O_NONBLOCK);
                for (;;) {
                    int r = read_exact(fd, buf, size);
                    if (r == 1) break;
                    if (r < 0) { ++rep.errors; break; }
                    int sent_flag = 0;
                    if (validate_conc_message(buf, size, &sent_flag) < 0) ++rep.errors;
                    else if (!sent_flag) ++rep.received;
                }
                close(fd);
            } else if (mode == TRANSPORT_POSIX) {
                if (write_exact(ready_pipe[1], "R", 1) < 0) _exit(3);
                while (read(go_pipe[0], &b, 1) > 0) {}
                for (;;) {
                    ssize_t n = mq_receive(mq, (char *)buf, size, NULL);
                    if (n < 0) {
                        if (errno == EINTR) continue;
                        ++rep.errors;
                        break;
                    }
                    if ((size_t)n != size) { ++rep.errors; continue; }
                    int sent_flag = 0;
                    if (validate_conc_message(buf, size, &sent_flag) < 0) ++rep.errors;
                    else if (sent_flag) break;
                    else ++rep.received;
                }
                mq_close(mq);
            } else if (mode == TRANSPORT_SYSV) {
                struct { long mtype; unsigned char mtext[1]; } *smsg = (void *)buf;
                if (write_exact(ready_pipe[1], "R", 1) < 0) _exit(3);
                while (read(go_pipe[0], &b, 1) > 0) {}
                for (;;) {
                    ssize_t n = msgrcv(msqid, smsg, size, 0, 0);
                    if (n < 0) {
                        if (errno == EINTR) continue;
                        ++rep.errors;
                        break;
                    }
                    if ((size_t)n != size) { ++rep.errors; continue; }
                    int sent_flag = 0;
                    if (validate_conc_message(smsg->mtext, size, &sent_flag) < 0) ++rep.errors;
                    else if (sent_flag) break;
                    else ++rep.received;
                }
            } else if (mode == TRANSPORT_UDS) {
                size_t expected_conns = (producers >= consumers)
                    ? (producers / consumers + (c < (producers % consumers) ? 1 : 0))
                    : 1;
                int *conns = calloc(expected_conns ? expected_conns : 1, sizeof(int));
                struct pollfd *pfds = calloc(expected_conns ? expected_conns : 1, sizeof(struct pollfd));
                if (!conns || !pfds) _exit(2);
                if (write_exact(ready_pipe[1], "R", 1) < 0) _exit(3);
                for (size_t k = 0; k < expected_conns; ++k) {
                    int cf = accept(uds_listen_fds[c], NULL, NULL);
                    if (cf < 0) {
                        if (errno == EINTR) { --k; continue; }
                        _exit(5);
                    }
                    conns[k] = cf;
                    pfds[k].fd = cf;
                    pfds[k].events = POLLIN;
                }
                close(uds_listen_fds[c]);
                while (read(go_pipe[0], &b, 1) > 0) {}
                size_t open_conns = expected_conns;
                while (open_conns > 0) {
                    int pr = poll(pfds, (nfds_t)expected_conns, -1);
                    if (pr < 0) {
                        if (errno == EINTR) continue;
                        ++rep.errors;
                        break;
                    }
                    for (size_t k = 0; k < expected_conns; ++k) {
                        if (pfds[k].fd < 0 || !pfds[k].revents) continue;
                        if (pfds[k].revents & (POLLIN | POLLHUP | POLLERR)) {
                            int r = recv_exact(pfds[k].fd, buf, size);
                            if (r == 1) {
                                close(pfds[k].fd);
                                pfds[k].fd = -1;
                                --open_conns;
                            } else if (r < 0) {
                                ++rep.errors;
                                close(pfds[k].fd);
                                pfds[k].fd = -1;
                                --open_conns;
                            } else {
                                int sent_flag = 0;
                                if (validate_conc_message(buf, size, &sent_flag) < 0) ++rep.errors;
                                else if (!sent_flag) ++rep.received;
                            }
                        }
                    }
                }
                free(conns);
                free(pfds);
            }

            (void)write_exact(report_pipe[1], &rep, sizeof(rep));
            close(report_pipe[1]);
            close(ready_pipe[1]);
            close(go_pipe[0]);
            free(buf);
            _exit(rep.errors ? 1 : 0);
        }
        cons_pids[c] = pid;
    }

    /* Fork producers */
    for (size_t p = 0; p < producers; ++p) {
        size_t share = count / producers + (p < (count % producers) ? 1 : 0);
        pid_t pid = fork();
        if (pid < 0) {
            snprintf(reason, reason_cap, "fork producer failed: %s", strerror(errno));
            goto cleanup;
        }
        if (pid == 0) {
            unsigned char *buf = malloc(size + sizeof(long));
            char b;
            close(ready_pipe[0]);
            close(go_pipe[1]);
            close(report_pipe[0]);
            close(report_pipe[1]);
            assign_worker_cpu(cpu_producer, cpu_consumer, p, consumers, 1);
            if (!buf) _exit(2);

            if (mode == TRANSPORT_PIPE) {
                close(data_pipe[0]);
                if (write_exact(ready_pipe[1], "R", 1) < 0) _exit(3);
                while (read(go_pipe[0], &b, 1) > 0) {}
                for (size_t s = 0; s < share; ++s) {
                    fill_conc_message(buf, size, (uint32_t)p, (uint64_t)s);
                    if (producers == 1) {
                        if (write_exact(data_pipe[1], buf, size) < 0) _exit(6);
                    } else {
                        ssize_t n;
                        do { n = write(data_pipe[1], buf, size); } while (n < 0 && errno == EINTR);
                        if (n < 0 || (size_t)n != size) _exit(6);
                    }
                }
                close(data_pipe[1]);
            } else if (mode == TRANSPORT_FIFO) {
                int fd = open(fifo_path, O_WRONLY);
                if (fd < 0) _exit(4);
                if (write_exact(ready_pipe[1], "R", 1) < 0) _exit(3);
                while (read(go_pipe[0], &b, 1) > 0) {}
                for (size_t s = 0; s < share; ++s) {
                    fill_conc_message(buf, size, (uint32_t)p, (uint64_t)s);
                    if (producers == 1) {
                        if (write_exact(fd, buf, size) < 0) _exit(6);
                    } else {
                        ssize_t n;
                        do { n = write(fd, buf, size); } while (n < 0 && errno == EINTR);
                        if (n < 0 || (size_t)n != size) _exit(6);
                    }
                }
                close(fd);
            } else if (mode == TRANSPORT_POSIX) {
                if (write_exact(ready_pipe[1], "R", 1) < 0) _exit(3);
                while (read(go_pipe[0], &b, 1) > 0) {}
                for (size_t s = 0; s < share; ++s) {
                    fill_conc_message(buf, size, (uint32_t)p, (uint64_t)s);
                    while (mq_send(mq, (const char *)buf, size, 0) < 0) {
                        if (errno == EINTR) continue;
                        _exit(6);
                    }
                }
                mq_close(mq);
            } else if (mode == TRANSPORT_SYSV) {
                struct { long mtype; unsigned char mtext[1]; } *smsg = (void *)buf;
                smsg->mtype = 1L;
                if (write_exact(ready_pipe[1], "R", 1) < 0) _exit(3);
                while (read(go_pipe[0], &b, 1) > 0) {}
                for (size_t s = 0; s < share; ++s) {
                    fill_conc_message(smsg->mtext, size, (uint32_t)p, (uint64_t)s);
                    while (msgsnd(msqid, smsg, size, 0) < 0) {
                        if (errno == EINTR) continue;
                        if (errno == EINVAL || errno == EMSGSIZE) _exit(7);
                        _exit(6);
                    }
                }
            } else if (mode == TRANSPORT_UDS) {
                size_t nconns = (producers >= consumers) ? 1 : consumers;
                int *socks = calloc(nconns, sizeof(int));
                if (!socks) _exit(2);
                for (size_t k = 0; k < nconns; ++k) {
                    size_t target_c = (producers >= consumers) ? (p % consumers) : k;
                    struct sockaddr_un addr;
                    socks[k] = socket(AF_UNIX, SOCK_STREAM, 0);
                    if (socks[k] < 0) _exit(5);
                    memset(&addr, 0, sizeof(addr));
                    addr.sun_family = AF_UNIX;
                    snprintf(addr.sun_path, sizeof(addr.sun_path), "%s", uds_paths[target_c]);
                    if (connect(socks[k], (struct sockaddr *)&addr, sizeof(addr)) < 0) _exit(5);
                }
                if (write_exact(ready_pipe[1], "R", 1) < 0) _exit(3);
                while (read(go_pipe[0], &b, 1) > 0) {}
                for (size_t s = 0; s < share; ++s) {
                    fill_conc_message(buf, size, (uint32_t)p, (uint64_t)s);
                    if (send_exact(socks[s % nconns], buf, size) < 0) _exit(6);
                }
                for (size_t k = 0; k < nconns; ++k) close(socks[k]);
                free(socks);
            }

            close(ready_pipe[1]);
            close(go_pipe[0]);
            free(buf);
            _exit(0);
        }
        prod_pids[p] = pid;
    }

    /* Coordinator: close unused pipe ends, wait for all workers ready, start clock */
    if (data_pipe[0] >= 0) { close(data_pipe[0]); data_pipe[0] = -1; }
    if (data_pipe[1] >= 0) { close(data_pipe[1]); data_pipe[1] = -1; }
    if (uds_listen_fds) {
        for (size_t c = 0; c < consumers; ++c) {
            if (uds_listen_fds[c] >= 0) { close(uds_listen_fds[c]); uds_listen_fds[c] = -1; }
        }
    }
    close(ready_pipe[1]); ready_pipe[1] = -1;
    close(go_pipe[0]); go_pipe[0] = -1;
    close(report_pipe[1]); report_pipe[1] = -1;

    for (size_t w = 0; w < producers + consumers; ++w) {
        char r;
        if (read_exact(ready_pipe[0], &r, 1) != 0) {
            snprintf(reason, reason_cap, "worker failed before barrier");
            goto cleanup;
        }
    }
    close(ready_pipe[0]); ready_pipe[0] = -1;

    uint64_t start_ns = monotonic_ns();
    close(go_pipe[1]); go_pipe[1] = -1; /* Release all workers simultaneously */

    int prod_unsupported = 0;
    int prod_failed = 0;
    for (size_t p = 0; p < producers; ++p) {
        int st = 0;
        while (waitpid(prod_pids[p], &st, 0) < 0 && errno == EINTR) {}
        prod_pids[p] = 0;
        if (!WIFEXITED(st) || WEXITSTATUS(st) != 0) {
            if (WIFEXITED(st) && WEXITSTATUS(st) == 7) prod_unsupported = 1;
            else prod_failed = 1;
        }
    }

    /* For message queues, push N sentinels after all producers exit */
    if (mode == TRANSPORT_POSIX || mode == TRANSPORT_SYSV) {
        unsigned char *sbuf = calloc(1, size + sizeof(long));
        if (sbuf) {
            conc_msg_hdr_t hdr;
            memset(&hdr, 0, sizeof(hdr));
            hdr.magic = CONC_SENTINEL;
            for (size_t c = 0; c < consumers; ++c) {
                if (mode == TRANSPORT_POSIX) {
                    if (size >= sizeof(hdr)) memcpy(sbuf, &hdr, sizeof(hdr));
                    while (mq_send(mq, (const char *)sbuf, size, 0) < 0 && errno == EINTR) {}
                } else {
                    struct { long mtype; unsigned char mtext[1]; } *smsg = (void *)sbuf;
                    smsg->mtype = 1L;
                    if (size >= sizeof(hdr)) memcpy(smsg->mtext, &hdr, sizeof(hdr));
                    while (msgsnd(msqid, smsg, size, 0) < 0 && errno == EINTR) {}
                }
            }
            free(sbuf);
        }
    }

    int cons_failed = 0;
    for (size_t c = 0; c < consumers; ++c) {
        int st = 0;
        while (waitpid(cons_pids[c], &st, 0) < 0 && errno == EINTR) {}
        cons_pids[c] = 0;
        if (!WIFEXITED(st) || WEXITSTATUS(st) != 0) cons_failed = 1;
    }
    uint64_t end_ns = monotonic_ns();
    *elapsed_ns = (end_ns >= start_ns) ? (end_ns - start_ns) : 0;

    for (size_t c = 0; c < consumers; ++c) {
        consumer_report_t rep = {0, 0};
        if (read_exact(report_pipe[0], &rep, sizeof(rep)) == 0) {
            *completed += rep.received;
            *errors += rep.errors;
        } else {
            ++(*errors);
        }
    }
    close(report_pipe[0]); report_pipe[0] = -1;

    if (prod_unsupported) {
        snprintf(reason, reason_cap, "payload size %zu exceeds OS queue limit", size);
        rc = EXIT_UNSUPPORTED;
    } else if (prod_failed || cons_failed || *errors != 0 || *completed != count) {
        snprintf(reason, reason_cap,
                 "integrity or worker failure (completed=%zu/%zu errors=%zu)",
                 *completed, count, *errors);
        rc = EXIT_FAIL;
    } else {
        snprintf(reason, reason_cap, "ok");
        rc = EXIT_PASS;
    }

cleanup:
    if (prod_pids) {
        for (size_t p = 0; p < producers; ++p) {
            if (prod_pids[p] > 0) { kill(prod_pids[p], SIGTERM); waitpid(prod_pids[p], NULL, 0); }
        }
    }
    if (cons_pids) {
        for (size_t c = 0; c < consumers; ++c) {
            if (cons_pids[c] > 0) { kill(cons_pids[c], SIGTERM); waitpid(cons_pids[c], NULL, 0); }
        }
    }
    if (data_pipe[0] >= 0) close(data_pipe[0]);
    if (data_pipe[1] >= 0) close(data_pipe[1]);
    if (ready_pipe[0] >= 0) close(ready_pipe[0]);
    if (ready_pipe[1] >= 0) close(ready_pipe[1]);
    if (go_pipe[0] >= 0) close(go_pipe[0]);
    if (go_pipe[1] >= 0) close(go_pipe[1]);
    if (report_pipe[0] >= 0) close(report_pipe[0]);
    if (report_pipe[1] >= 0) close(report_pipe[1]);
    if (fifo_path[0]) unlink(fifo_path);
    if (mq != (mqd_t)-1) mq_close(mq);
    if (mq_name[0]) mq_unlink(mq_name);
    if (msqid >= 0) msgctl(msqid, IPC_RMID, NULL);
    if (uds_listen_fds) {
        for (size_t c = 0; c < consumers; ++c) {
            if (uds_listen_fds[c] >= 0) close(uds_listen_fds[c]);
        }
    }
    if (uds_paths) {
        for (size_t c = 0; c < consumers; ++c) {
            if (uds_paths[c][0]) unlink(uds_paths[c]);
        }
    }
    free(uds_listen_fds);
    free(uds_paths);
    free(prod_pids);
    free(cons_pids);
    if (sigpipe_changed) sigaction(SIGPIPE, &old_pipe, NULL);
    return rc;
}

static void print_json_result(const char *exp_id, const char *status, const char *reason,
                              const char *req_mode, const char *sel_mode,
                              const char *workload_str, const char *lat_sem,
                              size_t size, size_t producers, size_t consumers,
                              int trial, size_t warmup, size_t target_msgs,
                              size_t completed_msgs, size_t errors,
                              uint64_t elapsed_ns, const latency_stats_t *st,
                              const os_metrics_t *om)
{
    double dur_s = (double)elapsed_ns / 1e9;
    double msg_s = (dur_s > 0.0 && completed_msgs > 0) ? ((double)completed_msgs / dur_s) : 0.0;
    double bytes_s = msg_s * (double)size;
    double mb_s = bytes_s / 1e6;
    double wire_mb_s = (strcmp(lat_sem, "round_trip_rtt") == 0) ? (2.0 * mb_s) : mb_s;

    printf("{");
    printf("\"experiment_id\":\"%s\",", exp_id);
    printf("\"status\":\"%s\",", status);
    printf("\"status_reason\":\"%s\",", reason);
    printf("\"requested_mode\":\"%s\",", req_mode);
    printf("\"selected_transport\":\"%s\",", sel_mode);
    printf("\"workload_type\":\"%s\",", workload_str);
    printf("\"latency_semantics\":\"%s\",", lat_sem);
    printf("\"payload_bytes\":%zu,", size);
    printf("\"producers\":%zu,", producers);
    printf("\"consumers\":%zu,", consumers);
    printf("\"trial\":%d,", trial);
    printf("\"warmup_count\":%zu,", warmup);
    printf("\"target_messages\":%zu,", target_msgs);
    printf("\"completed_messages\":%zu,", completed_msgs);
    printf("\"validation_errors\":%zu,", errors);
    printf("\"elapsed_ns\":%" PRIu64 ",", elapsed_ns);
    printf("\"duration_s\":%.9f,", dur_s);

    if (strcmp(status, "PASS") == 0 && strcmp(workload_str, "single_pair_rtt") == 0) {
        printf("\"avg_rtt_us\":%.6f,", st->avg_ns / 1000.0);
        printf("\"stddev_rtt_us\":%.6f,", st->stddev_ns / 1000.0);
        printf("\"min_rtt_us\":%.6f,", st->min_ns / 1000.0);
        printf("\"p50_rtt_us\":%.6f,", st->p50_ns / 1000.0);
        printf("\"p90_rtt_us\":%.6f,", st->p90_ns / 1000.0);
        printf("\"p95_rtt_us\":%.6f,", st->p95_ns / 1000.0);
        printf("\"p99_rtt_us\":%.6f,", st->p99_ns / 1000.0);
        printf("\"p999_rtt_us\":%.6f,", st->p999_ns / 1000.0);
        printf("\"max_rtt_us\":%.6f,", st->max_ns / 1000.0);
    } else if (strcmp(status, "PASS") == 0 && strcmp(workload_str, "selector_overhead") == 0) {
        printf("\"avg_rtt_us\":%.9f,", st->avg_ns / 1000.0);
        printf("\"stddev_rtt_us\":null,\"min_rtt_us\":null,\"p50_rtt_us\":null,"
               "\"p90_rtt_us\":null,\"p95_rtt_us\":null,\"p99_rtt_us\":null,"
               "\"p999_rtt_us\":null,\"max_rtt_us\":null,");
    } else {
        printf("\"avg_rtt_us\":null,\"stddev_rtt_us\":null,\"min_rtt_us\":null,"
               "\"p50_rtt_us\":null,\"p90_rtt_us\":null,\"p95_rtt_us\":null,"
               "\"p99_rtt_us\":null,\"p999_rtt_us\":null,\"max_rtt_us\":null,");
    }

    if (strcmp(status, "PASS") == 0) {
        if (strcmp(workload_str, "selector_overhead") == 0) {
            printf("\"throughput_msg_s\":%.4f,\"bytes_per_sec\":null,\"mb_per_sec\":null,\"wire_mb_per_sec\":null,", msg_s);
        } else {
            printf("\"throughput_msg_s\":%.4f,", msg_s);
            printf("\"bytes_per_sec\":%.4f,", bytes_s);
            printf("\"mb_per_sec\":%.6f,", mb_s);
            printf("\"wire_mb_per_sec\":%.6f,", wire_mb_s);
        }
        printf("\"user_cpu_s\":%.6f,", om->user_cpu_s);
        printf("\"sys_cpu_s\":%.6f,", om->sys_cpu_s);
        printf("\"total_cpu_s\":%.6f,", om->total_cpu_s);
        printf("\"cpu_util_pct\":%.3f,", om->cpu_util_pct);
        printf("\"cpu_us_per_msg\":%.6f,", om->cpu_us_per_msg);
        printf("\"parent_peak_rss_kb\":%ld,", om->parent_peak_rss_kb);
        printf("\"child_peak_rss_kb\":%ld,", om->child_peak_rss_kb);
        printf("\"combined_peak_rss_kb\":%ld,", om->combined_peak_rss_kb);
        printf("\"major_page_faults\":%ld,", om->major_faults);
        if (om->minor_faults_supported) printf("\"minor_page_faults\":%ld,", om->minor_faults);
        else printf("\"minor_page_faults\":null,");
        if (om->ctx_switches_supported) {
            printf("\"voluntary_ctx_switches\":%ld,\"involuntary_ctx_switches\":%ld",
                   om->vol_ctx_switches, om->invol_ctx_switches);
        } else {
            printf("\"voluntary_ctx_switches\":null,\"involuntary_ctx_switches\":null");
        }
    } else {
        printf("\"throughput_msg_s\":null,\"bytes_per_sec\":null,\"mb_per_sec\":null,"
               "\"wire_mb_per_sec\":null,\"user_cpu_s\":null,\"sys_cpu_s\":null,"
               "\"total_cpu_s\":null,\"cpu_util_pct\":null,\"cpu_us_per_msg\":null,"
               "\"parent_peak_rss_kb\":null,\"child_peak_rss_kb\":null,"
               "\"combined_peak_rss_kb\":null,\"major_page_faults\":null,"
               "\"minor_page_faults\":null,\"voluntary_ctx_switches\":null,"
               "\"involuntary_ctx_switches\":null");
    }
    printf("}\n");
}

int main(int argc, char **argv)
{
    const char *mode_str = NULL;
    const char *workload_str = "rtt";
    const char *exp_id = "exp_manual";
    const char *samples_out = NULL;
    size_t size = 0, count = 0, warmup = 0, producers = 1, consumers = 1;
    size_t threshold = DEFAULT_THRESHOLD;
    int threshold_set = 0;
    int trial = 1, cpu_producer = -1, cpu_consumer = -1;
    workload_t workload = WORKLOAD_RTT;
    transport_t requested, selected;

    for (int i = 1; i < argc; ++i) {
        if (strcmp(argv[i], "--mode") == 0 && i + 1 < argc) mode_str = argv[++i];
        else if (strcmp(argv[i], "--workload") == 0 && i + 1 < argc) workload_str = argv[++i];
        else if (strcmp(argv[i], "--size") == 0 && i + 1 < argc) {
            if (parse_size_arg(argv[++i], &size, 0) < 0) { usage(argv[0]); return EXIT_INVALID; }
        } else if (strcmp(argv[i], "--count") == 0 && i + 1 < argc) {
            if (parse_size_arg(argv[++i], &count, 0) < 0) { usage(argv[0]); return EXIT_INVALID; }
        } else if (strcmp(argv[i], "--warmup") == 0 && i + 1 < argc) {
            if (parse_size_arg(argv[++i], &warmup, 1) < 0) { usage(argv[0]); return EXIT_INVALID; }
        } else if (strcmp(argv[i], "--producers") == 0 && i + 1 < argc) {
            if (parse_size_arg(argv[++i], &producers, 0) < 0) { usage(argv[0]); return EXIT_INVALID; }
        } else if (strcmp(argv[i], "--consumers") == 0 && i + 1 < argc) {
            if (parse_size_arg(argv[++i], &consumers, 0) < 0) { usage(argv[0]); return EXIT_INVALID; }
        } else if (strcmp(argv[i], "--trial") == 0 && i + 1 < argc) {
            if (parse_int_arg(argv[++i], &trial) < 0 || trial < 1) { usage(argv[0]); return EXIT_INVALID; }
        } else if (strcmp(argv[i], "--threshold") == 0 && i + 1 < argc) {
            if (parse_size_arg(argv[++i], &threshold, 1) < 0) { usage(argv[0]); return EXIT_INVALID; }
            threshold_set = 1;
        } else if (strcmp(argv[i], "--cpu-producer") == 0 && i + 1 < argc) {
            if (parse_int_arg(argv[++i], &cpu_producer) < 0 || cpu_producer < -1) { usage(argv[0]); return EXIT_INVALID; }
        } else if (strcmp(argv[i], "--cpu-consumer") == 0 && i + 1 < argc) {
            if (parse_int_arg(argv[++i], &cpu_consumer) < 0 || cpu_consumer < -1) { usage(argv[0]); return EXIT_INVALID; }
        } else if (strcmp(argv[i], "--experiment-id") == 0 && i + 1 < argc) {
            exp_id = argv[++i];
        } else if (strcmp(argv[i], "--samples-out") == 0 && i + 1 < argc) {
            samples_out = argv[++i];
        } else {
            usage(argv[0]);
            return EXIT_INVALID;
        }
    }

    if (strcmp(workload_str, "rtt") == 0) workload = WORKLOAD_RTT;
    else if (strcmp(workload_str, "concurrency") == 0) workload = WORKLOAD_CONCURRENCY;
    else if (strcmp(workload_str, "unidirectional") == 0) workload = WORKLOAD_UNIDIRECTIONAL;
    else if (strcmp(workload_str, "selector_overhead") == 0) workload = WORKLOAD_SELECTOR_OVERHEAD;
    else { usage(argv[0]); return EXIT_INVALID; }

    if (parse_mode(mode_str, &requested) < 0 || size == 0 || count == 0) {
        usage(argv[0]);
        return EXIT_INVALID;
    }

    if (!threshold_set) {
        const char *env_t = getenv("AIPC_THRESHOLD");
        if (env_t && parse_size_arg(env_t, &threshold, 1) < 0) return EXIT_INVALID;
    }

    selected = (requested == TRANSPORT_ADAPTIVE) ? select_transport(size, threshold) : requested;

    latency_stats_t stats;
    os_metrics_t om;
    memset(&stats, 0, sizeof(stats));
    memset(&om, 0, sizeof(om));
    uint64_t elapsed_ns = 0;
    size_t errors = 0;
    size_t completed = 0;
    char reason[256] = "ok";

    if (workload == WORKLOAD_SELECTOR_OVERHEAD) {
        volatile transport_t sink = TRANSPORT_PIPE;
        struct rusage sb, cb, sa, ca;
        getrusage(RUSAGE_SELF, &sb);
        getrusage(RUSAGE_CHILDREN, &cb);
        uint64_t t0 = monotonic_ns();
        for (size_t i = 0; i < count; ++i)
            sink = select_transport(size, threshold);
        uint64_t t1 = monotonic_ns();
        (void)sink;
        getrusage(RUSAGE_SELF, &sa);
        getrusage(RUSAGE_CHILDREN, &ca);
        elapsed_ns = (t1 >= t0) ? (t1 - t0) : 0;
        stats.avg_ns = (double)elapsed_ns / (double)count;
        compute_os_metrics(&sb, &cb, &sa, &ca, (double)elapsed_ns / 1e9, count, &om);
        print_json_result(exp_id, "PASS", "ok", transport_name(requested),
                          transport_name(selected), "selector_overhead", "decision_only",
                          size, 1, 1, trial, 0, count, count, 0, elapsed_ns, &stats, &om);
        return EXIT_PASS;
    }

    if (workload == WORKLOAD_RTT) {
        if (producers != 1 || consumers != 1) {
            snprintf(reason, sizeof(reason),
                     "single_pair_rtt only supports 1 producer and 1 consumer");
            print_json_result(exp_id, "UNSUPPORTED", reason, transport_name(requested),
                              transport_name(selected), "single_pair_rtt", "round_trip_rtt",
                              size, producers, consumers, trial, warmup, count, 0, 0, 0, &stats, &om);
            return EXIT_UNSUPPORTED;
        }
        if (count > SIZE_MAX / sizeof(uint64_t)) return EXIT_INVALID;
        uint64_t *samples = malloc(count * sizeof(uint64_t));
        if (!samples) return EXIT_FAIL;

        ipc_bench_opts_t opts;
        opts.warmup = warmup;
        opts.cpu_producer = cpu_producer;
        opts.cpu_consumer = cpu_consumer;
        opts.samples_rtt_ns = samples;

        struct rusage sb, cb, sa, ca;
        getrusage(RUSAGE_SELF, &sb);
        getrusage(RUSAGE_CHILDREN, &cb);
        uint64_t wall0 = monotonic_ns();

        int rc = -1;
        errno = 0;
        if (selected == TRANSPORT_SHM) rc = ipc_shm_run_opts(size, count, &opts, &elapsed_ns, &errors);
        else if (selected == TRANSPORT_FIFO) rc = ipc_fifo_run_opts(size, count, &opts, &elapsed_ns, &errors);
        else if (selected == TRANSPORT_SYSV) rc = ipc_sysv_run_opts(size, count, &opts, &elapsed_ns, &errors);
        else if (selected == TRANSPORT_POSIX) rc = ipc_posix_run_opts(size, count, &opts, &elapsed_ns, &errors);
        else if (selected == TRANSPORT_UDS) rc = ipc_uds_run_opts(size, count, &opts, &elapsed_ns, &errors);
        else rc = ipc_pipe_run_opts(size, count, &opts, &elapsed_ns, &errors);
        int saved_errno = errno;

        uint64_t wall1 = monotonic_ns();
        getrusage(RUSAGE_SELF, &sa);
        getrusage(RUSAGE_CHILDREN, &ca);
        double proc_wall_s = (wall1 >= wall0) ? ((double)(wall1 - wall0) / 1e9) : 0.0;

        if (rc < 0) {
            const char *status_str = "FAIL";
            int exit_code = EXIT_FAIL;
            if (saved_errno == ENOSYS) {
                status_str = "BLOCKED";
                exit_code = EXIT_BLOCKED;
                snprintf(reason, sizeof(reason), "%s unsupported/not implemented in host runtime (ENOSYS)",
                         transport_name(selected));
            } else if (saved_errno == EMSGSIZE || saved_errno == EINVAL) {
                status_str = "UNSUPPORTED";
                exit_code = EXIT_UNSUPPORTED;
                snprintf(reason, sizeof(reason), "%s payload %zu bytes exceeds transport limit (%s)",
                         transport_name(selected), size, strerror(saved_errno));
            } else {
                snprintf(reason, sizeof(reason), "%s failed: %s (errors=%zu)",
                         transport_name(selected), strerror(saved_errno), errors);
            }
            free(samples);
            print_json_result(exp_id, status_str, reason, transport_name(requested),
                              transport_name(selected), "single_pair_rtt", "round_trip_rtt",
                              size, 1, 1, trial, warmup, count, 0, errors, 0, &stats, &om);
            return exit_code;
        }

        if (samples_out) {
            FILE *sf = fopen(samples_out, "w");
            if (sf) {
                for (size_t i = 0; i < count; ++i)
                    fprintf(sf, "%" PRIu64 "\n", samples[i]);
                fclose(sf);
            }
        }

        completed = (errors == 0) ? count : 0;
        compute_latency_stats(samples, count, elapsed_ns, &stats);
        compute_os_metrics(&sb, &cb, &sa, &ca, proc_wall_s, warmup + count, &om);
        free(samples);

        const char *status_str = (errors == 0) ? "PASS" : "FAIL";
        if (errors != 0) snprintf(reason, sizeof(reason), "validation errors=%zu", errors);
        print_json_result(exp_id, status_str, reason, transport_name(requested),
                          transport_name(selected), "single_pair_rtt", "round_trip_rtt",
                          size, 1, 1, trial, warmup, count, completed, errors,
                          elapsed_ns, &stats, &om);
        return (errors == 0) ? EXIT_PASS : EXIT_FAIL;
    }

    /* Concurrency or unidirectional one-way pipeline */
    const char *wname = (workload == WORKLOAD_UNIDIRECTIONAL) ? "unidirectional_stream" : "concurrency_pipeline";
    if (workload == WORKLOAD_UNIDIRECTIONAL && (producers != 1 || consumers != 1)) {
        snprintf(reason, sizeof(reason), "unidirectional requires 1P/1C");
        return EXIT_INVALID;
    }

    struct rusage sb, cb, sa, ca;
    getrusage(RUSAGE_SELF, &sb);
    getrusage(RUSAGE_CHILDREN, &cb);
    uint64_t wall0 = monotonic_ns();
    int exit_code = run_concurrency_workload(selected, size, count, producers, consumers,
                                             cpu_producer, cpu_consumer,
                                             &elapsed_ns, &completed, &errors,
                                             reason, sizeof(reason));
    uint64_t wall1 = monotonic_ns();
    getrusage(RUSAGE_SELF, &sa);
    getrusage(RUSAGE_CHILDREN, &ca);
    double proc_wall_s = (wall1 >= wall0) ? ((double)(wall1 - wall0) / 1e9) : 0.0;
    compute_os_metrics(&sb, &cb, &sa, &ca, proc_wall_s, completed, &om);

    const char *status_str = (exit_code == EXIT_PASS) ? "PASS"
                           : (exit_code == EXIT_UNSUPPORTED) ? "UNSUPPORTED"
                           : (exit_code == EXIT_BLOCKED) ? "BLOCKED" : "FAIL";
    print_json_result(exp_id, status_str, reason, transport_name(requested),
                      transport_name(selected), wname, "one_way_pipeline",
                      size, producers, consumers, trial, 0, count, completed, errors,
                      elapsed_ns, &stats, &om);
    return exit_code;
}

