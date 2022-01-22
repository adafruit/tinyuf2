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

// use as: GF_DEBUG_PRINT(("foo %d", x));
#define DEBUG 1
#if defined(DEBUG)
  #define GF_DEBUG_PRINT(x) do { printf x; fflush(stdout); } while (0)
#else
  #define GF_DEBUG_PRINT(x)
#endif


//--------------------------------------------------------------------+
//
//--------------------------------------------------------------------+

// ota0 partition size 
static uint32_t _flash_size;

#define STATIC_ASSERT(_exp) _Static_assert(_exp, "static assert failed")

#define STR0(x) #x
#define STR(x) STR0(x)

#define UF2_ARRAY_SIZE(_arr)    ( sizeof(_arr) / sizeof(_arr[0]) )
#define UF2_DIV_CEIL(_v, _d)    ( ((_v) / (_d)) + ((_v) % (_d) ? 1 : 0)) // avoid overflow

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

typedef struct FileContent {
  char const name[11];
  void const * content;
  uint32_t   size;       // OK to use uint32_T b/c FAT32 limits filesize to (4GiB - 2)
} FileContent_t;

// ota0 partition size
static uint32_t _flash_size;

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
#define FAT_END_OF_CHAIN          (0xFFFF)

// NOTE: MS specification explicitly allows FAT to be larger than necessary
#define TOTAL_CLUSTERS_ROUND_UP   UF2_DIV_CEIL(BPB_TOTAL_SECTORS, BPB_SECTORS_PER_CLUSTER)
#define BPB_SECTORS_PER_FAT       UF2_DIV_CEIL(TOTAL_CLUSTERS_ROUND_UP, FAT_ENTRIES_PER_SECTOR)
#define DIRENTRIES_PER_SECTOR     (BPB_SECTOR_SIZE/sizeof(DirEntry))
#define ROOT_DIR_SECTOR_COUNT     UF2_DIV_CEIL(BPB_ROOT_DIR_ENTRIES, DIRENTRIES_PER_SECTOR)
#define BPB_BYTES_PER_CLUSTER     (BPB_SECTOR_SIZE * BPB_SECTORS_PER_CLUSTER)

STATIC_ASSERT((BPB_SECTORS_PER_CLUSTER & (BPB_SECTORS_PER_CLUSTER-1)) == 0); // sectors per cluster must be power of two
STATIC_ASSERT(BPB_SECTOR_SIZE                              ==       512); // GhostFAT does not support other sector sizes (currently)
STATIC_ASSERT(BPB_NUMBER_OF_FATS                           ==         2); // FAT highest compatibility
STATIC_ASSERT(sizeof(DirEntry)                             ==        32); // FAT requirement
STATIC_ASSERT(BPB_SECTOR_SIZE % sizeof(DirEntry)           ==         0); // FAT requirement
STATIC_ASSERT(BPB_ROOT_DIR_ENTRIES % DIRENTRIES_PER_SECTOR ==         0); // FAT requirement
STATIC_ASSERT(BPB_BYTES_PER_CLUSTER                        <= (32*1024)); // FAT requirement (64k+ has known compatibility problems)
STATIC_ASSERT(FAT_ENTRIES_PER_SECTOR                       ==       256); // FAT requirement

#define UF2_FIRMWARE_BYTES_PER_SECTOR 256
#define UF2_SECTOR_COUNT   (_flash_size / UF2_FIRMWARE_BYTES_PER_SECTOR)
#define UF2_CLUSTER_COUNT  UF2_DIV_CEIL(UF2_SECTOR_COUNT, BPB_SECTORS_PER_CLUSTER)
#define UF2_BYTE_COUNT     (UF2_SECTOR_COUNT * BPB_SECTOR_SIZE) // always a multiple of sector size, per UF2 spec
#define UF2_FIRST_CLUSTER_NUMBER  info_cluster_start(NUM_FILES -1)
#define UF2_LAST_CLUSTER_NUMBER   (UF2_FIRST_CLUSTER_NUMBER + UF2_CLUSTER_COUNT - 1)


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

// size of CURRENT.UF2:
static FileContent_t const info[] = {
    {.name = "INFO_UF2TXT", .content = infoUf2File , .size = sizeof(infoUf2File) - 1},
    {.name = "INDEX   HTM", .content = indexFile   , .size = sizeof(indexFile  ) - 1},
#if TINYUF2_FAVICON
    {.name = "AUTORUN INF", .content = autorunFile , .size = sizeof(autorunFile) - 1},
    {.name = "FAVICON ICO", .content = favicon_data, .size = favicon_len            },
#endif
    // current.uf2 must be the last element and its content must be NULL
    {.name = "CURRENT UF2", .content = NULL       , .size = 0                       },
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
static uint16_t info_cluster_count(uint32_t fid)
{
  if (info[fid].size)
  {
    return UF2_DIV_CEIL(info[fid].size, BPB_SECTOR_SIZE*BPB_SECTORS_PER_CLUSTER);
  }
  else
  {
    // CURRENT.UF2
    return UF2_CLUSTER_COUNT;
  }
}

// cache the cluster start offset for each file
// this allows more flexible algorithms w/o O(n) time
static uint16_t _file_starting_clusters[NUM_FILES+1];
static void init_info2(void) {
  // +2 because FAT decided first data sector would be in cluster number 2, rather than zero
  uint16_t start_cluster = 2;
  for (uint16_t i = 0; i < NUM_FILES; i++) {
    _file_starting_clusters[i] = start_cluster;
    start_cluster += info_cluster_count(i);
  }
  _file_starting_clusters[NUM_FILES] = start_cluster;
  return;
}

// get starting cluster of a file index
static uint16_t info_cluster_start(uint32_t fid)
{
  // return cached information
  // note extra information at index NUM_FILES ...
  // this indicates the first cluster *AFTER* CURRENT.UF2.
  return _file_starting_clusters[ (fid < NUM_FILES) ? fid : NUM_FILES ];
}

static uint16_t info_cluster_last_of_file(uint32_t fid)
{
  if (fid >= NUM_FILES)
  {
    return CLUSTER_COUNT;
  }
  return _file_starting_clusters[fid+1] - 1;
}

// get file index for file that uses the cluster
// if cluster is past last file, returns ( NUM_FILES-1 ).
//
// Caller must still check if a particular *sector*
// contains data from the file's contents, as there
// are often padding sectors, including all the unused
// sectors past the end of the media.
static uint32_t info_index_of(uint32_t cluster)
{
  // default results for invalid requests is the index of the last file (CURRENT.UF2)
  static const uint32_t DEFAULT_FID_RESULT = NUM_FILES - 1;

  if (cluster >= 0xFFF0) {
    return DEFAULT_FID_RESULT;
  }
  for (uint32_t i = 0; i < NUM_FILES; i++) {
    if (cluster < info_cluster_start(i)) {
      continue; // before this file's first cluster
    }
    if (cluster > info_cluster_last_of_file(i)) {
      continue; // past this file's last used cluster
    }
    return i;
  }
  return DEFAULT_FID_RESULT;
}

static uint32_t old_info_cluster_start(uint32_t fid)
{
  // +2 because FAT decided first data sector would be in cluster number 2, rather than zero
  uint32_t start_cluster = 2;
  for(uint32_t i=0; i<fid; ++i)
  {
    start_cluster += info_cluster_count(i);
  }
  return start_cluster;
}
static uint32_t old_info_index_of(uint32_t cluster)
{
  cluster -= 2; // first cluster data is 2

  for(uint32_t i=0; i<NUM_FILES; ++i)
  {
    uint32_t count = info_cluster_count(i);
    if (cluster < count) return i;
    cluster -= count;
  }
  return NUM_FILES-1;
}


void uf2_init(void)
{
  GF_DEBUG_PRINT(("UF2 Initialization started:\n"));

  // TODO maybe limit to application size only if possible board_flash_app_size()
  _flash_size = board_flash_size();
  init_info2();

#if defined(DEBUG)

  GF_DEBUG_PRINT(("----------------------------------------------------------------------\n"));
  GF_DEBUG_PRINT(("File system clusters:\n"));
  int start = 0;
  int end   = 0;
  GF_DEBUG_PRINT(("  %-10s = 0x%04x .. 0x%04x (%5d .. %5d)\n", "BPB", start, end, start, end ));

  start = 1;
  end = 1 + BPB_SECTORS_PER_FAT - 1;
  GF_DEBUG_PRINT(("  %-10s = 0x%04x .. 0x%04x (%5d .. %5d)\n", "FAT0", start, end, start, end ));

  start += BPB_SECTORS_PER_FAT;
  end   += BPB_SECTORS_PER_FAT;
  GF_DEBUG_PRINT(("  %-10s = 0x%04x .. 0x%04x (%5d .. %5d)\n", "FAT1", start, end, start, end ));

  start = FS_START_ROOTDIR_SECTOR;
  end   = FS_START_CLUSTERS_SECTOR - 1;
  GF_DEBUG_PRINT(("  %-10s = 0x%04x .. 0x%04x (%5d .. %5d)\n", "DIRENTRIES", start, end, start, end ));

  GF_DEBUG_PRINT(("  --------------------------------------------------------------------\n"));
  for (uint32_t i = 0; i < NUM_FILES; i++) {
    FileContent_t const * inf = info + i;
    uint16_t startC = info_cluster_start(i);
    uint16_t lastC  = info_cluster_last_of_file(i);
    GF_DEBUG_PRINT((
      "  File %c%c%c%c%c%c%c%c%c%c%c: Clusters [0x%04x .. 0x%04x] ([%d .. %d])\n",
      inf->name[0], inf->name[1], inf->name[2], inf->name[3],
      inf->name[4], inf->name[5], inf->name[6], inf->name[7],
      inf->name[8], inf->name[9], inf->name[10],
      startC, lastC, startC, lastC));
  }
  do {
    uint16_t startC = info_cluster_start(NUM_FILES);
    uint16_t lastC  = info_cluster_last_of_file(NUM_FILES);
    GF_DEBUG_PRINT((
      "  Unused  Clusters: Clusters [0x%04x .. 0x%04x] ([%d .. %d])\n",
      startC, lastC, startC, lastC));
  } while (0);
  GF_DEBUG_PRINT(("----------------------------------------------------------------------\n"));

  GF_DEBUG_PRINT(("Comparing old vs. new  info_cluster_start() function\n"));
  for (uint32_t f = 0; f <= NUM_FILES; f++) {
    uint32_t oldStart = old_info_cluster_start(f);
    uint32_t newStart = info_cluster_start(f);
    if (newStart != oldStart) {
      GF_DEBUG_PRINT(("Start of FID mismatch (%d):  Old 0x%04x  New 0x%04x\n", f, oldStart, newStart));
    }
  }
  GF_DEBUG_PRINT(("----------------------------------------------------------------------\n"));

  GF_DEBUG_PRINT(("Comparing old vs. new  old_info_index_of() function\n"));
  for (uint32_t c = 0; c < BPB_TOTAL_SECTORS; c++) {
    uint32_t oldFileIndexForCluster = old_info_index_of(c);
    uint32_t fileIndexForCluster = info_index_of(c);
    if (fileIndexForCluster != oldFileIndexForCluster) {
      GF_DEBUG_PRINT(("FID lookup by cluster mismatch (0x%04x):  Old 0x%04x  New 0x%04x\n", c, oldFileIndexForCluster, fileIndexForCluster));
    }
  }
  GF_DEBUG_PRINT(("----------------------------------------------------------------------\n"));

  GF_DEBUG_PRINT(("UF2 Initialization complete\n"));
#endif // defined(DEBUG)

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

  if ( block_no == 0 ) // aka requesting boot block
  {
    // Requested boot block
    memcpy(data, &BootBlock, sizeof(BootBlock));
    data[510] = 0x55;    // Always at offsets 510/511, even when BPB_SECTOR_SIZE is larger
    data[511] = 0xaa;    // Always at offsets 510/511, even when BPB_SECTOR_SIZE is larger
  }
  else if ( block_no < FS_START_ROOTDIR_SECTOR ) // aka requesting sector of FAT tables
  {
    // Requested FAT table sector
    sectionRelativeSector -= FS_START_FAT0_SECTOR;

    // second FAT is same as the first... use sectionRelativeSector to write data
    if ( sectionRelativeSector >= BPB_SECTORS_PER_FAT )
    {
      sectionRelativeSector -= BPB_SECTORS_PER_FAT;
    }

    uint16_t* data16 = (uint16_t*) (void*) data;

    uint32_t sectorFirstCluster = sectionRelativeSector * FAT_ENTRIES_PER_SECTOR;
    uint32_t firstUnusedCluster = info_cluster_start(NUM_FILES);

    // OPTIMIZATION:
    // Because all files are contiguous, the FAT CHAIN entries
    // are all set to (cluster+1) to point to the next cluster.
    // All clusters past the last used cluster of the last file
    // are set to zero.
    //
    // EXCEPTIONS:
    // 1. Clusters 0 and 1 require special handling
    // 2. Final cluster of each file must be set to END_OF_CHAIN
    // 

    // Set default FAT values first.
    for (uint16_t i = 0; i < FAT_ENTRIES_PER_SECTOR; i++)
    {
      uint32_t cluster = i + sectorFirstCluster;
      if (cluster >= firstUnusedCluster)
      {
        data16[i] = 0;
      }
      else
      {
        data16[i] = cluster + 1;
      }
    }

    // Exception #1: clusters 0 and 1 need special handling
    if (sectionRelativeSector == 0)
    {
      data[0] = BPB_MEDIA_DESCRIPTOR_BYTE;
      data[1] = 0xff;
      data16[1] = FAT_END_OF_CHAIN; // cluster 1 is reserved
    }

    // Exception #2: the final cluster of each file must be set to END_OF_CHAIN
    for (uint32_t i = 0; i < NUM_FILES; i++)
    {
      uint32_t lastClusterOfFile = info_cluster_last_of_file(i);
      if (lastClusterOfFile >= sectorFirstCluster)
      {
        uint32_t idx = lastClusterOfFile - sectorFirstCluster;
        if (idx < FAT_ENTRIES_PER_SECTOR)
        {
          // that last cluster of the file is in this sector
          data16[idx] = FAT_END_OF_CHAIN;
        }
      }
    }
  }
  else if ( block_no < FS_START_CLUSTERS_SECTOR ) // aka requesting root directory sector(s)
  {
    // Requested (root) directory sector .. because not supporting subdirectories (yet)
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

      FileContent_t const *inf = &info[fileIndex];
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
  else if ( block_no < BPB_TOTAL_SECTORS ) // aka read from the data area (files, unused space, ...)
  {

    sectionRelativeSector -= FS_START_CLUSTERS_SECTOR;

    // plus 2 for first data cluster offset
    uint32_t const cluster_num = 2 + sectionRelativeSector / BPB_SECTORS_PER_CLUSTER;

    if ( cluster_num < UF2_FIRST_CLUSTER_NUMBER )
    {
      // Handle all files other than CURRENT.UF2
      // first data cluster == first file
      uint32_t fid = info_index_of(cluster_num);
      FileContent_t const * inf = &info[fid];

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
