UF2_FAMILY_ID = 0x00000000

# This should *NOT* cross-compile, because the goal is to run the
# resulting executable on the build machine, as a method of validating
# the generated ghostfat image.
CROSS_COMPILE = 

# List of git submodules that is included as part of the UF2 version
GIT_SUBMODULES = tinyusb

# Define this before including parent make.mk
BUILD_APPLICATION = 1
BUILD_NO_TINYUSB = 1
SKIP_NANOLIB = 1

include ../make.mk

# Port Compiler Flags
CFLAGS +=
LD_FILES ?=

# Port source
SRC_C += \
	src/ghostfat.c \
	$(addprefix $(CURRENT_PATH)/, $(wildcard *.c))

SRC_S +=

# Port include
INC += \
  $(TOP)/src \
  $(TOP)/$(PORT_DIR) \
  $(BOARD_DIR) \

include ../rules.mk
