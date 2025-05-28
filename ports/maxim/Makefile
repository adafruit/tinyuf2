# List of git submodules that is included as part of the UF2 version
GIT_SUBMODULES = tinyusb

include ../make.mk
include port.mk
include ../rules.mk

################################################################################
# Optional Save Log Support
################################################################################
ifeq ($(SAVELOG),1)
    TIMESTAMP := $(shell date +%Y%m%d_%H%M%S)
    LOG_SUFFIX = _$(TIMESTAMP).log
endif

################################################################################
# Self-update
################################################################################
self-update:
	@mkdir -p $(TOP)/$(PORT_DIR)/apps/self_update/logs/self-update
	@echo "Building self-update application..."
ifeq ($(SAVELOG),1)
	$(MAKE) -C $(TOP)/$(PORT_DIR)/apps/self_update uf2 2>&1 | tee $(TOP)/$(PORT_DIR)/apps/self_update/logs/self-update/self-update$(LOG_SUFFIX)
else
	$(MAKE) -C $(TOP)/$(PORT_DIR)/apps/self_update uf2
endif

self-update-clean:
	@mkdir -p $(TOP)/$(PORT_DIR)/apps/self_update/logs/self-update-clean
	@echo "Cleaning self-update application..."
ifeq ($(SAVELOG),1)
	$(MAKE) -C $(TOP)/$(PORT_DIR)/apps/self_update clean 2>&1 | tee $(TOP)/$(PORT_DIR)/apps/self_update/logs/self-update-clean/self-update-clean$(LOG_SUFFIX)
else
	$(MAKE) -C $(TOP)/$(PORT_DIR)/apps/self_update clean
endif

################################################################################
# Erase Firmware
################################################################################
erase-firmware:
	@mkdir -p $(TOP)/$(PORT_DIR)/apps/erase_firmware/logs/erase-firmware
	@echo "Building erase-firmware application..."
ifeq ($(SAVELOG),1)
	$(MAKE) -C $(TOP)/$(PORT_DIR)/apps/erase_firmware uf2 2>&1 | tee $(TOP)/$(PORT_DIR)/apps/erase_firmware/logs/erase-firmware/erase-firmware$(LOG_SUFFIX)
else
	$(MAKE) -C $(TOP)/$(PORT_DIR)/apps/erase_firmware uf2
endif

erase-firmware-clean:
	@mkdir -p $(TOP)/$(PORT_DIR)/apps/erase_firmware/logs/erase-firmware-clean
	@echo "Cleaning erase-firmware application..."
ifeq ($(SAVELOG),1)
	$(MAKE) -C $(TOP)/$(PORT_DIR)/apps/erase_firmware clean 2>&1 | tee $(TOP)/$(PORT_DIR)/apps/erase_firmware/logs/erase-firmware-clean/erase-firmware-clean$(LOG_SUFFIX)
else
	$(MAKE) -C $(TOP)/$(PORT_DIR)/apps/erase_firmware clean
endif

################################################################################
# Blinky
################################################################################
blinky:
	@mkdir -p $(TOP)/$(PORT_DIR)/apps/blinky/logs/blinky
	@echo "Building blinky application..."
ifeq ($(SAVELOG),1)
	$(MAKE) -C $(TOP)/$(PORT_DIR)/apps/blinky uf2 2>&1 | tee $(TOP)/$(PORT_DIR)/apps/blinky/logs/blinky/blinky$(LOG_SUFFIX)
else
	$(MAKE) -C $(TOP)/$(PORT_DIR)/apps/blinky uf2
endif

blinky-clean:
	@mkdir -p $(TOP)/$(PORT_DIR)/apps/blinky/logs/blinky-clean
	@echo "Cleaning blinky application..."
ifeq ($(SAVELOG),1)
	$(MAKE) -C $(TOP)/$(PORT_DIR)/apps/blinky clean 2>&1 | tee $(TOP)/$(PORT_DIR)/apps/blinky/logs/blinky-clean/blinky-clean$(LOG_SUFFIX)
else
	$(MAKE) -C $(TOP)/$(PORT_DIR)/apps/blinky clean
endif

################################################################################
# Clean Logs
################################################################################
clean-logs:
	@echo "Cleaning all log files..."
	@rm -rf $(TOP)/$(PORT_DIR)/apps/self_update/logs
	@rm -rf $(TOP)/$(PORT_DIR)/apps/erase_firmware/logs
	@rm -rf $(TOP)/$(PORT_DIR)/apps/blinky/logs
