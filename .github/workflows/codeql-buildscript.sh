#!/usr/bin/env bash

cd ports/stm32f4
make BOARD=feather_stm32f405_express get-deps
make BOARD=feather_stm32f405_express all
