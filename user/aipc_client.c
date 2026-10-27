#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define DEVICE_PATH "/dev/aipc"
#define MAX_MESSAGE (1024U * 1024U)

static void usage(const char *name)
{
    fprintf(stderr,
        "Usage: %s write TEXT | read BYTES | read-exact BYTES | "
        "try-read BYTES | try-write TEXT | roundtrip TEXT\n", name);
}

static int write_all(int fd, const char *p, size_t n)
{
    while (n) {
        ssize_t w = write(fd, p, n);
        if (w < 0) { if (errno == EINTR) continue; perror("write"); return -1; }
        if (w == 0) { fprintf(stderr, "write returned zero\n"); return -1; }
        p += (size_t)w; n -= (size_t)w;
    }
    return 0;
}

static int parse_size(const char *s, size_t *out)
{
    char *end = NULL;
    unsigned long value;
    errno = 0;
    value = strtoul(s, &end, 10);
    if (errno || !s[0] || !end || *end || value == 0 || value > MAX_MESSAGE)
        return -1;
    *out = (size_t)value;
    return 0;
}

static int read_exact(int fd, char *buf, size_t wanted)
{
    size_t done = 0;
    while (done < wanted) {
        ssize_t n = read(fd, buf + done, wanted - done);
        if (n < 0) { if (errno == EINTR) continue; perror("read"); return -1; }
        if (n == 0) { fprintf(stderr, "unexpected end of stream\n"); return -1; }
        done += (size_t)n;
    }
    return 0;
}

int main(int argc, char **argv)
{
    int fd, nonblock = 0;
    const char *cmd;
    if (argc != 3) { usage(argv[0]); return 2; }
    cmd = argv[1];
    if (strcmp(cmd, "write") && strcmp(cmd, "read") &&
        strcmp(cmd, "read-exact") && strcmp(cmd, "try-read") &&
        strcmp(cmd, "try-write") && strcmp(cmd, "roundtrip")) {
        usage(argv[0]); return 2;
    }
    if (!strcmp(cmd, "try-read") || !strcmp(cmd, "try-write")) nonblock = 1;
    fd = open(DEVICE_PATH, (nonblock ? O_NONBLOCK : 0) | O_RDWR);
    if (fd < 0) { perror("open /dev/aipc"); return 1; }

    if (!strcmp(cmd, "write") || !strcmp(cmd, "try-write")) {
        if (write_all(fd, argv[2], strlen(argv[2])) < 0) { close(fd); return 1; }
    } else if (!strcmp(cmd, "read") || !strcmp(cmd, "read-exact") || !strcmp(cmd, "try-read")) {
        size_t requested;
        char *buf;
        ssize_t n;
        if (parse_size(argv[2], &requested) < 0) {
            fprintf(stderr, "read size must be 1..%u\n", MAX_MESSAGE); close(fd); return 2;
        }
        buf = malloc(requested);
        if (!buf) { perror("malloc"); close(fd); return 1; }
        if (!strcmp(cmd, "read-exact")) {
            if (read_exact(fd, buf, requested) < 0) { free(buf); close(fd); return 1; }
            n = (ssize_t)requested;
        } else {
            do { n = read(fd, buf, requested); } while (n < 0 && errno == EINTR && !nonblock);
            if (n < 0) { perror("read"); free(buf); close(fd); return 1; }
        }
        if (fwrite(buf, 1, (size_t)n, stdout) != (size_t)n) { perror("stdout"); free(buf); close(fd); return 1; }
        free(buf);
    } else {
        size_t len = strlen(argv[2]);
        char *buf = malloc(len ? len : 1);
        if (!buf) { perror("malloc"); close(fd); return 1; }
        if (write_all(fd, argv[2], len) < 0 || read_exact(fd, buf, len) < 0) {
            free(buf); close(fd); return 1;
        }
        if (memcmp(buf, argv[2], len)) {
            fprintf(stderr, "integrity mismatch: expected %zu bytes\n", len);
            free(buf); close(fd); return 1;
        }
        printf("OK: %zu bytes round-tripped\n", len);
        free(buf);
    }
    close(fd);
    return 0;
}
