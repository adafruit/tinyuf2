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

# iMXRT self-update file is in the same BUILD folder
SELF_UF2 = $(BUILD)/update-$(OUTNAME).uf2

include ../rules.mk

#---------------------------------------------------------
# Load to SRAM using sdphost
# Note: you may need to give the sdphost binary executable permission first.
#
# SDP loads the image into the RAM locations specified in the .ld files.
#  - "SDP Write Address" must equal _fcfb_origin
#  - "SDP Jump Address" must equal _ivt_origin
#
# TinyUF2 will copy itself to the correct location in flash.
# "UF2 Write Address" shows where the image will reside in flash if you 
# want to use a tool like pyocd to write the binary into flash through SWD
# Note: The .elf file cannot be written directly to flash since the target 
# is RAM and the addresses need to be translated.
#---------------------------------------------------------
SDP_MIMXRT1011_PID = 0x0145
UF2_MIMXRT1011_WRITE_ADDR = 0x60000400

# RT1015, 1050 pid is also 0x0130
SDP_MIMXRT1021_PID = 0x0130
UF2_MIMXRT1021_WRITE_ADDR = 0x60000000

SDP_MIMXRT1024_PID = 0x0130
UF2_MIMXRT1024_WRITE_ADDR = 0x60000000

SDP_MIMXRT1062_PID = 0x0135
UF2_MIMXRT1062_WRITE_ADDR = 0x60000000

SDP_MIMXRT1064_PID = 0x0135
UF2_MIMXRT1064_WRITE_ADDR = 0x70000000

DBL_TAP_MAGIC_ERASE_APP = 0xf5e80ab4
DBL_TAP_REG_ADDR = 0x400D410C

# extract _fcfb_origin and _ivt_origin from linker file
SDP_WRITE_ADDR := $(shell sed -n 's/_fcfb_origin.*\(0x.*\);/\1/p' $(TOP)/$(PORT_DIR)/linker/$(MCU)_ram.ld)
SDP_JUMP_ADDR := $(shell sed -n 's/_ivt_origin.*\(0x.*\);/\1/p' $(TOP)/$(PORT_DIR)/linker/$(MCU)_ram.ld)
# SDPHOST is a variable if you need to change the path
SDPHOST = sdphost

flash-sdp: $(BUILD)/$(OUTNAME).bin
	@if [ -z "$(SDPHOST)" ]; then echo SDPHOST is not found for this machine; exit 1; fi
	$(SDPHOST) -u 0x1fc9,$(SDP_$(MCU)_PID) -- write-file $(SDP_WRITE_ADDR) $<
	$(SDPHOST) -u 0x1fc9,$(SDP_$(MCU)_PID) -- jump-address $(SDP_JUMP_ADDR)

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
