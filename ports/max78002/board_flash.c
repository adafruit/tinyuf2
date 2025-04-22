/*
 * The MIT License (MIT)
 *
 * Copyright (c) 2025 Brent Kowal, Analog Devices, Inc
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */

#include "board_api.h"

// MAX MSDK Includes
#include "flc.h"
#include "gpio.h"
#include "icc.h"
#include "mxc_sys.h"
#include "mcr_regs.h"
#include "mxc_device.h"
#include "uart.h"

/**
 * Implementation Notes:
 * 1) Per the MAX32 documentation, any operation which modifies the flash
 *    contents should be wrapped with ICC Disable/Enable calls to prevent
 *    invalid cache contents.  You'll see these calls during erases and writes.
 *
 * 2) The MAX32 flash is divided up into pages of 16K which is significantly
 *    larger than the UF2 block size. This poses a problem with erasing. Rather
 *    than assuming data will be written sequentially and erasing a page the
 *    first time its touched, this buffers pages in RAM allow sequential writes
 *    to occur in RAM.
 *
 *    When a page is first buffered its entire existing contents are copied into
 *    RAM as the baseline, then overwritten by board_flash_write().  As a new
 *    page is needed, the current page is erased in flash and the entire buffer
 *    then written, and the process repeats itself copying the existing data of
 *    the new page into RAM.
 *
 *    Assuming everything is written sequentially, this should have no different
 *    impact on flash cycles than erasing first.  If things _aren't_ written
 *    sequentially, or only a partial page is written and the other page data
 *    needs to be preserved (maybe the application has some exotic setup with
 *    multiple UF2 files) this effectively simulates a byte-level read/write
 *    access of flash.
 */

// A value to use to indicate no page is buffered
#define INVALID_PAGE_ADDR    0xFFFFFFFFUL

// Current base address of the buffered page
static uint32_t page_buffer_addr = INVALID_PAGE_ADDR;

// Page buffer. uint32_t to avoid some compile recast/alignment warnings
static uint32_t page_buffer[BOARD_FLASH_PAGE_SIZE / sizeof(uint32_t)];

//--------------------------------------------------------------------+
// Flash
//--------------------------------------------------------------------+
void board_flash_init(void) {
  page_buffer_addr = INVALID_PAGE_ADDR;
}

uint32_t board_flash_size(void) {
  return BOARD_FLASH_SIZE;
}

void board_flash_read(uint32_t addr, void* buffer, uint32_t len) {
  MXC_FLC_Read(addr, buffer, len);
}

static void flash_erase_page(uint32_t page_addr) {
  MXC_ICC_Disable(MXC_ICC0);
  MXC_CRITICAL(
    MXC_FLC_PageErase(page_addr);
  )
  MXC_ICC_Enable(MXC_ICC0);
}

static void flash_prepare_page_buffer(uint32_t addr) {
  //Get the base address for the page
  uint32_t page_addr = addr & MXC_FLASH_PAGE_MASK;

  if(page_buffer_addr == page_addr) {
    //Already buffered. Nothing to do
    return;
  }

  //Flush the current page buffer if active
  board_flash_flush();
  board_flash_read(page_addr, page_buffer, BOARD_FLASH_PAGE_SIZE);
  page_buffer_addr = page_addr;
}

void board_flash_flush(void) {
  if(page_buffer_addr != INVALID_PAGE_ADDR) {
    flash_erase_page(page_buffer_addr);
    MXC_ICC_Disable(MXC_ICC0);
    MXC_CRITICAL(
        MXC_FLC_Write(page_buffer_addr, BOARD_FLASH_PAGE_SIZE, page_buffer);
    )
    MXC_ICC_Enable(MXC_ICC0);
    page_buffer_addr = INVALID_PAGE_ADDR;
  }
}


bool board_flash_write(uint32_t addr, void const* data, uint32_t len) {
  uint8_t* data_ptr = (uint8_t*)data;
  uint32_t page_offset;
  uint32_t to_write;

  //Safety checks
  TUF2_ASSERT(addr >= BOARD_FLASH_ADDR_ZERO);
  TUF2_ASSERT(addr + len <= BOARD_FLASH_ADDR_LAST);

  while(len) {
    //Make sure the correct page is buffered
    flash_prepare_page_buffer(addr);

    //How many bytes into the page are we working
    page_offset = addr - page_buffer_addr;

    //Determine how many bytes in the current page we can/should write
    to_write = TUF2_MIN(len, BOARD_FLASH_PAGE_SIZE-page_offset);

    //Write into the buffer
    memcpy(((uint8_t*)page_buffer) + page_offset, data_ptr, to_write);

    //Adjust all the pointers, addresses and lengths for the next iteration
    data_ptr += to_write;
    addr += to_write;
    len -= to_write;
  }
  return true;
}

void board_flash_erase_app(void) {
    uint32_t page;
    for(page = BOARD_FLASH_APP_START_PAGE; page < BOARD_FLASH_NUM_PAGES; page++) {
        flash_erase_page(MXC_FLASH_PAGE_ADDR(page));
    }
}

bool board_flash_protect_bootloader(bool protect) {
  // TODO implement later
  // On the MAX78002 firmware protection is done via a register write, with each
  // bit protecting a page of flash.  The only way to clear a protection bit is
  // a POR, so currently its not viable to protect the bootloader as I don't
  // think there is anyway for the bootloader to know the self-update app is the
  // one that is about about to be run.  In the future if the bootloader could
  // distinguish regular apps from self update apps, then this could be used.
  //
  // Alternately, maybe a MAGIC value that launches the app without bootloader
  // protection could be used, so the self-update app could request a reload
  // without protection.
  (void) protect;
  return false;
}



#ifdef TINYUF2_SELF_UPDATE

// Run this function out of RAM. The linker file has a .flashprog section
// to relocated this.  Rather than putting all the support SDK calls in RAM as
// well, just do the handful of register writes to clear the first application
// page and reset the device
static void __attribute__((section(".flashprog"))) erase_app_reboot_from_ram(void) {
  while(MXC_FLC0->ctrl & MXC_F_FLC_CTRL_PEND);   //Wait for busy to clear
  MXC_FLC0->clkdiv = SystemCoreClock / 1000000;  //Set up the Flash clock
  MXC_FLC0->addr = BOARD_FLASH_APP_START;        //Erase starting at the app
  MXC_FLC0->ctrl =                               //Unlock the flash to allow writing
    (MXC_FLC0->ctrl & ~MXC_F_FLC_CTRL_UNLOCK) | MXC_S_FLC_CTRL_UNLOCK_UNLOCKED;
  MXC_FLC0->ctrl =                               //Set the erase mode to page
    (MXC_FLC0->ctrl & ~MXC_F_FLC_CTRL_ERASE_CODE) | MXC_S_FLC_CTRL_ERASE_CODE_ERASEPAGE;
  MXC_FLC0->ctrl |= MXC_F_FLC_CTRL_PGE;          //Erase the page
  while(MXC_FLC0->ctrl & MXC_F_FLC_CTRL_PEND);   //Wait for busy to clear
  MXC_FLC0->ctrl =                               //Relock the flash
    (MXC_FLC0->ctrl & ~MXC_F_FLC_CTRL_UNLOCK) | MXC_S_FLC_CTRL_UNLOCK_LOCKED;
  MXC_GCR->rst0 |= MXC_F_GCR_RST0_SYS;           //Reset the device
}

void board_self_update( const uint8_t * bootloader_bin, uint32_t bootloader_len) {
  MXC_SYS_Crit_Enter(); //Disable interrupts for whole operation

  if(bootloader_len > FLASH_BOOT_SIZE) {
    TUF2_LOG1("Bootloader size too large\n");
  } else if(memcmp((uint8_t*)BOARD_FLASH_ADDR_ZERO, bootloader_bin, bootloader_len) == 0) {
    TUF2_LOG1("Bootloader matches. Skipping re-flash\n");
  } else {
  #if TINYUF2_PROTECT_BOOTLOADER
    //Note: Don't protect bootloader when done, leave that to the new bootloader
    //since it may or may not enable protection.
    board_flash_protect_bootloader(false);
  #endif
    //Use our existing functions for flashing the bootloader. Application flash
    //is still valid, so all functions are available.
    board_flash_write(BOARD_FLASH_ADDR_ZERO, bootloader_bin, bootloader_len);
    board_flash_flush();
  }

  //Invalidate this application and reboot. Must be done from RAM
  erase_app_reboot_from_ram();
}
#endif
