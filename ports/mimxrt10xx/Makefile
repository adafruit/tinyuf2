# List of git submodules that is included as part of the UF2 version
GIT_SUBMODULES = tinyusb

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
SDP_MIMXRT1015_PID = 0x0130
SDP_MIMXRT1021_PID = 0x0130
SDP_MIMXRT1024_PID = 0x0130
SDP_MIMXRT1042_PID = 0x0135
SDP_MIMXRT1052_PID = 0x0130
SDP_MIMXRT1062_PID = 0x0135
SDP_MIMXRT1064_PID = 0x0135
SDP_MIMXRT1176_PID = 0x013d

UF2_MIMXRT1011_ADDR= 0x60000400
UF2_MIMXRT1015_ADDR= 0x60000000
UF2_MIMXRT1021_ADDR= 0x60000000
UF2_MIMXRT1024_ADDR= 0x60000000
UF2_MIMXRT1042_ADDR= 0x60000000
UF2_MIMXRT1052_ADDR= 0x60000000
UF2_MIMXRT1062_ADDR= 0x60000000
UF2_MIMXRT1064_ADDR= 0x70000000
UF2_MIMXRT1176_ADDR= 0x30000000

SDP_PID = $(SDP_$(MCU)_PID)
UF2_ADDR = $(UF2_$(MCU)_ADDR)

DBL_TAP_REG_ADDR = 0x400D410C

# extract _fcfb_origin and _ivt_origin from linker file
FCFB_ORIGIN := $(shell sed -n 's/_fcfb_origin.*\(0x.*\);/\1/p' $(TOP)/$(PORT_DIR)/linker/$(MCU)_ram.ld)
IVT_ORIGIN := $(shell sed -n 's/_ivt_origin.*\(0x.*\);/\1/p' $(TOP)/$(PORT_DIR)/linker/$(MCU)_ram.ld)

$(BUILD)/$(OUTNAME).hex: $(BUILD)/$(OUTNAME).elf
	@echo CREATE $@
	@$(OBJCOPY) -O ihex --change-addresses $$(( $(UF2_ADDR)-$(FCFB_ORIGIN) ))  $^ $@

# SDPHOST is a variable if you need to change the path
SDPHOST = sdphost

flash-sdp: $(BUILD)/$(OUTNAME).bin
	@if [ -z "$(SDPHOST)" ]; then echo SDPHOST is not found for this machine; exit 1; fi
	$(SDPHOST) -u 0x1fc9,$(SDP_PID) write-file $(FCFB_ORIGIN) $<
	$(SDPHOST) -u 0x1fc9,$(SDP_PID) jump-address $(IVT_ORIGIN)

#-------------------------- Self-update  --------------------------
# RT10xx run entire bootloader from SRAM and can directly flash
# the bootloader region without using self-update app as other port
#--------------------------------------------------------------------
self-update: $(SELF_UF2)

# self-update uf2 file
$(SELF_UF2): $(BUILD)/$(OUTNAME).bin
	@echo CREATE $@
	$(UF2CONV_PY) -f $(UF2_FAMILY_ID) -b $(UF2_ADDR) -c -o $@ $<

# flash by copying uf2
flash-uf2: $(SELF_UF2)
	@echo copying $<
	$(UF2CONV_PY) -f $(UF2_FAMILY_ID) --deploy $<
