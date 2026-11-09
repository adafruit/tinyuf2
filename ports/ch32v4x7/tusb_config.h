// SPDX-License-Identifier: MIT
#pragma once
#define CFG_TUSB_OS          OPT_OS_NONE
#define CFG_TUD_ENABLED      1
#define CFG_TUD_MAX_SPEED    OPT_MODE_HIGH_SPEED
#define TUP_RHPORT_HIGHSPEED 1
#define TUP_DCD_ENDPOINT_MAX 8
#define TUP_DCD_EDPT_CLOSE_API
#define BOARD_TUD_RHPORT 0
#define CFG_TUSB_MEM_SECTION
#define CFG_TUSB_MEM_ALIGN     __attribute__((aligned(4)))
#define CFG_TUD_ENDPOINT0_SIZE 64
#define CFG_TUD_CDC            0
#define CFG_TUD_MSC            1
#define CFG_TUD_HID            0
#define CFG_TUD_MIDI           0
#define CFG_TUD_VENDOR         0
#define CFG_TUD_MSC_BUFSIZE    4096
