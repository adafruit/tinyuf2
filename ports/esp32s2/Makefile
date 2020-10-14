# Espressif IDF use CMake build system, this add wrapper target to call idf.py

.PHONY: all clean flash
.DEFAULT_GOAL := all

# Build directory
BUILD = _build/build-$(BOARD)

all:
	idf.py -B$(BUILD) -DBOARD=$(BOARD) build

clean:
	idf.py -B$(BUILD) -DBOARD=$(BOARD) clean

flash:
	idf.py -B$(BUILD) -DBOARD=$(BOARD) flash
