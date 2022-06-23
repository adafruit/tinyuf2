# ---------------------------------------
# Common make rules for all
# ---------------------------------------

PYTHON3 ?= python3
MKDIR = mkdir
SED = sed
CP = cp
RM = rm

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
	@$(CC) -o $@ $(LDFLAGS) $(addprefix $(LD_SCRIPT_FLAG), $(LD_FILES)) $^ -Wl,--start-group $(LIBS) -Wl,--end-group

$(BUILD)/$(OUTNAME).bin: $(BUILD)/$(OUTNAME).elf
	@echo CREATE $@
	@$(OBJCOPY) -O binary $^ $@

$(BUILD)/$(OUTNAME).hex: $(BUILD)/$(OUTNAME).elf
	@echo CREATE $@
	@$(OBJCOPY) -O ihex $^ $@

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
