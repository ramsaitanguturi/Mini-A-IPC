CC := gcc
CFLAGS := -std=c11 -D_POSIX_C_SOURCE=200809L -Wall -Wextra -Wpedantic -O2 -Iinclude
LDFLAGS := -pthread -lrt
TARGET := mini-aipc
MIXED_TARGET := mini-aipc-mixed
SOURCES := src/main.c src/ipc_pipe.c src/ipc_shm.c src/selector.c

.PHONY: all clean test bench environment
all: $(TARGET) $(MIXED_TARGET)

$(TARGET): $(SOURCES) include/ipc.h
	$(CC) $(CFLAGS) $(SOURCES) -o $@ $(LDFLAGS)

$(MIXED_TARGET): src/mixed_benchmark.c include/ipc.h
	$(CC) $(CFLAGS) src/mixed_benchmark.c -o $@ $(LDFLAGS)

clean:
	rm -f $(TARGET) $(MIXED_TARGET) results/benchmark.csv results/calibration.csv results/threshold.txt results/mixed_workload.csv results/environment.txt

test: all
	bash ./tests/test_cli.sh

bench: all
	bash ./bench/run_experiments.sh

environment:
	bash ./bench/capture_environment.sh
