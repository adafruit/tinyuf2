/*
 * The MIT License (MIT)
 *
 * Copyright (c) 2021 Greg Steiert for NXP
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

#include "kuiic_rgb.h"
#include "fsl_common.h"
#include "fsl_port.h"
#include "fsl_tpm.h"
#include "fsl_dma.h"
#include "fsl_dmamux.h"

//--------------------------------------------------------------------+
// Variables
//--------------------------------------------------------------------+
const uint32_t DISABLED_TIMER_REG_VALUE = KUIIC_RGB_TPM_SC_STOP;
volatile bool kuiic_rgb_on;

//--------------------------------------------------------------------+
// Code
//--------------------------------------------------------------------+

// KUIIC RGB initialization
void kuiic_rgb_init(void) {
    tpm_config_t tpmConfig;
    dma_handle_t dmaHandle; /* DMA handler. */
    dma_transfer_config_t transferConfig;
    uint8_t rgb[3] = {0,0,0x80};

    /* Select timer output for LED pins */
    CLOCK_EnableClock(KUIIC_RGB_CLK_PORT);
    PORT_SetPinMux(KUIIC_RGB_BR_PORT, KUIIC_RGB_BR_PIN, KUIIC_RGB_BR_MUX);
    PORT_SetPinMux(KUIIC_RGB_GB_PORT, KUIIC_RGB_GB_PIN, KUIIC_RGB_GB_MUX);

    /* Select the clock source for the TPM counter as kCLOCK_McgIrc48MClk */
    CLOCK_SetTpmClock(1U);

    /*
     * tpmConfig.prescale = kTPM_Prescale_Divide_1;
     * tpmConfig.useGlobalTimeBase = false;
     * tpmConfig.enableDoze = false;
     * tpmConfig.enableDebugMode = false;
     * tpmConfig.enableReloadOnTrigger = false;
     * tpmConfig.enableStopOnOverflow = false;
     * tpmConfig.enableStartOnTrigger = false;
     * tpmConfig.enablePauseOnTrigger = false;
     * tpmConfig.triggerSelect = kTPM_Trigger_Select_0;
     * tpmConfig.triggerSource = kTPM_TriggerSource_External;
     */
    TPM_GetDefaultConfig(&tpmConfig);
    tpmConfig.enableDebugMode = true;
    tpmConfig.enableReloadOnTrigger = true;
    tpmConfig.enableStopOnOverflow = true;
    /* Initialize TPM module */
    TPM_Init(KUIIC_RGB_TPM, &tpmConfig);
	// clear flag, edge mode
	KUIIC_RGB_TPM->CONTROLS[KUIIC_RGB_BR_CH].CnSC = 0x28;
	KUIIC_RGB_TPM->CONTROLS[KUIIC_RGB_GB_CH].CnSC = 0x28;
    KUIIC_RGB_TPM->SC = KUIIC_RGB_TPM_SC_STOP;

    kuiic_rgb_write(rgb);

    /* Configure DMAMUX. */
    DMAMUX_Init(DMAMUX0);
    DMAMUX_SetSource(DMAMUX0, KUIIC_RGB_DMA_CHANNEL, KUIIC_RGB_DMA_SOURCE); /* Map TPM2 TOF source to channel 0 */
    DMAMUX_EnableChannel(DMAMUX0, KUIIC_RGB_DMA_CHANNEL);

    DMA_Init(DMA0);
    DMA_CreateHandle(&dmaHandle, DMA0, KUIIC_RGB_DMA_CHANNEL);
    /* enable cycle steal and enable auto disable channel request */

    DMA_PrepareTransferConfig(&transferConfig, (void *)(&DISABLED_TIMER_REG_VALUE), sizeof(uint32_t),
                        (void *)&KUIIC_RGB_TPM->SC, sizeof(uint32_t), sizeof(uint32_t),
						kDMA_AddrNoIncrement, kDMA_AddrNoIncrement);
    DMA_SubmitTransfer(&dmaHandle, &transferConfig, kDMA_NoOptions);
    /* Enable transfer. */
    DMA0->DMA[KUIIC_RGB_DMA_CHANNEL].DCR &= ~DMA_DCR_D_REQ(true);
    DMA0->DMA[KUIIC_RGB_DMA_CHANNEL].DCR |= DMA_DCR_ERQ(true) | DMA_DCR_CS(true);

}

// KUIIC RGB write function
void kuiic_rgb_write(uint8_t const rgb[]) {
  if ((rgb[0]==0)&&(rgb[1]==0)&&(rgb[2]==0)) {
    kuiic_rgb_on = false;
  } else {
    kuiic_rgb_on = true;
    uint32_t r = rgb[0] << KUIIC_RGB_BRIGHT_SHIFT;
    // avoid setting counts to zero by padding green pulse if 0
    uint32_t g = (rgb[1]>0) ? (rgb[1] << KUIIC_RGB_BRIGHT_SHIFT) : 1;
    uint32_t b = rgb[2] << KUIIC_RGB_BRIGHT_SHIFT;
	KUIIC_RGB_TPM->MOD = (r + g + b);
	KUIIC_RGB_TPM->CONTROLS[KUIIC_RGB_BR_CH].CnV = (g + b);
	KUIIC_RGB_TPM->CONTROLS[KUIIC_RGB_GB_CH].CnV = (g);
  }
}

// KUIIC RGB tick handler
// This should be called in the systick handler
// to initiate the next pulses
void kuiic_rgb_tick(void) {
  if (kuiic_rgb_on) {
    // clear DMA DONE bit
    DMA0->DMA[KUIIC_RGB_DMA_CHANNEL].DSR_BCR = DMA_DSR_BCR_DONE(true);
    // reset transfer count
    DMA0->DMA[KUIIC_RGB_DMA_CHANNEL].DSR_BCR = 4;
    // start timer
    KUIIC_RGB_TPM->SC = KUIIC_RGB_TPM_SC_GO;
  }
}
