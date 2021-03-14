UF2_FAMILY_ID = 0x00000000
# This should *NOT* cross-compile, because the goal is to run the
# resulting executable on the build machine, as a method of validating
# the generated ghostfat image.

# List of git submodules that is included as part of the UF2 version
GIT_SUBMODULES = tinyusb

include ../make.mk

# Port Compiler Flags
CFLAGS += \
  -flto \
  -DCFG_TUSB_MCU=OPT_MCU_NONE

# suppress warning caused by vendor mcu driver
CFLAGS += -Wno-error=cast-align -Wno-error=unused-parameter

LD_FILES ?=

# Port source
PORT_SRC_C += \
	$(addprefix $(CURRENT_PATH)/, $(wildcard *.c))

SRC_C += \
	$(PORT_SRC_C) \
	lib/tinyusb/src/portable/template/dcd_template.c \

SRC_S +=

# Port include
INC +=

include ../rules.mk

# TODO - modify to run the resulting binary.

# #-------------- Self-update  --------------
# SELF_CFLAGS  = $(CFLAGS) -DTINYUF2_SELF_UPDATE
# SELF_LDFLAGS = $(LDFLAGS)
# SELF_LD_FILES ?= $(LD_FILES)
# SELF_ASFLAGS = $(ASFLAGS)

# include ../self_update.mk

# # self-update uf2 file
# $(SELF_BUILD_OBJ)/$(SELF_OUTNAME).uf2: $(SELF_BUILD_OBJ)/$(SELF_OUTNAME).hex
# 	@echo CREATE $@
# 	$(PYTHON3) $(TOP)/lib/uf2/utils/uf2conv.py -f $(UF2_FAMILY_ID) -c -o $@ $^

# $(SELF_BUILD_OBJ)/$(SELF_OUTNAME).hex: $(SELF_BUILD_OBJ)/$(SELF_OUTNAME).elf
# 	@echo CREATE $@
# 	@$(OBJCOPY) -O ihex $^ $@

# # required for self-update elf compile
# $(SELF_BUILD_OBJ)/self_update/$(OUTNAME).c:
# 	@echo "const unsigned long bindata_len = 1;" > $@
# 	@echo "const unsigned char bindata[] __attribute__((aligned(16))) = { 0 };" >> $@
# 	#$(PYTHON3) $(TOP)/lib/uf2/utils/uf2conv.py --carray $^ -o $@
