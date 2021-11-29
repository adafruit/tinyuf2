# ---------------------------------------
# Common make definition for all
# ---------------------------------------

CC = $(CROSS_COMPILE)gcc
OBJCOPY = $(CROSS_COMPILE)objcopy
SIZE = $(CROSS_COMPILE)size

ifneq ($(lastword a b),b)
$(error This Makefile require make 3.81 or newer)
endif

# Set TOP to be the path to get from the current directory (where make was
# invoked) to the top of the tree. $(lastword $(MAKEFILE_LIST)) returns
# the name of this makefile relative to where make was invoked.
THIS_MAKEFILE := $(lastword $(MAKEFILE_LIST))
TOP := $(shell realpath $(THIS_MAKEFILE))
TOP := $(patsubst %/ports/make.mk,%,$(TOP))

CURRENT_PATH := $(shell realpath --relative-to=$(TOP) `pwd`)

#-------------- Handy check parameter function ------------
check_defined = \
    $(strip $(foreach 1,$1, \
    $(call __check_defined,$1,$(strip $(value 2)))))
__check_defined = \
    $(if $(value $1),, \
    $(error Undefined: $1$(if $2, ($2))))

#-------------- Select the board to build for. ------------

# PORT is default to directory name containing the Makefile
# can be set manually by custom build such as flash_nuke
PORT ?= $(notdir $(shell pwd))
PORT_DIR = ports/$(PORT)

# BOARD must be set manually. BOARD_DIR can be set by a custom build to
# an absolute path or relative to where make was invoked.
ifeq ($(BOARD),)
  $(info You must provide a BOARD parameter with 'BOARD=')
  $(error No BOARD specified)
endif
BOARD_DIR ?= $(TOP)/$(PORT_DIR)/boards/$(BOARD)
ifeq ($(wildcard $(BOARD_DIR)/),)
  $(info Check your BOARD parameter and optionally provide BOARD_DIR)
  $(error Cannot find board directory)
endif

# Fetch submodules depended by family
fetch_submodule_if_empty = $(if $(wildcard $(TOP)/lib/$1/*),,$(info $(shell git -C $(TOP)/lib submodule update --init $1)))
ifdef GIT_SUBMODULES
  $(foreach s,$(GIT_SUBMODULES),$(call fetch_submodule_if_empty,$(s)))
endif

# Build directory
BUILD = _build/$(BOARD)
BIN = $(TOP)/$(PORT_DIR)/_bin/$(BOARD)

# can be set manually by custom build such as flash_nuke
OUTNAME ?= tinyuf2-$(BOARD)

# UF2 version with git tag and submodules
GIT_VERSION := $(shell git describe --dirty --always --tags)
GIT_SUBMODULE_VERSIONS := $(shell git submodule status $(addprefix ../../lib/,$(GIT_SUBMODULES)) | cut -d" " -f3,4 | paste -s -d" " -)
GIT_SUBMODULE_VERSIONS := $(subst ../../lib/,,$(GIT_SUBMODULE_VERSIONS))

CFLAGS += \
  -DBOARD_UF2_FAMILY_ID=$(UF2_FAMILY_ID) \
  -DUF2_VERSION_BASE='"$(GIT_VERSION)"'\
  -DUF2_VERSION='"$(GIT_VERSION) - $(GIT_SUBMODULE_VERSIONS)"'

#-------------- Bootloader --------------
# skip bootloader src if building application
ifdef BUILD_APPLICATION

CFLAGS += -DBUILD_APPLICATION

else

# Bootloader src, board folder and TinyUSB stack
SRC_C += \
  $(subst $(TOP)/,,$(wildcard $(TOP)/src/*.c)) \
  $(subst $(TOP)/,,$(wildcard $(BOARD_DIR)/*.c))

# Include
INC += \
  $(TOP)/src \
  $(TOP)/$(PORT_DIR) \
  $(BOARD_DIR)

endif # BUILD_APPLICATION

#-------------- TinyUSB --------------
# skip tinyusb src if building application such as erase firmware
ifdef BUILD_NO_TINYUSB

CFLAGS += -DBUILD_NO_TINYUSB

else

TINYUSB_DIR = lib/tinyusb/src

SRC_C += \
	$(TINYUSB_DIR)/tusb.c \
	$(TINYUSB_DIR)/common/tusb_fifo.c \
	$(TINYUSB_DIR)/device/usbd.c \
	$(TINYUSB_DIR)/device/usbd_control.c \
	$(TINYUSB_DIR)/class/cdc/cdc_device.c \
	$(TINYUSB_DIR)/class/dfu/dfu_rt_device.c \
	$(TINYUSB_DIR)/class/hid/hid_device.c \
	$(TINYUSB_DIR)/class/midi/midi_device.c \
	$(TINYUSB_DIR)/class/msc/msc_device.c \
	$(TINYUSB_DIR)/class/net/net_device.c \
	$(TINYUSB_DIR)/class/usbtmc/usbtmc_device.c \
	$(TINYUSB_DIR)/class/vendor/vendor_device.c

INC += $(TOP)/$(TINYUSB_DIR)

endif # BUILD_NO_TINYUSB

#-------------- Debug & Log --------------

# Debugging
ifeq ($(DEBUG), 1)
  CFLAGS += -Og
else
  CFLAGS += -Os
endif

# Log level is mapped to TUSB DEBUG option
LOG ?= 0
CFLAGS += -DTUF2_LOG=$(LOG) -DCFG_TUSB_DEBUG=$(LOG)

# Logger: default is uart, can be set to rtt or swo
ifeq ($(LOGGER),rtt)
  RTT_SRC = lib/SEGGER_RTT
  CFLAGS += -DLOGGER_RTT -DSEGGER_RTT_MODE_DEFAULT=SEGGER_RTT_MODE_BLOCK_IF_FIFO_FULL
  INC   += $(TOP)/$(RTT_SRC)/RTT
  SRC_C += $(RTT_SRC)/RTT/SEGGER_RTT.c
else ifeq ($(LOGGER),swo)
  CFLAGS += -DLOGGER_SWO
endif

#-------------- Common Compiler Flags --------------

# Compiler Flags
CFLAGS += \
  -ggdb \
  -fdata-sections \
  -ffunction-sections \
  -fsingle-precision-constant \
  -fno-strict-aliasing \
  -Wdouble-promotion \
  -Wstrict-prototypes \
  -Wall \
  -Wextra \
  -Werror \
  -Wfatal-errors \
  -Werror-implicit-function-declaration \
  -Wfloat-equal \
  -Wundef \
  -Wshadow \
  -Wwrite-strings \
  -Wsign-compare \
  -Wmissing-format-attribute \
  -Wunreachable-code \
  -Wcast-align

# Linker Flags
LDFLAGS += \
	-fshort-enums \
	-Wl,-Map=$@.map \
	-Wl,-cref \
	-Wl,-gc-sections

# libc
LIBS += -lgcc -lm -lc

# nanolib
ifneq ($(SKIP_NANOLIB), 1)
  LDFLAGS += -specs=nosys.specs -specs=nano.specs
  LIBS += -lnosys
endif

# Board specific define
include $(BOARD_DIR)/board.mk
