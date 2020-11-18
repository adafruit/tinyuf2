# ---------------------------------------
# Common make rules for all
# ---------------------------------------

# libc
LIBS += -lgcc -lm -lnosys -lc

CFLAGS += $(addprefix -I,$(INC))

# TODO Skip nanolib for MSP430
ifeq ($(BOARD), msp_exp430f5529lp)
  LDFLAGS += $(CFLAGS) -fshort-enums -Wl,-T,$(TOP)/$(LD_FILE) -Wl,-Map=$@.map -Wl,-cref -Wl,-gc-sections
else
  LDFLAGS += $(CFLAGS) -fshort-enums -Wl,-T,$(TOP)/$(LD_FILE) -Wl,-Map=$@.map -Wl,-cref -Wl,-gc-sections -specs=nosys.specs -specs=nano.specs
endif

ASFLAGS += $(CFLAGS)

# Assembly files can be name with upper case .S, convert it to .s
SRC_S := $(SRC_S:.S=.s)

# Due to GCC LTO bug https://bugs.launchpad.net/gcc-arm-embedded/+bug/1747966
# assembly file should be placed first in linking order
OBJ += $(addprefix $(BUILD)/obj/, $(SRC_S:.s=.o))
OBJ += $(addprefix $(BUILD)/obj/, $(SRC_C:.c=.o))

# Verbose mode
ifeq ("$(V)","1")
$(info CFLAGS  $(CFLAGS) ) $(info )
$(info LDFLAGS $(LDFLAGS)) $(info )
$(info ASFLAGS $(ASFLAGS)) $(info )
endif

# Set all as default goal
.DEFAULT_GOAL := all
all: $(BUILD)/tinyuf2-$(BOARD).bin $(BUILD)/tinyuf2-$(BOARD).hex size

uf2: $(BUILD)/tinyuf2-$(BOARD).uf2

OBJ_DIRS = $(sort $(dir $(OBJ)))
$(OBJ): | $(OBJ_DIRS)
$(OBJ_DIRS):
	@$(MKDIR) -p $@

$(BUILD)/tinyuf2-$(BOARD).elf: $(OBJ)
	@echo LINK $@
	@$(CC) -o $@ $(LDFLAGS) $^ -Wl,--start-group $(LIBS) -Wl,--end-group

$(BUILD)/tinyuf2-$(BOARD).bin: $(BUILD)/tinyuf2-$(BOARD).elf
	@echo CREATE $@
	@$(OBJCOPY) -O binary $^ $@

$(BUILD)/tinyuf2-$(BOARD).hex: $(BUILD)/tinyuf2-$(BOARD).elf
	@echo CREATE $@
	@$(OBJCOPY) -O ihex $^ $@

UF2_FAMILY ?= 0x00
$(BUILD)/tinyuf2-$(BOARD).uf2: $(BUILD)/tinyuf2-$(BOARD).hex
	@echo CREATE $@
	$(PYTHON) $(TOP)/tools/uf2/utils/uf2conv.py -f $(UF2_FAMILY) -c -o $@ $^

# We set vpath to point to the top of the tree so that the source files
# can be located. By following this scheme, it allows a single build rule
# to be used to compile all .c files.
vpath %.c . $(TOP)
$(BUILD)/obj/%.o: %.c
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
$(BUILD)/obj/%.o: %.s
	@echo AS $(notdir $@)
	@$(CC) -x assembler-with-cpp $(ASFLAGS) -c -o $@ $<

# ASM sources upper case .S
vpath %.S . $(TOP)
$(BUILD)/obj/%.o: %.S
	@echo AS $(notdir $@)
	@$(CC) -x assembler-with-cpp $(ASFLAGS) -c -o $@ $<

size: $(BUILD)/tinyuf2-$(BOARD).elf
	-@echo ''
	@$(SIZE) $<
	-@echo ''

.PHONY: clean
clean:
	$(RM) -rf $(BUILD)

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

$(BUILD)/$(BOARD).jlink: $(BUILD)/tinyuf2-$(BOARD).hex
	@echo halt > $@
	@echo r >> $@
	@echo loadfile $< >> $@
	@echo r >> $@
	@echo go >> $@
	@echo exit >> $@

# Flash using jlink
flash-jlink: $(BUILD)/$(BOARD).jlink
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
flash-stlink: $(BUILD)/tinyuf2-$(BOARD).elf
	STM32_Programmer_CLI --connect port=swd --write $< --go

erase-stlink:
	STM32_Programmer_CLI --connect port=swd --erase all

#-------------------- Flash with pyocd --------------------
flash-pyocd: $(BUILD)/tinyuf2-$(BOARD).hex
	pyocd flash -t $(PYOCD_TARGET) $<
	pyocd reset -t $(PYOCD_TARGET)

erase-pyocd:
	pyocd erase -t $(PYOCD_TARGET) -c
