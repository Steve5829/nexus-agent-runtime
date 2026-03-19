# Nexus Agent Runtime Build System

CC = gcc
CFLAGS = -Wall -Wextra -O2
PYTHON = python3
PIP = $(PYTHON) -m pip

CORE_DIR = core
SANDBOX_DIR = $(CORE_DIR)/sandbox

.PHONY: all install compile test check clean help

all: compile check

help:
	@echo "Nexus Agent Runtime Build System"
	@echo "  make install  - Install development dependencies"
	@echo "  make compile  - Compile the C sandbox launcher"
	@echo "  make test     - Run the pytest suite"
	@echo "  make check    - Compile Python files and run tests"
	@echo "  make clean    - Remove build artifacts"

install:
	@echo "[BUILD] Installing development dependencies..."
	$(PIP) install -r requirements-dev.txt

compile:
	@echo "[BUILD] Compiling C sandbox launcher..."
	$(CC) $(CFLAGS) $(SANDBOX_DIR)/sandbox.c -o $(SANDBOX_DIR)/sandbox_kernel

test:
	@echo "[TEST] Running unit tests..."
	$(PYTHON) -m pytest tests/

check:
	@echo "[CHECK] Compiling Python sources..."
	$(PYTHON) -m compileall core sdk tests
	@echo "[CHECK] Running unit tests..."
	$(PYTHON) -m pytest tests/

clean:
	@echo "[CLEAN] Removing sandbox binary..."
	rm -f $(SANDBOX_DIR)/sandbox_kernel
