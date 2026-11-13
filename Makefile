CC := gcc
CFLAGS := -std=c11 -D_POSIX_C_SOURCE=200809L -D_GNU_SOURCE -Wall -Wextra -Wpedantic -O2 -Iinclude
LDFLAGS := -pthread -lrt -lm
TARGET := mini-aipc
MIXED_TARGET := mini-aipc-mixed
CONCURRENCY_TARGET := mini-aipc-concurrency
AIPC_CLIENT := aipc-client
FIFO_TARGET := bin/ipc_fifo
SOURCES := src/main.c src/ipc_pipe.c src/ipc_fifo.c src/ipc_shm.c src/ipc_sysv_mq.c src/ipc_posix_mq.c src/ipc_uds.c src/selector.c src/ipc_spsc_ring.c

.PHONY: all clean test bench bench-comparative bench-unified bench-unified-quick bench-optimizations environment kernel-module kernel-clean kernel-test kernel-stress kernel-bench
all: $(TARGET) $(MIXED_TARGET) $(CONCURRENCY_TARGET) $(AIPC_CLIENT) $(FIFO_TARGET)

$(TARGET): $(SOURCES) include/ipc.h include/spsc_ring.h
	$(CC) $(CFLAGS) $(SOURCES) -o $@ $(LDFLAGS)

$(MIXED_TARGET): src/mixed_benchmark.c include/ipc.h
	$(CC) $(CFLAGS) src/mixed_benchmark.c -o $@ $(LDFLAGS)

$(CONCURRENCY_TARGET): src/concurrency_benchmark.c
	$(CC) $(CFLAGS) src/concurrency_benchmark.c -o $@ $(LDFLAGS)

$(AIPC_CLIENT): user/aipc_client.c
	$(CC) $(CFLAGS) user/aipc_client.c -o $@

$(FIFO_TARGET): src/ipc_fifo.c include/ipc.h
	@mkdir -p bin
	$(CC) $(CFLAGS) -DIPC_FIFO_STANDALONE src/ipc_fifo.c -o $@ $(LDFLAGS)

kernel-module:
	$(MAKE) -C kernel

kernel-clean:
	$(MAKE) -C kernel clean

kernel-test: $(AIPC_CLIENT)
	bash ./tests/kernel/test_device.sh

kernel-stress:
	sudo ./tests/kernel/test_load_unload.sh

kernel-bench:
	python3 ./bench/benchmark_kernel_mailbox.py

clean:
	rm -rf $(TARGET) $(MIXED_TARGET) $(CONCURRENCY_TARGET) $(AIPC_CLIENT) bin results/benchmark.csv results/calibration.csv results/threshold.txt results/mixed_workload.csv

test: all
	bash ./tests/test_cli.sh

bench: all
	bash ./bench/run_experiments.sh

bench-comparative: all
	bash ./bench/run_comparative.sh

bench-unified: all
	bash ./bench/run_unified_benchmark.sh

bench-unified-quick: all
	bash ./bench/run_unified_benchmark.sh --quick

bench-optimizations: all
	bash ./bench/run_optimization_experiments.sh

environment:
	bash ./bench/capture_environment.sh
