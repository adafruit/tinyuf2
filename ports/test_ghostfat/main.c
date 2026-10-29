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
    ERR_WRITE_BLOCK_UNEXPECTED_RESULT = -14,
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
    if (e == ERR_WRITE_BLOCK_UNEXPECTED_RESULT) { return "WRITE_BLOCK_UNEXPECTED_RESULT"; }
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

#define STRIFY(x) #x
#define X_STRIFY(x) STRIFY(x)

static char const * const knownGoodFilename = "knowngood.img";
static char const * const defaultFilename = "ghostfat.img";
static uint8_t singleSectorBuffer [GHOSTFAT_SECTOR_SIZE];
static uint8_t anotherSectorBuffer[GHOSTFAT_SECTOR_SIZE];
static char const * const infoUf2File =
    "TinyUF2 Bootloader " UF2_VERSION "\r\n"
    "Model: " UF2_PRODUCT_NAME "\r\n"
    "Board-ID: " UF2_BOARD_ID "\r\n"
    "Date: " COMPILE_DATE "\r\n"
    "Flash Size: " X_STRIFY(CFG_UF2_FLASH_SIZE) " bytes";

bool SectorAppearsToBe_INFO_UF2(void const * sectorBuffer) {
    char const * tmp = sectorBuffer;
    size_t infoLength = strlen(infoUf2File  );

    if (tmp[GHOSTFAT_SECTOR_SIZE-1] != 0) {
        // sector must end with all zeros, and must be null-terminated string
        printf("Is_INFO_UF2: sector does not end with zero byte\n");
        return false;
    }

    if (strncmp(infoUf2File, tmp, infoLength)) {
        // mismatch of the ending string for this sector
        printf("Is_INFO_UF2: mismatched\n");
        printf("Is_INFO_UF2: Expecting:\n");
        DumpBuffer(0, infoUf2File, infoLength);
        printf("Is_INFO_UF2: Actual:\n");
        DumpBuffer(0, tmp, infoLength);
        return false;
    }

    // all bytes after strlen() must be zero
    size_t bufferStringLength = strnlen(tmp, GHOSTFAT_SECTOR_SIZE); // [0..511]
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

    enum { directoryEntrySize = 0x20 };
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

_Static_assert(sizeof(UF2_Block) == GHOSTFAT_SECTOR_SIZE, "UF2 block must fill one sector");

#define TEST_UF2_NUM_BLOCKS 2
#define TEST_UF2_TARGET_ADDR(blockNo) (0x1000u + 256u * (blockNo))

static UF2_Block uf2Block;
static WriteState writeState;
static WriteState writeStateBefore;

// otherwise-valid block of a TEST_UF2_NUM_BLOCKS-block file, its data a pattern that differs per block and offset
static void MakeUf2Block(uint32_t blockNo, uint32_t payloadSize, uint32_t familyID) {
    memset(&uf2Block, 0, sizeof(uf2Block));
    uf2Block.magicStart0 = UF2_MAGIC_START0;
    uf2Block.magicStart1 = UF2_MAGIC_START1;
    uf2Block.flags       = UF2_FLAG_FAMILYID;
    uf2Block.targetAddr  = TEST_UF2_TARGET_ADDR(blockNo);
    uf2Block.payloadSize = payloadSize;
    uf2Block.blockNo     = blockNo;
    uf2Block.numBlocks   = TEST_UF2_NUM_BLOCKS;
    uf2Block.familyID    = familyID;
    uf2Block.magicEnd    = UF2_MAGIC_END;
    for (size_t i = 0; i < sizeof(uf2Block.data); i++) {
        uf2Block.data[i] = (uint8_t) (0xA5u ^ (i * 13u) ^ (blockNo * 0x5Bu));
    }
}

// a payloadSize beyond the 476-byte data field, or another family, must be rejected before flashing or touching
// the state
static int ExpectWriteRejected(uint32_t blockNo, uint32_t payloadSize, uint32_t familyID) {
    MakeUf2Block(blockNo, payloadSize, familyID);
    memcpy(&writeStateBefore, &writeState, sizeof(writeState));
    uint32_t const writes  = test_flash_write_count;
    uint32_t const flushes = test_flash_flush_count;

    int r = uf2_write_block(0, (uint8_t *) &uf2Block, &writeState);
    bool const stateChanged = (0 != memcmp(&writeStateBefore, &writeState, sizeof(writeState)));
    if ((r != -1) || (test_flash_write_count != writes) || (test_flash_flush_count != flushes) || stateChanged) {
        printf("FAIL: payloadSize 0x%08" PRIx32 " block %" PRIu32 " family 0x%08" PRIx32 ": returned %d, %" PRIu32
               " write(s), %" PRIu32 " flush(es), state %s; expected -1, no write, no flush, state unchanged\n",
               payloadSize, blockNo, familyID, r, test_flash_write_count - writes, test_flash_flush_count - flushes,
               stateChanged ? "changed" : "unchanged");
        return ERR_WRITE_BLOCK_UNEXPECTED_RESULT;
    }
    return ERR_NONE;
}

static int ExpectWriteAccepted(uint32_t blockNo, uint32_t payloadSize, uint32_t expectedFlushes) {
    MakeUf2Block(blockNo, payloadSize, BOARD_UF2_FAMILY_ID);
    uint32_t const writes  = test_flash_write_count;
    uint32_t const flushes = test_flash_flush_count;
    uint32_t const numWritten = writeState.numWritten;

    int r = uf2_write_block(0, (uint8_t *) &uf2Block, &writeState);
    bool const marked = (0 != (writeState.writtenMask[blockNo / 8] & (1u << (blockNo % 8))));
    bool const dataMatches = (0 == memcmp(test_flash_write_data, uf2Block.data, payloadSize));
    if ((r != GHOSTFAT_SECTOR_SIZE) || (test_flash_write_count != writes + 1) ||
        (test_flash_write_addr != TEST_UF2_TARGET_ADDR(blockNo)) || (test_flash_write_len != payloadSize) ||
        !dataMatches ||
        (test_flash_flush_count != flushes + expectedFlushes) || (writeState.numBlocks != TEST_UF2_NUM_BLOCKS) ||
        (writeState.numWritten != numWritten + 1) || !marked) {
        printf("FAIL: payloadSize %" PRIu32 " block %" PRIu32 ": returned %d, %" PRIu32 " write(s) last 0x%08" PRIx32
               "+%" PRIu32 " data %s, %" PRIu32 " flush(es), numBlocks %" PRIu32 ", numWritten %" PRIu32 ", %s\n",
               payloadSize, blockNo, r, test_flash_write_count - writes, test_flash_write_addr, test_flash_write_len,
               dataMatches ? "matches" : "differs",
               test_flash_flush_count - flushes, writeState.numBlocks, writeState.numWritten,
               marked ? "marked" : "not marked");
        return ERR_WRITE_BLOCK_UNEXPECTED_RESULT;
    }
    return ERR_NONE;
}

static int TestWriteBlock(void) {
    static uint32_t const oversized[] = { 477, 481, 0xFFFFFFFFu };
    uint32_t const otherFamily = BOARD_UF2_FAMILY_ID ^ 1u;
    int r;

    memset(&writeState, 0, sizeof(writeState));
    for (size_t i = 0; i < sizeof(oversized) / sizeof(oversized[0]); i++) {
        r = ExpectWriteRejected(1, oversized[i], BOARD_UF2_FAMILY_ID);
        if (r) { return r; }
    }
    r = ExpectWriteRejected(0, 256, otherFamily);
    if (r) { return r; }

    r = ExpectWriteAccepted(0, 256, 0);
    if (r) { return r; }

    // same checks with an update in progress, on the block that would complete it
    for (size_t i = 0; i < sizeof(oversized) / sizeof(oversized[0]); i++) {
        r = ExpectWriteRejected(1, oversized[i], BOARD_UF2_FAMILY_ID);
        if (r) { return r; }
    }
    r = ExpectWriteRejected(1, sizeof(uf2Block.data), otherFamily);
    if (r) { return r; }

    // last block of the file flushes
    return ExpectWriteAccepted(1, sizeof(uf2Block.data), 1);
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

    printf("testing uf2_write_block\n"); fflush(stdout);
    r = TestWriteBlock();
    if (r) { goto errorExit; }

    printf("PASS: Ghostfat generation validation completed successfully.\n");
    return ERR_NONE;

errorExit:
    printf("FAIL: (%d) %s\n", r, GetErrorString(r));
    return r;
}
