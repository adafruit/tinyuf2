MCU_VARIANT = D6

LDFLAGS += \
  -Wl,--defsym=__flash_size=64K \
  -Wl,--defsym=__ram_size=20K \
