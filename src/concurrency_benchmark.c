#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#ifndef _POSIX_C_SOURCE
#define _POSIX_C_SOURCE 200809L
#endif

#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <mqueue.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ipc.h>
#include <sys/mman.h>
#include <sys/msg.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define MAX_WORKERS 32
#define DEFAULT_PAYLOAD 64
#define DEFAULT_MESSAGES 1000

/* System V message structure */
struct sysv_conc_msg {
  long mtype; /* 1 = normal payload, 2 = sentinel/termination */
  char mtext[4096];
};

/* Shared coordination structure for M:N consumers and synchronization */
typedef struct {
  volatile uint64_t total_received;
  volatile uint64_t total_bytes_drained;
  volatile int start_flag;
  volatile int abort_flag;
} conc_shared_state_t;

static uint64_t get_time_ns(void) {
  struct timespec ts;
  if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0)
    return 0;
  return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}

/* Run concurrent System V Message Queue benchmark */
static int run_sysv_concurrency(int num_producers, int num_consumers,
                                size_t payload_size, size_t msgs_per_prod,
                                double *elapsed_ms, double *tput_msg_sec,
                                double *tput_mb_sec) {
  int msqid = -1;
  pid_t prod_pids[MAX_WORKERS];
  pid_t cons_pids[MAX_WORKERS];
  uint64_t total_expected = (uint64_t)num_producers * msgs_per_prod;
  uint64_t start_ns, end_ns;
  int i;

  /* Allocate private message queue */
  msqid = msgget(IPC_PRIVATE, IPC_CREAT | IPC_EXCL | 0600);
  if (msqid < 0) {
    perror("sysv msgget failed");
    return -1;
  }

  /* Fork consumers */
  for (i = 0; i < num_consumers; i++) {
    pid_t pid = fork();
    if (pid < 0) {
      perror("fork consumer failed");
      msgctl(msqid, IPC_RMID, NULL);
      return -1;
    }
    if (pid == 0) {
      /* Child consumer process */
      struct sysv_conc_msg msg;
      while (1) {
        ssize_t n = msgrcv(msqid, &msg, sizeof(msg.mtext), 0, 0);
        if (n < 0) {
          if (errno == EINTR)
            continue;
          _exit(1);
        }
        /* mtype 2 signals termination */
        if (msg.mtype == 2L) {
          _exit(0);
        }
      }
    }
    cons_pids[i] = pid;
  }

  /* Start timing */
  start_ns = get_time_ns();

  /* Fork producers */
  for (i = 0; i < num_producers; i++) {
    pid_t pid = fork();
    if (pid < 0) {
      perror("fork producer failed");
      msgctl(msqid, IPC_RMID, NULL);
      return -1;
    }
    if (pid == 0) {
      /* Child producer process */
      struct sysv_conc_msg msg;
      msg.mtype = 1L;
      memset(msg.mtext, 'A' + (i % 26), payload_size);
      for (size_t m = 0; m < msgs_per_prod; m++) {
        if (msgsnd(msqid, &msg, payload_size, 0) < 0) {
          _exit(1);
        }
      }
      _exit(0);
    }
    prod_pids[i] = pid;
  }

  /* Wait for all producers to finish */
  for (i = 0; i < num_producers; i++) {
    int status;
    waitpid(prod_pids[i], &status, 0);
  }

  /* Send termination sentinels (one for each consumer) */
  for (i = 0; i < num_consumers; i++) {
    struct sysv_conc_msg term;
    term.mtype = 2L;
    term.mtext[0] = '\0';
    msgsnd(msqid, &term, 1, 0);
  }

  /* Wait for all consumers to finish */
  for (i = 0; i < num_consumers; i++) {
    int status;
    waitpid(cons_pids[i], &status, 0);
  }

  end_ns = get_time_ns();
  msgctl(msqid, IPC_RMID, NULL);

  *elapsed_ms = (double)(end_ns - start_ns) / 1e6;
  double elapsed_sec = (double)(end_ns - start_ns) / 1e9;
  *tput_msg_sec =
      elapsed_sec > 0 ? ((double)total_expected / elapsed_sec) : 0.0;
  *tput_mb_sec = elapsed_sec > 0
                     ? (((double)total_expected * (double)payload_size) /
                        (1024.0 * 1024.0) / elapsed_sec)
                     : 0.0;
  return 0;
}

/* Run concurrent POSIX Message Queue benchmark */
static int run_posix_concurrency(int num_producers, int num_consumers,
                                 size_t payload_size, size_t msgs_per_prod,
                                 double *elapsed_ms, double *tput_msg_sec,
                                 double *tput_mb_sec) {
  char mq_name[64];
  mqd_t mq;
  struct mq_attr attr;
  pid_t prod_pids[MAX_WORKERS];
  pid_t cons_pids[MAX_WORKERS];
  uint64_t total_expected = (uint64_t)num_producers * msgs_per_prod;
  uint64_t start_ns, end_ns;
  int i;

  snprintf(mq_name, sizeof(mq_name), "/mini_aipc_conc_%ld", (long)getpid());

  memset(&attr, 0, sizeof(attr));
  attr.mq_maxmsg = 10;
  attr.mq_msgsize = (long)(payload_size < 128 ? 128 : payload_size);

  mq = mq_open(mq_name, O_CREAT | O_EXCL | O_RDWR, 0600, &attr);
  if (mq == (mqd_t)-1) {
    perror("posix mq_open failed");
    return -1;
  }

  /* Fork consumers */
  for (i = 0; i < num_consumers; i++) {
    pid_t pid = fork();
    if (pid < 0) {
      perror("fork consumer failed");
      mq_close(mq);
      mq_unlink(mq_name);
      return -1;
    }
    if (pid == 0) {
      unsigned char *buf = malloc(attr.mq_msgsize);
      if (!buf)
        _exit(1);
      unsigned int prio = 0;
      while (1) {
        ssize_t n = mq_receive(mq, (char *)buf, attr.mq_msgsize, &prio);
        if (n < 0) {
          if (errno == EINTR)
            continue;
          free(buf);
          _exit(1);
        }
        /* Check for sentinel byte 0xFF */
        if (n == 1 && (unsigned char)buf[0] == 0xFF) {
          free(buf);
          _exit(0);
        }
      }
    }
    cons_pids[i] = pid;
  }

  start_ns = get_time_ns();

  /* Fork producers */
  for (i = 0; i < num_producers; i++) {
    pid_t pid = fork();
    if (pid < 0) {
      perror("fork producer failed");
      mq_close(mq);
      mq_unlink(mq_name);
      return -1;
    }
    if (pid == 0) {
      unsigned char *buf = malloc(attr.mq_msgsize);
      if (!buf)
        _exit(1);
      memset(buf, 'P' + (i % 26), payload_size);
      for (size_t m = 0; m < msgs_per_prod; m++) {
        if (mq_send(mq, (const char *)buf, payload_size, 0) < 0) {
          free(buf);
          _exit(1);
        }
      }
      free(buf);
      _exit(0);
    }
    prod_pids[i] = pid;
  }

  /* Wait for all producers to finish */
  for (i = 0; i < num_producers; i++) {
    int status;
    waitpid(prod_pids[i], &status, 0);
  }

  /* Send sentinel to each consumer with priority 0 (FIFO behind remaining messages) */
  unsigned char sentinel[128];
  memset(sentinel, 0xFF, sizeof(sentinel));
  for (i = 0; i < num_consumers; i++) {
    mq_send(mq, (const char *)sentinel, 1, 0);
  }

  /* Wait for all consumers to finish */
  for (i = 0; i < num_consumers; i++) {
    int status;
    waitpid(cons_pids[i], &status, 0);
  }

  end_ns = get_time_ns();

  mq_close(mq);
  mq_unlink(mq_name);

  *elapsed_ms = (double)(end_ns - start_ns) / 1e6;
  double elapsed_sec = (double)(end_ns - start_ns) / 1e9;
  *tput_msg_sec =
      elapsed_sec > 0 ? ((double)total_expected / elapsed_sec) : 0.0;
  *tput_mb_sec = elapsed_sec > 0
                     ? (((double)total_expected * (double)payload_size) /
                        (1024.0 * 1024.0) / elapsed_sec)
                     : 0.0;
  return 0;
}

/* Run concurrent Kernel Mailbox (/dev/aipc) benchmark */
static int run_kernel_concurrency(const char *device_path, int num_producers,
                                  int num_consumers, size_t payload_size,
                                  size_t msgs_per_prod, double *elapsed_ms,
                                  double *tput_msg_sec, double *tput_mb_sec) {
  if (access(device_path, R_OK | W_OK) != 0) {
    return 77; /* BLOCKED: Device absent or permissions denied */
  }

  conc_shared_state_t *shm = mmap(NULL, sizeof(*shm), PROT_READ | PROT_WRITE,
                                  MAP_SHARED | MAP_ANONYMOUS, -1, 0);
  if (shm == MAP_FAILED) {
    perror("mmap shared state failed");
    return -1;
  }

  memset((void *)shm, 0, sizeof(*shm));
  uint64_t total_expected = (uint64_t)num_producers * msgs_per_prod;
  uint64_t total_bytes = total_expected * (uint64_t)payload_size;
  pid_t prod_pids[MAX_WORKERS];
  pid_t cons_pids[MAX_WORKERS];
  uint64_t start_ns, end_ns;
  int i;

  /* Drain any preexisting bytes in /dev/aipc */
  int drain_fd = open(device_path, O_RDONLY | O_NONBLOCK);
  if (drain_fd >= 0) {
    char junk[65536];
    while (read(drain_fd, junk, sizeof(junk)) > 0) {
    }
    close(drain_fd);
  }

  /* Fork consumers */
  for (i = 0; i < num_consumers; i++) {
    pid_t pid = fork();
    if (pid < 0) {
      munmap(shm, sizeof(*shm));
      return -1;
    }
    if (pid == 0) {
      int fd = open(device_path, O_RDONLY);
      if (fd < 0)
        _exit(1);
      unsigned char *buf = malloc(payload_size);
      if (!buf)
        _exit(1);

      while (__atomic_load_n(&shm->total_bytes_drained, __ATOMIC_RELAXED) <
                 total_bytes &&
             !__atomic_load_n(&shm->abort_flag, __ATOMIC_RELAXED)) {
        ssize_t n = read(fd, buf, payload_size);
        if (n > 0) {
          __atomic_add_fetch(&shm->total_bytes_drained, (uint64_t)n,
                             __ATOMIC_RELAXED);
          __atomic_add_fetch(&shm->total_received, 1, __ATOMIC_RELAXED);
        } else if (n < 0 && errno != EINTR && errno != EAGAIN) {
          break;
        }
      }
      free(buf);
      close(fd);
      _exit(0);
    }
    cons_pids[i] = pid;
  }

  /* Small settle time so all consumers open device and block */
  usleep(10000);

  start_ns = get_time_ns();

  /* Fork producers */
  for (i = 0; i < num_producers; i++) {
    pid_t pid = fork();
    if (pid < 0) {
      __atomic_store_n(&shm->abort_flag, 1, __ATOMIC_RELAXED);
      munmap(shm, sizeof(*shm));
      return -1;
    }
    if (pid == 0) {
      int fd = open(device_path, O_WRONLY);
      if (fd < 0)
        _exit(1);
      unsigned char *buf = malloc(payload_size);
      if (!buf)
        _exit(1);
      memset(buf, 'K' + (i % 26), payload_size);

      for (size_t m = 0; m < msgs_per_prod; m++) {
        size_t done = 0;
        while (done < payload_size) {
          ssize_t n = write(fd, buf + done, payload_size - done);
          if (n > 0)
            done += (size_t)n;
          else if (n < 0 && errno != EINTR) {
            free(buf);
            close(fd);
            _exit(1);
          }
        }
      }
      free(buf);
      close(fd);
      _exit(0);
    }
    prod_pids[i] = pid;
  }

  /* Wait for producers to complete */
  for (i = 0; i < num_producers; i++) {
    int status;
    waitpid(prod_pids[i], &status, 0);
  }

  /* Give consumers a brief moment to finish reading all bytes */
  for (int retry = 0; retry < 500; retry++) {
    if (__atomic_load_n(&shm->total_bytes_drained, __ATOMIC_RELAXED) >=
        total_bytes)
      break;
    usleep(1000);
  }
  __atomic_store_n(&shm->abort_flag, 1, __ATOMIC_RELAXED);

  /* Wake up any sleeping consumers by writing 1 byte or closing */
  int wake_fd = open(device_path, O_WRONLY | O_NONBLOCK);
  if (wake_fd >= 0) {
    char dummy = 0;
    write(wake_fd, &dummy, 1);
    close(wake_fd);
  }

  for (i = 0; i < num_consumers; i++) {
    int status;
    waitpid(cons_pids[i], &status, 0);
  }

  end_ns = get_time_ns();

  *elapsed_ms = (double)(end_ns - start_ns) / 1e6;
  double elapsed_sec = (double)(end_ns - start_ns) / 1e9;
  *tput_msg_sec =
      elapsed_sec > 0 ? ((double)total_expected / elapsed_sec) : 0.0;
  *tput_mb_sec = elapsed_sec > 0
                     ? (((double)total_expected * (double)payload_size) /
                        (1024.0 * 1024.0) / elapsed_sec)
                     : 0.0;

  munmap(shm, sizeof(*shm));
  return 0;
}

int main(int argc, char **argv) {
  const char *mode = "sysv";
  int num_producers = 1;
  int num_consumers = 1;
  size_t payload_size = DEFAULT_PAYLOAD;
  size_t count = DEFAULT_MESSAGES;
  const char *device = "/dev/aipc";
  int csv_output = 0;

  for (int i = 1; i < argc; i++) {
    if (strcmp(argv[i], "--mode") == 0 && i + 1 < argc) {
      mode = argv[++i];
    } else if (strcmp(argv[i], "--producers") == 0 && i + 1 < argc) {
      num_producers = atoi(argv[++i]);
    } else if (strcmp(argv[i], "--consumers") == 0 && i + 1 < argc) {
      num_consumers = atoi(argv[++i]);
    } else if (strcmp(argv[i], "--size") == 0 && i + 1 < argc) {
      payload_size = (size_t)strtoull(argv[++i], NULL, 10);
    } else if (strcmp(argv[i], "--count") == 0 && i + 1 < argc) {
      count = (size_t)strtoull(argv[++i], NULL, 10);
    } else if (strcmp(argv[i], "--device") == 0 && i + 1 < argc) {
      device = argv[++i];
    } else if (strcmp(argv[i], "--csv") == 0) {
      csv_output = 1;
    }
  }

  if (num_producers <= 0 || num_producers > MAX_WORKERS || num_consumers <= 0 ||
      num_consumers > MAX_WORKERS) {
    fprintf(stderr, "Error: workers must be between 1 and %d\n", MAX_WORKERS);
    return 1;
  }

  double elapsed_ms = 0.0, tput_msg_sec = 0.0, tput_mb_sec = 0.0;
  int rc = -1;

  if (strcmp(mode, "sysv") == 0) {
    rc = run_sysv_concurrency(num_producers, num_consumers, payload_size, count,
                              &elapsed_ms, &tput_msg_sec, &tput_mb_sec);
  } else if (strcmp(mode, "posix") == 0) {
    rc = run_posix_concurrency(num_producers, num_consumers, payload_size,
                               count, &elapsed_ms, &tput_msg_sec, &tput_mb_sec);
  } else if (strcmp(mode, "kernel") == 0) {
    rc = run_kernel_concurrency(device, num_producers, num_consumers,
                                payload_size, count, &elapsed_ms, &tput_msg_sec,
                                &tput_mb_sec);
  } else {
    fprintf(stderr, "Error: unsupported mode '%s'\n", mode);
    return 1;
  }

  uint64_t total_messages = (uint64_t)num_producers * count;

  if (rc == 77) {
    if (csv_output) {
      printf("%s,%d,%d,%zu,%zu,%" PRIu64
             ",0.0,0.00,0.000,BLOCKED,Device %s not available\n",
             mode, num_producers, num_consumers, payload_size, count,
             total_messages, device);
    } else {
      printf("BLOCKED: Device %s not available\n", device);
    }
    return 77;
  }

  if (rc < 0) {
    if (csv_output) {
      printf("%s,%d,%d,%zu,%zu,%" PRIu64
             ",0.0,0.00,0.000,FAILED,Execution failed\n",
             mode, num_producers, num_consumers, payload_size, count,
             total_messages);
    } else {
      printf("FAILED\n");
    }
    return 1;
  }

  if (csv_output) {
    printf("%s,%d,%d,%zu,%zu,%" PRIu64 ",%.3f,%.2f,%.3f,PASS,OK\n", mode,
           num_producers, num_consumers, payload_size, count, total_messages,
           elapsed_ms, tput_msg_sec, tput_mb_sec);
  } else {
    printf("Mode: %s | %dP:%dC | Msgs: %" PRIu64
           " | Elapsed: %.2f ms | Tput: %.1f msg/s (%.2f MB/s)\n",
           mode, num_producers, num_consumers, total_messages, elapsed_ms,
           tput_msg_sec, tput_mb_sec);
  }

  return 0;
}
