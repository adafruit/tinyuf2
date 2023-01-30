# List of git submodules that is included as part of the UF2 version
GIT_SUBMODULES = st/cmsis_device_f3 st/stm32f3xx_hal_driver tinyusb

include ../make.mk
include port.mk
include ../rules.mk

# flash using ROM bootloader
flash-dfu-util: $(BUILD)/$(OUTNAME).bin
	dfu-util -R -a 0 --dfuse-address 0x08000000 -D $<

#------------------------------------------
# Self-update
#------------------------------------------

self-update:
	@echo "not implemented yet"
