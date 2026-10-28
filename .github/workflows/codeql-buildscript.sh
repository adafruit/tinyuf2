#!/usr/bin/env bash
set -e

PORT=stm32f4
BOARD=feather_stm32f405_express
BUILD=cmake-build/codeql-$BOARD

cd "$(dirname "$0")/../.."
python3 tools/get_deps.py --board $BOARD
# CodeQL sees only the compiles it traces: an empty build dir compiles every source
rm -rf "$BUILD"
cmake -B "$BUILD" -G Ninja -DCMAKE_BUILD_TYPE=MinSizeRel -DBOARD=$BOARD -DARTIFACT_PATH="$PWD/$BUILD/_bin" ports/$PORT
cmake --build "$BUILD" --target tinyuf2
