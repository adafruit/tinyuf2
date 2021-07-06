# List of git submodules that is included as part of the UF2 version
GIT_SUBMODULES = nxp/mcux-sdk tinyusb

# For flash-pyocd-bin target
FLASH_BIN_ADDR = $(UF2_$(MCU)_WRITE_ADDR)

include ../make.mk
include port.mk

LD_FILES ?= \
  $(PORT_DIR)/linker/$(MCU)_ram.ld \
  $(PORT_DIR)/linker/memory.ld \
  $(PORT_DIR)/linker/common.ld

SRC_C += \
	$(PORT_DIR)/boards.c \
	$(PORT_DIR)/board_flash.c \
	$(PORT_DIR)/romapi_flash.c \

# include
# INC +=

include ../rules.mk

#---------------------------------------------------------
# Load to SRAM using sdphost
# Note: you may need to give the sdphost binary executable permission first.
#---------------------------------------------------------
SDP_MIMXRT1011_PID = 0x0145
SDP_MIMXRT1011_WRITE_ADDR = 0x20206400
SDP_MIMXRT1011_JUMP_ADDR  = 0x20207000
UF2_MIMXRT1011_WRITE_ADDR = 0x60000400

# RT1015, 1050 pid is also 0x0130
SDP_MIMXRT1021_PID = 0x0130
SDP_MIMXRT1021_WRITE_ADDR = 0x0400
SDP_MIMXRT1021_JUMP_ADDR  = 0x1000
UF2_MIMXRT1021_WRITE_ADDR = 0x60000400

SDP_MIMXRT1024_PID = 0x0130
SDP_MIMXRT1024_WRITE_ADDR = 0x0400
SDP_MIMXRT1024_JUMP_ADDR  = 0x1000
UF2_MIMXRT1024_WRITE_ADDR = 0x60000400

SDP_MIMXRT1062_PID = 0x0135
SDP_MIMXRT1062_WRITE_ADDR = 0x20208000
SDP_MIMXRT1062_JUMP_ADDR  = 0x20209000
UF2_MIMXRT1062_WRITE_ADDR = 0x60000000

SDP_MIMXRT1064_PID = 0x0135
SDP_MIMXRT1064_WRITE_ADDR = 0x20208000
SDP_MIMXRT1064_JUMP_ADDR  = 0x20209000
UF2_MIMXRT1064_WRITE_ADDR = 0x70000000

DBL_TAP_MAGIC_ERASE_APP = 0xf5e80ab4
DBL_TAP_REG_ADDR = 0x400D410C

ifeq ($(OS),Windows_NT)
	SDPHOST = sdphost/win/sdphost.exe
else
	UNAME_S := $(shell uname -s)
	UNAME_M := $(shell uname -m)

	ifeq ($(UNAME_S),Darwin)
		SDPHOST = sdphost/mac/sdphost
	endif

	ifeq ($(UNAME_S),Linux)
		SDPHOST_x86_64 = amd64
		SDPHOST_i386 = i386
		SDPHOST_armv7l = arm32

		SDPHOST = sdphost/linux/$(SDPHOST_$(UNAME_M))/sdphost
	endif
endif

flash-sdp: $(BUILD)/$(OUTNAME).bin
	@if [ -z "$(SDPHOST)" ]; then echo SDPHOST is not found for this machine; exit 1; fi
	$(SDPHOST) -u 0x1fc9,$(SDP_$(MCU)_PID) -- write-file $(SDP_$(MCU)_WRITE_ADDR) $<
	$(SDPHOST) -u 0x1fc9,$(SDP_$(MCU)_PID) -- jump-address $(SDP_$(MCU)_JUMP_ADDR)

# TODO write-register doesn't work
erase-app: $(BUILD)/$(OUTNAME).bin
	@if [ -z "$(SDPHOST)" ]; then echo SDPHOST is not found for this machine; exit 1; fi
	$(SDPHOST) -u 0x1fc9,$(SDP_$(MCU)_PID) -- write-register $(DBL_TAP_REG_ADDR) 32 $(DBL_TAP_MAGIC_ERASE_APP)
	$(SDPHOST) -u 0x1fc9,$(SDP_$(MCU)_PID) -- write-file $(SDP_$(MCU)_WRITE_ADDR) $<
	$(SDPHOST) -u 0x1fc9,$(SDP_$(MCU)_PID) -- jump-address $(SDP_$(MCU)_JUMP_ADDR)

#-------------------------- Self-update  --------------------------
# RT10xx run entire bootloader from SRAM and can directly flash
# the bootloader region without using self-update app as other port
#--------------------------------------------------------------------
self-update: $(SELF_UF2)

# self-update uf2 file
$(SELF_UF2): $(BUILD)/$(OUTNAME).bin
	@echo CREATE $@
	$(PYTHON3) $(TOP)/lib/uf2/utils/uf2conv.py -f $(UF2_FAMILY_ID) -b $(UF2_$(MCU)_WRITE_ADDR) -c -o $@ $<
