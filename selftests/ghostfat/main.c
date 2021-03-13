#include <stdlib.h>
#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>

#include "../../src/uf2.h"

// provides the following relevant functions:
int main(void)
{
    board_init();
    board_dfu_init();
    board_flash_init();
    uf2_init();
    // tusb_init();


    // this creates an image file in the current directory
    uint8_t singleSector[512];
    uint32_t countOfSectors_UF2 = board_flash_size() / 512;

    // TODO: open disk image file for writing (binary)
    for (uint32_t i = 0; i < countOfSectors_UF2; i++) {

        uf2_read_block(i, singleSector);
        // TODO: append the sector to the disk image file
    }
    // TODO: close the disk image file
    // TODO: compare the disk image file vs. expected data ... but EXCLUDE timestamps such as from directory entries!
    // TODO: allow overriding of DOSDATE and DOSTIME in ghostfat, to allow 100% reproducible images

}


