# ---------------------------------------
# Common make rules for all
# ---------------------------------------

CFLAGS  += $(addprefix -I,$(INC))
LDFLAGS += $(CFLAGS)
ASFLAGS += $(CFLAGS)

LD_SCRIPT_FLAG := -Wl,-T,$(TOP)/

# Verbose mode
ifeq ("$(V)","1")
$(info CFLAGS  $(CFLAGS) ) $(info )
$(info LDFLAGS $(LDFLAGS)) $(info )
$(info ASFLAGS $(ASFLAGS)) $(info )
endif

# Assembly files can be name with upper case .S, convert it to .s
SRC_S := $(SRC_S:.S=.s)

# Due to GCC LTO bug https://bugs.launchpad.net/gcc-arm-embedded/+bug/1747966
# assembly file should be placed first in linking order
BUILD_OBJ = $(BUILD)/obj
OBJ += $(addprefix $(BUILD_OBJ)/, $(SRC_S:.s=.o))
OBJ += $(addprefix $(BUILD_OBJ)/, $(SRC_C:.c=.o))

# Set all as default goal
.DEFAULT_GOAL := all
all: $(BUILD)/$(OUTNAME).bin $(BUILD)/$(OUTNAME).hex size

OBJ_DIRS = $(sort $(dir $(OBJ)))
$(OBJ): | $(OBJ_DIRS)
$(OBJ_DIRS):
	@$(MKDIR) -p $@

$(BUILD)/$(OUTNAME).elf: $(OBJ)
	@echo LINK $@
	@$(CC) -o $@ $(LDFLAGS) $(addprefix $(LD_SCRIPT_FLAG), $(LD_FILES)) $^ -Wl,--print-memory-usage -Wl,--start-group $(LIBS) -Wl,--end-group

$(BUILD)/$(OUTNAME).bin: $(BUILD)/$(OUTNAME).elf
	@echo CREATE $@
	@$(OBJCOPY) -O binary $^ $@

# skip hex rule if building bootloader for imxrt since it needs spceial rule
ifneq ($(PORT)$(BUILD_APPLICATION),mimxrt10xx)

$(BUILD)/$(OUTNAME).hex: $(BUILD)/$(OUTNAME).elf
	@echo CREATE $@
	@$(OBJCOPY) -O ihex $^ $@

endif

size: $(BUILD)/$(OUTNAME).elf
	-@echo ''
	@$(SIZE) $<
	-@echo ''

# linkermap must be install previously at https://github.com/hathach/linkermap
linkermap: $(BUILD)/$(OUTNAME).elf
	@linkermap -v $<.map

.PHONY: clean
clean:
	$(RM) -rf $(BUILD)
	$(RM) -rf $(BIN)

# get dependencies
.PHONY: get-deps
get-deps:
	$(PYTHON3) $(TOP)/tools/get_deps.py --board $(BOARD)

#-------------- Artifacts --------------
SELF_UF2 ?= apps/self_update/$(BUILD)/update-$(OUTNAME).uf2

$(BIN):
	@$(MKDIR) -p $@

copy-artifact: $(BIN)
copy-artifact: $(BUILD)/$(OUTNAME).bin $(BUILD)/$(OUTNAME).hex
	@$(CP) $(BUILD)/$(OUTNAME).bin $(BIN)
	@$(CP) $(BUILD)/$(OUTNAME).hex $(BIN)
	@if [ -f "$(SELF_UF2)" ]; then $(CP) $(SELF_UF2) $(BIN); fi

#-------------- Compile Rules --------------

# We set vpath to point to the top of the tree so that the source files
# can be located. By following this scheme, it allows a single build rule
# to be used to compile all .c files.
vpath %.c . $(TOP)
$(BUILD_OBJ)/%.o: %.c
	@echo CC $(notdir $@)
	@$(CC) $(CFLAGS) -c -MD -o $@ $<
	@# The following fixes the dependency file.
	@# See http://make.paulandlesley.org/autodep.html for details.
	@# Regex adjusted from the above to play better with Windows paths, etc.
	@$(CP) $(@:.o=.d) $(@:.o=.P); \
	  $(SED) -e 's/#.*//' -e 's/^.*:  *//' -e 's/ *\\$$//' \
	      -e '/^$$/ d' -e 's/$$/ :/' < $(@:.o=.d) >> $(@:.o=.P); \
	  $(RM) $(@:.o=.d)

# ASM sources lower case .s
vpath %.s . $(TOP)
$(BUILD_OBJ)/%.o: %.s
	@echo AS $(notdir $@)
	@$(CC) -x assembler-with-cpp $(ASFLAGS) -c -o $@ $<

# ASM sources upper case .S
vpath %.S . $(TOP)
$(BUILD_OBJ)/%.o: %.S
	@echo AS $(notdir $@)
	@$(CC) -x assembler-with-cpp $(ASFLAGS) -c -o $@ $<

# Print out the value of a make variable.
# https://stackoverflow.com/questions/16467718/how-to-print-out-a-variable-in-makefile
print-%:
	@echo $* = $($*)

#-------------------- Flash with Jlink --------------------
ifeq ($(OS),Windows_NT)
  JLINKEXE = JLink.exe
else
  JLINKEXE = JLinkExe
endif

JLINK_IF ?= swd

# Flash hex file using jlink
$(BUILD)/$(BOARD).jlink: $(BUILD)/$(OUTNAME).hex
	@echo halt > $@
	@echo r >> $@
	@echo loadfile $< >> $@
	@echo r >> $@
	@echo go >> $@
	@echo exit >> $@

flash-jlink: $(BUILD)/$(BOARD).jlink
	$(JLINKEXE) -device $(JLINK_DEVICE) -if $(JLINK_IF) -JTAGConf -1,-1 -speed auto -CommandFile $<

# Flash bin file with jlink
$(BUILD)/$(BOARD)-bin.jlink: $(BUILD)/$(OUTNAME).bin
	@echo halt > $@
	@echo r >> $@
	@echo loadfile $< $(FLASH_BIN_ADDR) >> $@
	@echo r >> $@
	@echo go >> $@
	@echo exit >> $@

flash-jlink-bin: $(BUILD)/$(BOARD)-bin.jlink
	$(JLINKEXE) -device $(JLINK_DEVICE) -if $(JLINK_IF) -JTAGConf -1,-1 -speed auto -CommandFile $<

# Erase with jlink
$(BUILD)/$(BOARD)-erase.jlink:
	@echo halt > $@
	@echo r >> $@
	@echo erase >> $@
	@echo exit >> $@

erase-jlink: $(BUILD)/$(BOARD)-erase.jlink
	$(JLINKEXE) -device $(JLINK_DEVICE) -if $(JLINK_IF) -JTAGConf -1,-1 -speed auto -CommandFile $<

#-------------------- Flash with STLink --------------------
# STM32_Programmer_CLI must be in PATH
flash-stlink: $(BUILD)/$(OUTNAME).elf
	STM32_Programmer_CLI --connect port=swd --write $< --go

erase-stlink:
	STM32_Programmer_CLI --connect port=swd --erase all

# st-flash must be in PATH
flash-stflash: $(BUILD)/$(OUTNAME).bin
	st-flash --reset --format binary write $< 0x8000000

erase-stflash:
	st-flash erase

#-------------------- Flash with pyocd --------------------

# Flash hex file using pyocd
flash-pyocd: $(BUILD)/$(OUTNAME).hex
	pyocd flash -t $(PYOCD_TARGET) $<
	pyocd reset -t $(PYOCD_TARGET)

# Flash bin file using pyocd
flash-pyocd-bin: $(BUILD)/$(OUTNAME).bin
	pyocd flash -t $(PYOCD_TARGET) -a $(FLASH_BIN_ADDR) $<
	pyocd reset -t $(PYOCD_TARGET)

erase-pyocd:
	pyocd erase -t $(PYOCD_TARGET) -c

#-------------------- Flash with dfu-util -----------------

# flash using ROM bootloader
flash-dfu-util: $(BUILD)/$(OUTNAME).bin
	dfu-util -R -a 0 --dfuse-address 0x08000000 -D $<

erase-dfu-util:
	dfu-util -R -a 0 --dfuse-address 0x08000000:mass-erase:force

# --------------- openocd-wch -----------------
# wch-linke is not supported yet in official openOCD yet. We need to either use
# 1. download openocd as part of mounriver studio http://www.mounriver.com/download or
# 2. compiled from https://github.com/hathach/riscv-openocd-wch or
#    https://github.com/dragonlock2/miscboards/blob/main/wch/SDK/riscv-openocd.tar.xz
#    with  ./configure --disable-werror --enable-wlinke --enable-ch347=no
OPENOCD_WCH ?= /home/${USER}/app/riscv-openocd-wch/src/openocd
OPENOCD_WCH_OPTION ?=
flash-openocd-wch: $(BUILD)/$(OUTNAME).elf
	$(OPENOCD_WCH) $(OPENOCD_WCH_OPTION) -c init -c halt -c "flash write_image $<" -c reset -c exit

#-------------------- Flash with uf2 -----------------
UF2CONV_PY = $(TOP)/lib/uf2/utils/uf2conv.py
flash-uf2: $(BUILD)/$(OUTNAME).uf2
	python ${UF2CONV_PY} -f ${UF2_FAMILY_ID} --deploy $^
