# iMXRT10XX Load to RAM

The serial download protocol (SDP) implemented in the RT10xx ROM does not have the abilty natively load flash, so a flashloader image needs to be loaded to run from RAM.  The boot ROM supports eXecute In Place (XIP), and load to RAM images, so the same flashloader that is designed to be loaded through the serial download protocol, can also be copied into external flash to be loaded at boot.  

## Load Image Through SDP using sdphost

1. Power down RT1011 and switch to Serial Downloader Boot Type (BOOT_MODE[1:0]=01)
2. Power up RT1011 and connect USB cable
3. Load flashloader into RAM using sdphost and run with `flash-sdp` target. For example

  ```
  make BOARD=imxrt1010_evk flash-sdp
  ```

Note: flash-sdp target use `sdphost` tool which is included as pre-built binaries in the mimxrt10xx/sdphost, you may need to give it execution permission first.

## Copy Image to flash with UF2

1. Generate update UF2 file using `self-update` target
  
  ```
  make BOARD=imxrt1010_evk self-update
  ```
  
2. Get board into UF2 mode by loading the image through SDP or double pressing the reset button if it is already present in flash
3. Drag-N-Drop generated uf2 e.g `_build/imxrt1010_evk/self_obj/update-tinyuf2-imxrt1010_evk.uf2` onto `RT1010BOOT` drive.

## To Be Developed

1. Convert additonal mimxrt10xx boards to work using load-to-RAM
2. Implement bootloader version, so when the image is loaded through SDP, it will self copy to flash if there is no flashloader or an older flashloader image in flash.  It simply needs to copy itself to flash.