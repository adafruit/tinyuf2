idf_component_register(SRCS "bootloader_start.c"
                    INCLUDE_DIRS "../../boards/${BOARD}"
                    REQUIRES bootloader bootloader_support hal)
