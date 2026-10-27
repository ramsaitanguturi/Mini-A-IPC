CC := gcc
CFLAGS := -std=c11 -D_POSIX_C_SOURCE=200809L -Wall -Wextra -Wpedantic -O2 -Iinclude
LDFLAGS := -pthread -lrt
TARGET := mini-aipc
SOURCES := src/main.c src/ipc_pipe.c src/ipc_shm.c src/selector.c

.PHONY: all clean test
all: $(TARGET)

$(TARGET): $(SOURCES) include/ipc.h
	$(CC) $(CFLAGS) $(SOURCES) -o $@ $(LDFLAGS)

clean:
	rm -f $(TARGET) results/benchmark.csv

test: $(TARGET)
	./tests/test_cli.sh

bench: $(TARGET)
	./bench/run_experiments.sh
