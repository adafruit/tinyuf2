#!/usr/bin/env bash
set -e

cd ports/stm32f4
make BOARD=feather_stm32f405_express get-deps
make BOARD=feather_stm32f405_express all
