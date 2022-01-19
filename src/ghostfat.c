/*
 * The MIT License (MIT)
 *
 * Copyright (c) Microsoft Corporation
 * Copyright (c) Ha Thach for Adafruit Industries
 * Copyright (c) Henry Gabryjelski
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

#include <string.h>
#include <stdio.h>
#include <assert.h>

#include "compile_date.h"
#include "board_api.h"
#include "uf2.h"

//--------------------------------------------------------------------+
//
//--------------------------------------------------------------------+

#define STATIC_ASSERT(_exp) _Static_assert(_exp, "static assert failed")

#define STR0(x) #x
#define STR(x) STR0(x)

#define UF2_ARRAY_SIZE(_arr)    ( sizeof(_arr) / sizeof(_arr[0]) )
#define UF2_DIV_CEIL(_v, _d)    ( ((_v) + (_d) - 1) / (_d) )

typedef struct {
    uint8_t JumpInstruction[3];
    uint8_t OEMInfo[8];
    uint16_t SectorSize;
    uint8_t SectorsPerCluster;
    uint16_t ReservedSectors;
    uint8_t FATCopies;
    uint16_t RootDirectoryEntries;
    uint16_t TotalSectors16;
    uint8_t MediaDescriptor;
    uint16_t SectorsPerFAT;
    uint16_t SectorsPerTrack;
    uint16_t Heads;
    uint32_t HiddenSectors;
    uint32_t TotalSectors32;
    uint8_t PhysicalDriveNum;
    uint8_t Reserved;
    uint8_t ExtendedBootSig;
    uint32_t VolumeSerialNumber;
    uint8_t VolumeLabel[11];
    uint8_t FilesystemIdentifier[8];
} __attribute__((packed)) FAT_BootBlock;

typedef struct {
    char name[8];
    char ext[3];
    uint8_t attrs;
    uint8_t reserved;
    uint8_t createTimeFine;
    uint16_t createTime;
    uint16_t createDate;
    uint16_t lastAccessDate;
    uint16_t highStartCluster;
    uint16_t updateTime;
    uint16_t updateDate;
    uint16_t startCluster;
    uint32_t size;
} __attribute__((packed)) DirEntry;
STATIC_ASSERT(sizeof(DirEntry) == 32);

typedef struct TextFile {
  char const name[11];
  char const *content;
  uint32_t size;
}TextFile_t;


//--------------------------------------------------------------------+
//
//--------------------------------------------------------------------+

#define BPB_SECTOR_SIZE           ( 512)
#define BPB_SECTORS_PER_CLUSTER   (CFG_UF2_SECTORS_PER_CLUSTER)
#define BPB_RESERVED_SECTORS      (   1)
#define BPB_NUMBER_OF_FATS        (   2)
#define BPB_ROOT_DIR_ENTRIES      (  64)
#define BPB_TOTAL_SECTORS         CFG_UF2_NUM_BLOCKS
#define BPB_MEDIA_DESCRIPTOR_BYTE (0xF8)
#define FAT_ENTRY_SIZE            (2)
#define FAT_ENTRIES_PER_SECTOR    (BPB_SECTOR_SIZE / FAT_ENTRY_SIZE)
// NOTE: MS specification explicitly allows FAT to be larger than necessary
#define TOTAL_CLUSTERS_ROUND_UP   UF2_DIV_CEIL(BPB_TOTAL_SECTORS, BPB_SECTORS_PER_CLUSTER)
#define BPB_SECTORS_PER_FAT       UF2_DIV_CEIL(TOTAL_CLUSTERS_ROUND_UP, FAT_ENTRIES_PER_SECTOR)
#define DIRENTRIES_PER_SECTOR     (BPB_SECTOR_SIZE/sizeof(DirEntry))
#define ROOT_DIR_SECTOR_COUNT     (BPB_ROOT_DIR_ENTRIES/DIRENTRIES_PER_SECTOR)
#define BPB_BYTES_PER_CLUSTER     (BPB_SECTOR_SIZE * BPB_SECTORS_PER_CLUSTER)

STATIC_ASSERT((BPB_SECTORS_PER_CLUSTER & (BPB_SECTORS_PER_CLUSTER-1)) == 0); // sectors per cluster must be power of two
STATIC_ASSERT(BPB_SECTOR_SIZE                              ==       512); // GhostFAT does not support other sector sizes (currently)
STATIC_ASSERT(BPB_NUMBER_OF_FATS                           ==         2); // FAT highest compatibility
STATIC_ASSERT(sizeof(DirEntry)                             ==        32); // FAT requirement
STATIC_ASSERT(BPB_SECTOR_SIZE % sizeof(DirEntry)           ==         0); // FAT requirement
STATIC_ASSERT(BPB_ROOT_DIR_ENTRIES % DIRENTRIES_PER_SECTOR ==         0); // FAT requirement
STATIC_ASSERT(BPB_BYTES_PER_CLUSTER                        <= (32*1024)); // FAT requirement (64k+ has known compatibility problems)
STATIC_ASSERT(FAT_ENTRIES_PER_SECTOR                       ==       256); // FAT requirement

const char infoUf2File[] =
    "TinyUF2 Bootloader " UF2_VERSION "\r\n"
    "Model: " UF2_PRODUCT_NAME "\r\n"
    "Board-ID: " UF2_BOARD_ID "\r\n"
    "Date: " COMPILE_DATE "\r\n";

const char indexFile[] =
    "<!doctype html>\n"
    "<html>"
    "<body>"
    "<script>\n"
    "location.replace(\"" UF2_INDEX_URL "\");\n"
    "</script>"
    "</body>"
    "</html>\n";

#if TINYUF2_FAVICON
#include "favicon.h"
const char autorunFile[] = "[Autorun]\r\nIcon=FAVICON.ICO\r\n";
#endif

static TextFile_t const info[] = {
    {.name = "INFO_UF2TXT", .content = infoUf2File, .size = sizeof(infoUf2File) - 1},
    {.name = "INDEX   HTM", .content = indexFile  , .size = sizeof(indexFile  ) - 1},
#if TINYUF2_FAVICON
    {.name = "AUTORUN INF", .content = autorunFile, .size = sizeof(autorunFile) - 1},
    {.name = "FAVICON ICO", .content = (char const *) favicon_data, .size = favicon_len},
#endif
    // current.uf2 must be the last element and its content must be NULL
    {.name = "CURRENT UF2", .content = NULL       , .size = 0},
};

#define NUM_FILES          (UF2_ARRAY_SIZE(info))
#define NUM_DIRENTRIES     (NUM_FILES + 1) // Code adds volume label as first root directory entry
#define REQUIRED_ROOT_DIRECTORY_SECTORS UF2_DIV_CEIL(NUM_DIRENTRIES+1, DIRENTRIES_PER_SECTOR)

STATIC_ASSERT(ROOT_DIR_SECTOR_COUNT >= REQUIRED_ROOT_DIRECTORY_SECTORS);         // FAT requirement -- Ensures BPB reserves sufficient entries for all files
STATIC_ASSERT(NUM_DIRENTRIES < (DIRENTRIES_PER_SECTOR * ROOT_DIR_SECTOR_COUNT)); // FAT requirement -- end directory with unused entry
STATIC_ASSERT(NUM_DIRENTRIES < BPB_ROOT_DIR_ENTRIES);                            // FAT requirement -- Ensures BPB reserves sufficient entries for all files
STATIC_ASSERT(NUM_DIRENTRIES < DIRENTRIES_PER_SECTOR); // GhostFAT bug workaround -- else, code overflows buffer

#define NUM_SECTORS_IN_DATA_REGION (BPB_TOTAL_SECTORS - BPB_RESERVED_SECTORS - (BPB_NUMBER_OF_FATS * BPB_SECTORS_PER_FAT) - ROOT_DIR_SECTOR_COUNT)
#define CLUSTER_COUNT              (NUM_SECTORS_IN_DATA_REGION / BPB_SECTORS_PER_CLUSTER)

// Ensure cluster count results in a valid FAT16 volume!
STATIC_ASSERT( CLUSTER_COUNT >= 0x0FF5 && CLUSTER_COUNT < 0xFFF5 );

// Many existing FAT implementations have small (1-16) off-by-one style errors
// So, avoid being within 32 of those limits for even greater compatibility.
STATIC_ASSERT( CLUSTER_COUNT >= 0x1015 && CLUSTER_COUNT < 0xFFD5 );

#define UF2_FIRMWARE_BYTES_PER_SECTOR 256
#define UF2_SECTOR_COUNT   (_flash_size / UF2_FIRMWARE_BYTES_PER_SECTOR)
#define UF2_CLUSTER_COUNT  UF2_DIV_CEIL(UF2_SECTOR_COUNT, BPB_SECTORS_PER_CLUSTER)
#define UF2_BYTE_COUNT     (UF2_SECTOR_COUNT * BPB_SECTOR_SIZE) // always a multiple of sector size, per UF2 spec

#define UF2_FIRST_CLUSTER_NUMBER  info_cluster_start(NUM_FILES -1)
#define UF2_LAST_CLUSTER_NUMBER   (UF2_FIRST_CLUSTER_NUMBER + UF2_CLUSTER_COUNT - 1)

#define FS_START_FAT0_SECTOR      BPB_RESERVED_SECTORS
#define FS_START_FAT1_SECTOR      (FS_START_FAT0_SECTOR + BPB_SECTORS_PER_FAT)
#define FS_START_ROOTDIR_SECTOR   (FS_START_FAT1_SECTOR + BPB_SECTORS_PER_FAT)
#define FS_START_CLUSTERS_SECTOR  (FS_START_ROOTDIR_SECTOR + ROOT_DIR_SECTOR_COUNT)

//--------------------------------------------------------------------+
//
//--------------------------------------------------------------------+

static FAT_BootBlock const BootBlock = {
    .JumpInstruction      = {0xeb, 0x3c, 0x90},
    .OEMInfo              = "UF2 UF2 ",
    .SectorSize           = BPB_SECTOR_SIZE,
    .SectorsPerCluster    = BPB_SECTORS_PER_CLUSTER,
    .ReservedSectors      = BPB_RESERVED_SECTORS,
    .FATCopies            = BPB_NUMBER_OF_FATS,
    .RootDirectoryEntries = BPB_ROOT_DIR_ENTRIES,
    .TotalSectors16       = (BPB_TOTAL_SECTORS > 0xFFFF) ? 0 : BPB_TOTAL_SECTORS,
    .MediaDescriptor      = BPB_MEDIA_DESCRIPTOR_BYTE,
    .SectorsPerFAT        = BPB_SECTORS_PER_FAT,
    .SectorsPerTrack      = 1,
    .Heads                = 1,
    .TotalSectors32       = (BPB_TOTAL_SECTORS > 0xFFFF) ? BPB_TOTAL_SECTORS : 0,
    .PhysicalDriveNum     = 0x80, // to match MediaDescriptor of 0xF8
    .ExtendedBootSig      = 0x29,
    .VolumeSerialNumber   = 0x00420042,
    .VolumeLabel          = UF2_VOLUME_LABEL,
    .FilesystemIdentifier = "FAT16   ",
};

// ota0 partition size
static uint32_t _flash_size;

//--------------------------------------------------------------------+
//
//--------------------------------------------------------------------+

static inline bool is_uf2_block (UF2_Block const *bl)
{
  return (bl->magicStart0 == UF2_MAGIC_START0) &&
         (bl->magicStart1 == UF2_MAGIC_START1) &&
         (bl->magicEnd == UF2_MAGIC_END) &&
         (bl->flags & UF2_FLAG_FAMILYID) &&
         !(bl->flags & UF2_FLAG_NOFLASH);
}

// get number of clusters of a file index
static uint32_t info_cluster_count(uint32_t fid)
{
  if (info[fid].size)
  {
    return UF2_DIV_CEIL(info[fid].size, BPB_SECTOR_SIZE*BPB_SECTORS_PER_CLUSTER);
  }else
  {
    // CURRENT.UF2
    return UF2_CLUSTER_COUNT;
  }
}

// get starting cluster of a file index
static uint32_t info_cluster_start(uint32_t fid)
{
  // +2 because FAT decided first data sector would be in cluster number 2, rather than zero
  uint32_t start_cluster = 2;
  for(uint32_t i=0; i<fid; i++)
  {
    start_cluster += info_cluster_count(i);
  }
  return start_cluster;
}

// get file index where the cluster belongs to
static uint32_t info_index_of(uint32_t cluster)
{
  cluster -= 2; // first cluster data is 2

  for(uint32_t i=0; i<NUM_FILES; i++)
  {
    uint32_t count = info_cluster_count(i);
    if (cluster < count) return i;
    cluster -= count;
  }
  return NUM_FILES-1;
}

void uf2_init(void)
{
  // TODO maybe limit to application size only if possible board_flash_app_size()
  _flash_size = board_flash_size();
}

/*------------------------------------------------------------------*/
/* Read CURRENT.UF2
 *------------------------------------------------------------------*/
void padded_memcpy (char *dst, char const *src, int len)
{
  for ( int i = 0; i < len; ++i )
  {
    if ( *src ) {
      *dst = *src++;
    } else {
      *dst = ' ';
    }
    dst++;
  }
}

void uf2_read_block (uint32_t block_no, uint8_t *data)
{
  memset(data, 0, BPB_SECTOR_SIZE);
  uint32_t sectionRelativeSector = block_no;

  if ( block_no == 0 )
  {
    // Requested boot block
    memcpy(data, &BootBlock, sizeof(BootBlock));
    data[510] = 0x55;    // Always at offsets 510/511, even when BPB_SECTOR_SIZE is larger
    data[511] = 0xaa;    // Always at offsets 510/511, even when BPB_SECTOR_SIZE is larger
  }
  else if ( block_no < FS_START_ROOTDIR_SECTOR )
  {
    // Requested FAT table sector
    sectionRelativeSector -= FS_START_FAT0_SECTOR;

    // second FAT is same as the first...
    if ( sectionRelativeSector >= BPB_SECTORS_PER_FAT ) sectionRelativeSector -= BPB_SECTORS_PER_FAT;

    uint16_t* data16 = (uint16_t*) (void*) data;

    if ( sectionRelativeSector == 0 )
    {
      // first FAT entry must match BPB MediaDescriptor
      data[0] = BPB_MEDIA_DESCRIPTOR_BYTE;
      data[1] = 0xff;

      // cluster 1 is reserved
      data16[1] = 0xffff;

      // WARNING -- code presumes only one NULL .content for .UF2 file
      //            and requires it be the last element of the array
      uint32_t v = 2;
      for (uint32_t i=0; i<NUM_FILES-1; i++)
      {
        uint32_t const count = info_cluster_count(i);
        for ( uint32_t c = 0; c < count-1; c++ )
        {
          data16[v] = v+1;
          v++;
        }

        data16[v] = 0xffff; // end of file
        v++;
      }
    }

    // Generate the FAT chain for the CURRENT.UF2 "file"
    for ( uint32_t i = 0; i < FAT_ENTRIES_PER_SECTOR; ++i )
    {
      // `i` here is the sector-relative array index into this sector of the FAT
      // `v` here is the overall array index into the FAT, which corresponds to
      //     where the next cluster in the chain is stored.
      uint32_t v = (sectionRelativeSector * FAT_ENTRIES_PER_SECTOR) + i;

      if ( UF2_FIRST_CLUSTER_NUMBER <= v && v < UF2_LAST_CLUSTER_NUMBER )
      {
        data16[i] = v + 1; // contiguous file, so point to next cluster number
      }
      else if ( v == UF2_LAST_CLUSTER_NUMBER)
      {
        data16[i] = 0xffff; // end of file marker in FAT16
      }
    }
  }
  else if ( block_no < FS_START_CLUSTERS_SECTOR )
  {
    // Requested root directory sector

    sectionRelativeSector -= FS_START_ROOTDIR_SECTOR;

    DirEntry *d = (void*) data;                   // pointer to next free DirEntry this sector
    int remainingEntries = DIRENTRIES_PER_SECTOR; // remaining count of DirEntries this sector

    uint32_t startingFileIndex;

    if ( sectionRelativeSector == 0 )
    {
      // volume label first
      // volume label is first directory entry
      padded_memcpy(d->name, (char const*) BootBlock.VolumeLabel, 11);
      d->attrs = 0x28;
      d++;
      remainingEntries--;

      startingFileIndex = 0;
    }else
    {
      // -1 to account for volume label in first sector
      startingFileIndex = DIRENTRIES_PER_SECTOR * sectionRelativeSector - 1;
    }

    for ( uint32_t fileIndex = startingFileIndex;
          remainingEntries > 0 && fileIndex < NUM_FILES; // while space remains in buffer and more files to add...
          fileIndex++, d++ )
    {
      // WARNING -- code presumes all files take exactly one directory entry (no long file names!)
      uint32_t const startCluster = info_cluster_start(fileIndex);

      TextFile_t const *inf = &info[fileIndex];
      padded_memcpy(d->name, inf->name, 11);
      d->createTimeFine = COMPILE_SECONDS_INT % 2 * 100;
      d->createTime = COMPILE_DOS_TIME;
      d->createDate = COMPILE_DOS_DATE;
      d->lastAccessDate = COMPILE_DOS_DATE;
      d->highStartCluster = startCluster >> 16;
      d->updateTime = COMPILE_DOS_TIME;
      d->updateDate = COMPILE_DOS_DATE;
      d->startCluster = startCluster & 0xFFFF;
      d->size = (inf->content ? inf->size : UF2_BYTE_COUNT);
    }
  }
  else if ( block_no < BPB_TOTAL_SECTORS )
  {
    sectionRelativeSector -= FS_START_CLUSTERS_SECTOR;

    // plus 2 for first data cluster offset
    uint32_t const cluster_num = 2 + sectionRelativeSector / BPB_SECTORS_PER_CLUSTER;

    if ( cluster_num < UF2_FIRST_CLUSTER_NUMBER )
    {
      // Files that is not CURRENT.UF2
      // first data cluster == first file
      uint32_t fid = info_index_of(cluster_num);
      TextFile_t const * inf = &info[fid];

      sectionRelativeSector -= (info_cluster_start(fid)-2) * BPB_SECTORS_PER_CLUSTER;

      size_t fileContentStartOffset = sectionRelativeSector * BPB_SECTOR_SIZE;
      size_t fileContentLength = inf->size;

      // nothing to copy if already past the end of the file (only when >1 sector per cluster)
      if (fileContentLength > fileContentStartOffset) {
        // obviously, 2nd and later sectors should not copy data from the start
        const void * dataStart = (inf->content) + fileContentStartOffset;
        // limit number of bytes of data to be copied to remaining valid bytes
        size_t bytesToCopy = fileContentLength - fileContentStartOffset;
        // and further limit that to a single sector at a time
        if (bytesToCopy > BPB_SECTOR_SIZE) {
          bytesToCopy = BPB_SECTOR_SIZE;
        }
        memcpy(data, dataStart, bytesToCopy);
      }
    }
    else
    {
      // CURRENT.UF2: generate data on-the-fly
      sectionRelativeSector -= (UF2_FIRST_CLUSTER_NUMBER-2) * BPB_SECTORS_PER_CLUSTER;
      uint32_t addr = BOARD_FLASH_APP_START + (sectionRelativeSector * UF2_FIRMWARE_BYTES_PER_SECTOR);
      if ( addr < _flash_size ) // TODO abstract this out
      {
        UF2_Block *bl = (void*) data;
        bl->magicStart0 = UF2_MAGIC_START0;
        bl->magicStart1 = UF2_MAGIC_START1;
        bl->magicEnd = UF2_MAGIC_END;
        bl->blockNo = sectionRelativeSector;
        bl->numBlocks = UF2_SECTOR_COUNT;
        bl->targetAddr = addr;
        bl->payloadSize = UF2_FIRMWARE_BYTES_PER_SECTOR;
        bl->flags = UF2_FLAG_FAMILYID;
        bl->familyID = BOARD_UF2_FAMILY_ID;

        board_flash_read(addr, bl->data, bl->payloadSize);
      }
    }
  }
}

/*------------------------------------------------------------------*/
/* Write UF2
 *------------------------------------------------------------------*/

/**
 * Write an uf2 block wrapped by 512 sector.
 * @return number of bytes processed, only 3 following values
 *  -1 : if not an uf2 block
 * 512 : write is successful (BPB_SECTOR_SIZE == 512)
 *   0 : is busy with flashing, tinyusb stack will call write_block again with the same parameters later on
 */
int uf2_write_block (uint32_t block_no, uint8_t *data, WriteState *state)
{
  (void) block_no;
  UF2_Block *bl = (void*) data;

  if ( !is_uf2_block(bl) ) return -1;

  if (bl->familyID == BOARD_UF2_FAMILY_ID)
  {
    // generic family ID
    board_flash_write(bl->targetAddr, bl->data, bl->payloadSize);
  }else
  {
    // TODO family matches VID/PID
    return -1;
  }

  //------------- Update written blocks -------------//
  if ( bl->numBlocks )
  {
    // Update state num blocks if needed
    if ( state->numBlocks != bl->numBlocks )
    {
      if ( bl->numBlocks >= MAX_BLOCKS || state->numBlocks )
        state->numBlocks = 0xffffffff;
      else
        state->numBlocks = bl->numBlocks;
    }

    if ( bl->blockNo < MAX_BLOCKS )
    {
      uint8_t const mask = 1 << (bl->blockNo % 8);
      uint32_t const pos = bl->blockNo / 8;

      // only increase written number with new write (possibly prevent overwriting from OS)
      if ( !(state->writtenMask[pos] & mask) )
      {
        state->writtenMask[pos] |= mask;
        state->numWritten++;
      }

      // flush last blocks
      // TODO numWritten can be smaller than numBlocks if return early
      if ( state->numWritten >= state->numBlocks )
      {
        board_flash_flush();
      }
    }
  }

  return BPB_SECTOR_SIZE;
}
