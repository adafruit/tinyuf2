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
    ERR_CANNOT_OPEN_FILE = -2,
    ERR_FAILED_WRITE_FILE = -3,
    ERR_FAILED_CLOSE_FILE = -4,
    ERR_INTERNAL_NO_FILENAME = -1000,

} ErrorType;

typedef struct {
    char const * filename;
} PROGRAM_OPTIONS;

// If the sector size changes, such as to support 4kn sectors in the generated FAT filesystem, 
// then this will need to change also.
#define GHOSTFAT_SECTOR_SIZE 512


static PROGRAM_OPTIONS options = {};

// currently only allows setting output filename
int ValidateArgs(int argc, char const * const * argv) {

    // ARGV[0] == program's own name ... maybe use that (minus extension) for filename default?
    // ARGV[1] == first actual program argument, which we will use as the filename


    // allow a default filename of "ghostfat.img"
    if (argc < 2) {
        static char const * const defaultFilename = "ghostfat.img";
        options.filename = defaultFilename;
        return ERR_NONE;
    }

    // argv[0] == output filename
    //   Must be of the form (ignoring whitespace):
    //      ^  [A-Za-z]{1,8}  ( \. [A-Za-z]{1,3})?   $
    //   

    bool valid = false;
    int i = 0;
    char t = 0;
    char const * filename = argv[1];

    // validate filename (not including extension, if any)
    // NOTE: does NOT check for special filenames (CON, PRN, etc.)
    for (; i < 8; i++) {
        t = filename[i];
        if ((('A' <= t) && (t <= 'Z')) ||
            (('a' <= t) && (t <= 'z')) ||
            (('0' <= t) && (t <= '9'))    ) {
            // legal, allowed character
            valid = true;
            continue;
        }
        // If not A-Za-z0-9, only allowed items are NULL or period ...
        if ((t == '.') || (t == '\0')) {
            // Note that `valid` will be true only if at least one character was already matched
            break;
        }
        // Character not allowed, and it's not the end of the filename or start of extension.
        // Definitely not valid.
        valid = false;
        break; // out of for loop
    }
    // validate file extension, if it exists
    if (valid && (t != '\0') && (argv[0][i] == '.')) {
        i++;
        valid = false; // start at invalid again ... only valid with at least one character following period
        for (int x = 0; x < 3; x++) {
            t = filename[i+x];
            if ((('A' <= t) && (t <= 'Z')) ||
                (('a' <= t) && (t <= 'z')) ||
                (('0' <= t) && (t <= '9'))    ) {
                valid = true;
                continue;
            }
            // If not A-Za-z0-9, only allowed value is NULL ...
            if (t == '\0') {
                // Note that `valid` will be true only if at least one character (in extension) was matched
                break;
            }
            // no other valid characters in file extension
            valid = false;
            break; // out of for loop
        }
    }
    if (t != '\0') {
        valid = false; // filename or extension too long ...
    }

    if (valid) {
        options.filename = filename;
    }

    return valid ? 0 : ERR_INVALID_FILENAME;
}

int DumpDiskImage(void) {
    if (!options.filename) { return ERR_INTERNAL_NO_FILENAME; }

    // Generally:
    // 1. Opens a file for the disk image results
    // 2. initializes UF2
    // 3. loops through each sector of the disk image:
    //    reads the sector via uf2_read_block()
    //    write the sector to the disk image file
    // 4. close the disk image file

    FILE * file = fopen( options.filename, "w" ); // create / overwrite existing file
    if (!file) { return ERR_CANNOT_OPEN_FILE; }

    board_init();
    board_dfu_init();
    board_flash_init();
    uf2_init();
    // tusb_init();

    // this creates an image file in the current directory
    uint8_t singleSector[GHOSTFAT_SECTOR_SIZE];
    uint32_t countOfSectors_UF2 = board_flash_size() / GHOSTFAT_SECTOR_SIZE;

    for (uint32_t i = 0; i < countOfSectors_UF2; i++) {

        uf2_read_block(i, singleSector);
        size_t written = fwrite (singleSector, 1, GHOSTFAT_SECTOR_SIZE, file );
        if (written != GHOSTFAT_SECTOR_SIZE) {
            return ERR_FAILED_WRITE_FILE;
        }
    }

    if (fclose(file)) {
        return ERR_FAILED_CLOSE_FILE;
    }
    file = 0; // don't keep stale file pointer
    return ERR_NONE;
}

int main(int argc, char **argv)
{
    int r = ValidateArgs(argc, ((char const * const *) argv) );
    if (r) { return r; }

    r = DumpDiskImage();
    if (r) { return r; }

    // TODO: compare the disk image file vs. expected data ... but EXCLUDE timestamps such as from directory entries!
    // TODO: allow overriding of DOSDATE and DOSTIME in ghostfat, to allow 100% reproducible images
    return ERR_NONE;
}


