# TinyUF2 for STM32H7

TinyUF2 reserves 64KB like the F4 port to be compatible with existing application.

H750 boards run the application from external QSPI flash at 0x90000000. Boards with `BOARD_PFLASH_APP_EN`
(stm32h743nucleo) keep TinyUF2 in internal flash sector 0 (128KB) and run the application from internal flash at
0x08020000.

## Build

```
cmake -B build -DBOARD=stm32h743nucleo
cmake --build build
```

Make is also available:

```
make BOARD=stm32h743nucleo all
```

## Supported Boards

See the board list for this family in [supported_boards.md](../../supported_boards.md#stm32h7).
