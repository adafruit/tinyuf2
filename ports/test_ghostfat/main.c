#include "boards.h"
#include <inttypes.h>

#ifndef COMPILE_DATE
  #error "Reproducible build requirement - COMPILE_DATE"
#endif

#ifndef COMPILE_TIME
  #error "Reproducible build requirement - COMPILE_TIME"
#endif

// If the sector size changes, such as to support 4kn sectors in the generated FAT filesystem, 
// then this will need to change also.
#define GHOSTFAT_SECTOR_SIZE 512

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

void DumpBuffer(uint64_t startingOffset, const void * sectorBuffer, uint16_t byteCount) {
    unsigned char printable[17] = {0};
    //printf("\nDumping %" PRIu16 " bytes at %p", byteCount, sectorBuffer);
    const uint8_t * tmp = sectorBuffer;
    uint16_t i = 0;
    for (; i < byteCount; i++) {
        uint16_t mod = i % 16u;
        // print offset at start of each set of 16
        if (0 == mod) {
            printf("\n%08" PRIx64 ":", startingOffset + i);
            for (int j = 0; j < 16; j++) {
                printable[j] = '.';
            }
        }
        if (8 == mod) {
            printf(" ");
        }
        // print hex version of each byte
        printf(" %02" PRIx8, *tmp);
        if ((*tmp >= 0x20) && (*tmp < 127)) {
            printable[ (i % 16) ] = *tmp;
        }
        // and print the printable characters
        if (15 == mod) {
            printf(" ");
            // print any remaining printable characters
            for (int k = 0; k < 16; k++) {
                if (0 == k % 8) {
                    printf(" ");
                }
                printf("%c", printable[k]);
            }
        }
        fflush(NULL); // for debugging
        tmp++;
    }
    if (0 != (i%16)) {
        // print any extra remaining spaces to align final characters
        uint16_t mod = i % 16u;
        int spacesRequired = (3 * (16 - mod)) + 2;
        if (i < 8) {
            spacesRequired++;
        }
        for (int j = 0; j < spacesRequired; j++) {
            printf(" ");
            fflush(NULL); // for debugging
        }
        // print any remaining printable characters
        for (int k = 0; k < mod; k++) {
            if (0 == k % 8) {
                printf(" ");
            }
            printf("%c", printable[k]);
        }

    }
    printf("\n");
}

static char const * const knownGoodFilename = "knowngood.img";
static char const * const defaultFilename = "ghostfat.img";
static uint8_t singleSectorBuffer [GHOSTFAT_SECTOR_SIZE];
static uint8_t anotherSectorBuffer[GHOSTFAT_SECTOR_SIZE];
static char const * const infoUf2FileStart =
    "TinyUF2 Bootloader ";
static char const * const infoUf2FileEnd =
    "\r\n"
    "Model: " UF2_PRODUCT_NAME "\r\n"
    "Board-ID: " UF2_BOARD_ID "\r\n"
    "Date: " COMPILE_DATE "\r\n";

bool SectorAppearsToBe_INFO_UF2(void const * sectorBuffer) {
    char const * tmp = sectorBuffer;
    size_t startStringLength = strlen(infoUf2FileStart);
    size_t endStringLength   = strlen(infoUf2FileEnd  );

    if (tmp[GHOSTFAT_SECTOR_SIZE-1] != 0) {
        // sector must end with all zeros, and must be null-terminated string
        printf("Is_INFO_UF2: sector does not end with zero byte\n");
        return false;
    }

    if (strncmp(infoUf2FileStart, tmp, startStringLength)) {
        // mismatch of the starting bytes for this sector
        printf("Is_INFO_UF2: Mismatch at start of sector\n");
        printf("Is_INFO_UF2: Expecting:\n");
        DumpBuffer(0, infoUf2FileStart, startStringLength);
        printf("Is_INFO_UF2: Actual:");
        DumpBuffer(0, sectorBuffer, startStringLength);
        printf("\n");
        return false;
    }

    // next is the UF2_VERSION, which is variable length.
    // calculate offset where ending string should begin.

    size_t bufferStringLength = strnlen(tmp, GHOSTFAT_SECTOR_SIZE); // [0..511]
    if (bufferStringLength <= startStringLength + endStringLength) {
        // not enough space to store START_STRING + UF2_VERSION + END_STRING...
        printf("Is_INFO_UF2: string in sector too small for all data\n");
        DumpBuffer(0, sectorBuffer, bufferStringLength+1);
        return false;
    }

    size_t offset = bufferStringLength - endStringLength;
    if (strncmp(infoUf2FileEnd, tmp + offset, endStringLength+1)) {
        // mismatch of the ending string for this sector
        printf("Is_INFO_UF2: mismatch at end of sector's string (starting at offset %zd)\n", offset);
        printf("Is_INFO_UF2: Expecting:\n");
        DumpBuffer(0, infoUf2FileEnd, endStringLength+1);
        printf("Is_INFO_UF2: Actual:\n");
        DumpBuffer(0, tmp+offset, endStringLength+1);
        return false;
    }

    // all bytes after strlen() must be zero
    for (int i = bufferStringLength; i < GHOSTFAT_SECTOR_SIZE; i++) {
        if (tmp[i] != 0) {
            printf("Is_INFO_UF2: sector does not end with all zeros (non-zero at offset %d)\n", i);
            return false;
        }
    }
    // all checks pass
    return true;
}
bool IdenticalDirEntriesExcludingFileSizes(void const * sector1, void const * sector2) {

    const uint16_t directoryEntrySize = 0x20;
    _Static_assert(0 == (GHOSTFAT_SECTOR_SIZE % directoryEntrySize), "GHOSTFAT_SECTOR_SIZE must be multiple of directoryEntry size" );

    // If they are both directory entry sectors,
    // then they must be identical, EXCEPT for the file size
    // Each directory entry is 0x20 bytes, and the file size
    // is stored in the last four of those bytes.
    for (uint16_t i = 0; i < GHOSTFAT_SECTOR_SIZE; i+= directoryEntrySize) {
        if (memcmp(sector1+i, sector2+i, 16)) {
            return false;
        }
    }
    // Allow exactly ONE difference in file size
    int count = 0;
    for (uint16_t i = 0; i < GHOSTFAT_SECTOR_SIZE; i+= directoryEntrySize) {
        if (memcmp(sector1+i+16, sector2+i+16, 4)) {
            count++;
        }
    }
    if (count > 1) {
        return false;
    }
    // For that ONE allowed difference in file size,
    // verify filename is "INFO_UF2.TXT"
    for (uint16_t i = 0; i < GHOSTFAT_SECTOR_SIZE; i+= directoryEntrySize) {
        if (memcmp(sector1+i+16, sector2+i+16, 4)) {
            static char const requiredBytes[11] = {
                0x49, 0x4E, 0x46, 0x4F,
                0x5F, 0x55, 0x46, 0x32,
                0x54, 0x58, 0x54
                };
            if (memcmp(sector1+i, requiredBytes, 11)) {
                return false;
            }
            if (memcmp(sector2+i, requiredBytes, 11)) {
                return false;
            }
        }
    }
    // OK, that's as good as this gets without hard-coding other assumptions
    return true;
}
bool Are_accepted_INFO_UF2_Files(void const * sector1, void const * sector2) {
    if (!SectorAppearsToBe_INFO_UF2(sector1)) {
        return false;
    }
    if (!SectorAppearsToBe_INFO_UF2(sector2)) {
        return false;
    }
    return true;
}
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

    // The commit ID is embedded within the generated file system.
    // This is not a violation of deterministic build.
    // However, it causes the following allowed changes to the file system:
    // [ ] Contents of the file INFO_UF2.TXT has variable-sized string in the middle of the content
    // [ ] Directory entry for INFO_UF2.TXT list correspondingly different file size
    // Therefore, check for (and allow) these two changes relative to the known good image
    int64_t mismatchedDirectoryEntry = -1;
    int64_t mismatchedInfoUF2Contents = -1;

    // loop through all sectors of both files, ensure they compare as equal
    for (uint32_t i = 0; i < CFG_UF2_NUM_BLOCKS; i++) {
        uint64_t fileOffset = ((uint64_t)GHOSTFAT_SECTOR_SIZE) * i;

        memset(singleSectorBuffer,  0xAA, GHOSTFAT_SECTOR_SIZE); // TODO: make this be random data...
        memset(anotherSectorBuffer, 0x55, GHOSTFAT_SECTOR_SIZE); // TODO: make this be random data...

        size_t read1 = fread(singleSectorBuffer,  1, GHOSTFAT_SECTOR_SIZE, newFile);
        size_t read2 = fread(anotherSectorBuffer, 1, GHOSTFAT_SECTOR_SIZE, knownGoodFile);
        if ((read1 != GHOSTFAT_SECTOR_SIZE) || (read2 != GHOSTFAT_SECTOR_SIZE)) {
            retVal = ERR_FAILED_READ_DURING_COMPARE;
            goto cleanup;
        }

        if (memcmp(singleSectorBuffer, anotherSectorBuffer, GHOSTFAT_SECTOR_SIZE)) {

            if ((mismatchedInfoUF2Contents == -1) && (mismatchedDirectoryEntry == -1) &&
                IdenticalDirEntriesExcludingFileSizes(singleSectorBuffer, anotherSectorBuffer)) {
                printf(
                    "INFO: Allowed differences in DirEntry for INFO_UF2 @ sector %" PRId32
                    " (byte offset 0x%" PRIx64 ")\n",
                    i, fileOffset
                    );
                // mismatched directory entry, if exists, must occur prior to mismatched UF2 contents
                mismatchedDirectoryEntry = i;
            } else if ((mismatchedInfoUF2Contents == -1) &&
                       Are_accepted_INFO_UF2_Files(singleSectorBuffer, anotherSectorBuffer)) {
                printf(
                    "INFO: Allowed differences in INFO_UF2.TXT contents @ sector %" PRId32
                    " (byte offset 0x%" PRIx64 ")\n",
                    i, fileOffset
                    );
                // once get to mismatched INFO_UF2.TXT files,
                // cannot later have mismatched directory entries 
                mismatchedDirectoryEntry = -2;
                mismatchedInfoUF2Contents = i;
            } else {
                printf("FAIL: Mismatched data at sector %" PRIu32 " (byte offset 0x%" PRIx64 ")\n", i, fileOffset);
                printf("Expected sector data:\n");
                DumpBuffer(fileOffset, anotherSectorBuffer, GHOSTFAT_SECTOR_SIZE);
                printf("Actual   sector data:\n");
                DumpBuffer(fileOffset, singleSectorBuffer,  GHOSTFAT_SECTOR_SIZE);
                retVal = ERR_FILES_NOT_IDENTICAL;
                goto cleanup;
            }
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

int main(void)
{
    int r;

    printf("initializing UF2\n"); fflush(stdout);
    uf2_init();

    printf("generating new disk image\n"); fflush(stdout);
    r = DumpDiskImage();
    if (r) { goto errorExit; }

    printf("comparing against known good disk image\n"); fflush(stdout);
    r = CompareDiskImages();
    if (r) { goto errorExit; }

    printf("PASS: Ghostfat generation validation completed successfully.\n");
    return ERR_NONE;

errorExit:
    printf("FAIL: (%d) %s\n", r, GetErrorString(r));
    return r;
}




