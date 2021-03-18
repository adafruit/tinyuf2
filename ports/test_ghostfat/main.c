#include "common.h"


#ifndef __PERSISTENT_COMPILATION_DATE__
  #define __PERSISTENT_COMPILATION_DATE__ __DATE__
#endif

#ifndef __PERSISTENT_COMPILATION_TIME__
  #define __PERSISTENT_COMPILATION_TIME__ __TIME__
#endif

typedef enum {
    ERR_NONE = 0,
    ERR_SUCCESS = 0,
    ERR_INVALID_FILENAME = -1,
    ERR_CANNOT_OPEN_NEW_IMAGE_FILE = -2,
    ERR_FAILED_WRITE_FILE = -3,
    ERR_FAILED_CLOSE_FILE = -4,
    ERR_CANNOT_OPEN_KNOWN_GOOD_IMAGE_FILE = -5,
    ERR_CANNOT_SEEK_TO_FILE_END = -6,
    ERR_UNEXPECTED_NEW_FILE_SIZE = -7,
    ERR_UNEXPECTED_KNOWN_GOOD_FILE_SIZE = -8,
    ERR_FAILED_READ_DURING_COMPARE = -9,
    ERR_FILES_NOT_IDENTICAL = -10,
    ERR_CANNOT_SEEK_TO_FILE_START = -11,
    ERR_NOT_YET_IMPLEMENTED = -12,
    ERR_INTERNAL_ERROR = -13,
} ErrorType;

const char * GetErrorString(ErrorType e)
{
    if (e == ERR_SUCCESS) { return "SUCCESS"; }
    if (e == ERR_INVALID_FILENAME) { return "INVALID_FILENAME"; }
    if (e == ERR_CANNOT_OPEN_NEW_IMAGE_FILE) { return "CANNOT_OPEN_NEW_IMAGE_FILE"; }
    if (e == ERR_FAILED_WRITE_FILE) { return "FAILED_WRITE_FILE"; }
    if (e == ERR_FAILED_CLOSE_FILE) { return "FAILED_CLOSE_FILE"; }
    if (e == ERR_CANNOT_OPEN_KNOWN_GOOD_IMAGE_FILE) { return "CANNOT_OPEN_KNOWN_GOOD_IMAGE_FILE"; }
    if (e == ERR_CANNOT_SEEK_TO_FILE_END) { return "CANNOT_SEEK_TO_FILE_END"; }
    if (e == ERR_UNEXPECTED_NEW_FILE_SIZE) { return "UNEXPECTED_NEW_FILE_SIZE"; }
    if (e == ERR_UNEXPECTED_KNOWN_GOOD_FILE_SIZE) { return "UNEXPECTED_KNOWN_GOOD_FILE_SIZE"; }
    if (e == ERR_FAILED_READ_DURING_COMPARE) { return "FAILED_READ_DURING_COMPARE"; }
    if (e == ERR_FILES_NOT_IDENTICAL) { return "FILES_NOT_IDENTICAL"; }
    if (e == ERR_CANNOT_SEEK_TO_FILE_START) { return "CANNOT_SEEK_TO_FILE_START"; }
    if (e == ERR_NOT_YET_IMPLEMENTED) { return "NOT_YET_IMPLEMENTED"; }
    if (e == ERR_INTERNAL_ERROR) { return "INTERNAL_ERROR"; }
    return "Unknown error ... code update required";
}

// If the sector size changes, such as to support 4kn sectors in the generated FAT filesystem, 
// then this will need to change also.
#define GHOSTFAT_SECTOR_SIZE 512

static char const * const knownGoodFilename = "knowngood.img";
static char const * const defaultFilename = "ghostfat.img";
static uint8_t singleSectorBuffer [GHOSTFAT_SECTOR_SIZE];
static uint8_t anotherSectorBuffer[GHOSTFAT_SECTOR_SIZE];


// TODO: use gzopen() to open compressed known good image directly
int CompareDiskImages(void) {
    // open both files for binary read
    FILE * newFile = NULL;
    FILE * knownGoodFile = NULL;
    int retVal; // code must set this value

    newFile = fopen( defaultFilename, "r" );
    if (!newFile) {
        retVal = ERR_CANNOT_OPEN_NEW_IMAGE_FILE;
        goto cleanup;
    }
    // TODO: use gzopen() to open compressed file...
    knownGoodFile = fopen( knownGoodFilename, "r" );
    if (!knownGoodFile) {
        retVal = ERR_CANNOT_OPEN_KNOWN_GOOD_IMAGE_FILE;
        goto cleanup;
    }
    if (fseek(newFile, 0L, SEEK_END) || fseek(knownGoodFile, 0L, SEEK_END)) {
        retVal = ERR_CANNOT_SEEK_TO_FILE_END;
        goto cleanup;
    }

    // verify both files have same size, using method that works with GZ'd file
    long int newFileSize = ftell(newFile);
    long int knownGoodFileSize = ftell(knownGoodFile);
    long int expectedFileSize = ((long int)GHOSTFAT_SECTOR_SIZE) * CFG_UF2_NUM_BLOCKS;
    if (newFileSize != expectedFileSize) {
        retVal = ERR_UNEXPECTED_NEW_FILE_SIZE;
        goto cleanup;
    }
    if (knownGoodFileSize != expectedFileSize) {
        retVal = ERR_UNEXPECTED_KNOWN_GOOD_FILE_SIZE;
        goto cleanup;
    }

    if (fseek(newFile, 0L, SEEK_SET) || fseek(knownGoodFile, 0L, SEEK_SET)) {
        retVal = ERR_CANNOT_SEEK_TO_FILE_START;
        goto cleanup;
    }


    // loop through all sectors of both files, ensure they compare as equal
    for (uint32_t i = 0; i < CFG_UF2_NUM_BLOCKS; i++) {

        memset(singleSectorBuffer,  0xAA, GHOSTFAT_SECTOR_SIZE); // TODO: make this be random data...
        memset(anotherSectorBuffer, 0x55, GHOSTFAT_SECTOR_SIZE); // TODO: make this be random data...

        size_t read1 = fread(singleSectorBuffer,  1, GHOSTFAT_SECTOR_SIZE, newFile);
        size_t read2 = fread(anotherSectorBuffer, 1, GHOSTFAT_SECTOR_SIZE, knownGoodFile);
        if ((read1 != GHOSTFAT_SECTOR_SIZE) || (read2 != GHOSTFAT_SECTOR_SIZE)) {
            retVal = ERR_FAILED_READ_DURING_COMPARE;
            goto cleanup;
        }
        if (memcmp(singleSectorBuffer, anotherSectorBuffer, GHOSTFAT_SECTOR_SIZE)) {
            retVal = ERR_FILES_NOT_IDENTICAL;
            goto cleanup;
        }
        // else compared OK for this sector... check next
    }
    // SUCCESS!
    retVal = ERR_NONE;

cleanup:
    if (knownGoodFile) { fclose(knownGoodFile); }
    if (newFile) { fclose(newFile); }

    // verify both files are same sized
    return retVal;
}

int DumpDiskImage(void) {

    // Generally:
    // 1. Opens a file for the disk image results
    // 2. initializes UF2
    // 3. loops through each sector of the disk image:
    //    reads the sector via uf2_read_block()
    //    write the sector to the disk image file
    // 4. close the disk image file

    FILE * file = fopen( defaultFilename, "w" ); // create / overwrite existing file
    if (!file) { return ERR_CANNOT_OPEN_NEW_IMAGE_FILE; }


    // this creates an image file in the current directory
    uint32_t countOfSectors_UF2 = CFG_UF2_NUM_BLOCKS;

    for (uint32_t i = 0; i < countOfSectors_UF2; i++) {
        memset(singleSectorBuffer, 0xAA, GHOSTFAT_SECTOR_SIZE); // TODO: make this be random data...
        uf2_read_block(i, singleSectorBuffer);
        size_t written = fwrite (singleSectorBuffer, 1, GHOSTFAT_SECTOR_SIZE, file );
        if (written != GHOSTFAT_SECTOR_SIZE) {
            return ERR_FAILED_WRITE_FILE;
        }
    }

    if (fclose(file)) {
        return ERR_FAILED_CLOSE_FILE;
    }
    return ERR_NONE;
}

int test_main(void)
{
    int r;

    r = DumpDiskImage();
    if (r) { goto errorExit; }

    r = CompareDiskImages();
    if (r) { goto errorExit; }

    printf("SUCCESS!\n");
    return ERR_NONE;

errorExit:
    printf("Failed -- %s", GetErrorString(r));
    return r;
}




