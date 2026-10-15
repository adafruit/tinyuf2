// SPDX-License-Identifier: MIT
#ifndef WIFI_SCAN_H_
#define WIFI_SCAN_H_

// Return valid SSID count, zero for none, or -1 for a protocol/timeout error.
int wifi_scan(void);

// Provided by main.c; services USB and the idle indicators without starting a scan.
void demo_service(void);

#endif
