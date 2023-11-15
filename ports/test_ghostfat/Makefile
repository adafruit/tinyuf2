UF2_FAMILY_ID = 0x00000000

# This should *NOT* cross-compile, because the goal is to run the
# resulting executable on the build machine, as a method of validating
# the generated ghostfat image.
CROSS_COMPILE =

# List of git submodules that is included as part of the UF2 version
GIT_VERSION = 0.0.0-selftest
GIT_SUBMODULE_VERSIONS = tinyusb (0.0.1-selftest)

# Define this before including parent make.mk
BUILD_APPLICATION = 1
BUILD_NO_TINYUSB = 1
SKIP_NANOLIB = 1

include ../make.mk

CFG_UF2_FLASH_SIZE ?= 0x00400000

# Fixed version for comparing
CFLAGS += \
  -DUF2_VERSION_BASE='"$(GIT_VERSION)"'\
  -DUF2_VERSION='"$(GIT_VERSION) - $(GIT_SUBMODULE_VERSIONS)"'\
  -DCFG_UF2_FLASH_SIZE=$(CFG_UF2_FLASH_SIZE) \

#LD_FILES ?=

# Port source
SRC_C += \
	src/ghostfat.c \
	$(CURRENT_PATH)/boards.c \
	$(CURRENT_PATH)/main.c \

SRC_S +=

# Port include
INC += \
  $(TOP)/src \
  $(TOP)/src/favicon \
  $(TOP)/$(PORT_DIR) \
  $(TOP)/$(BOARD_DIR) \

include ../rules.mk

$(BUILD)/ghostfat.img: $(BUILD)/$(OUTNAME).elf
	@echo CREATE $@
	$^

mk-knowngood: $(BUILD)/ghostfat.img
	@echo Making knowngood.img
	$(CP) $^ $(BUILD)/knowngood.img
	gzip $(BUILD)/knowngood.img
	gzip --force --best $(BUILD)/knowngood.img.gz
	$(CP) -f $(BUILD)/knowngood.img.gz.gz boards/$(BOARD)/knowngood.img.gz.gz
