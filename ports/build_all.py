import os
import shutil
import glob
import sys
import subprocess
import time

SUCCEEDED = "\033[32msucceeded\033[0m"
FAILED = "\033[31mfailed\033[0m"

success_count = 0
fail_count = 0
exit_status = 0

build_format = '| {:32} | {:18} | {:6} | {:6} | {:6} |'
build_separator = '-' * 74

# Default is all ports
all_ports = []
for entry in os.scandir("ports"):
    if entry.is_dir():
        all_ports.append(entry.name)

if len(sys.argv) > 1:
    all_ports = list(set(all_ports).intersection(sys.argv))

all_ports.sort()

os.chdir("ports")
#sha, version = build_info.get_version_info()

total_time = time.monotonic()

print(build_separator)
print(build_format.format('Board', '\033[39mResult\033[0m', 'Time', 'Flash', 'SRAM'))
print(build_separator)

for port in all_ports:
    # All supported boards
    all_boards = []
    for entry in os.scandir(port + "/boards"):
        if entry.is_dir():
            all_boards.append(entry.name)
    all_boards.sort()

    for board in all_boards:
        build_dir = "{}/_build/{}".format(port, board)

        start_time = time.monotonic()
        #subprocess.run("make -j -C {} BOARD={} clean".format(port, board), shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        make_result = subprocess.run("make -j -C {} BOARD={} all".format(port, board), shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        subprocess.run("make -j -C {} BOARD={} self-update".format(port, board), shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        subprocess.run("make -j -C {} BOARD={} copy-artifact".format(port, board), shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        build_duration = time.monotonic() - start_time

        flash_size = "-"
        sram_size = "-"

        if make_result.returncode == 0:
            success = SUCCEEDED
            success_count += 1

            out_file = glob.glob(build_dir + "/*.elf")[0]
            size_output = subprocess.run('size {}'.format(out_file), shell=True, stdout=subprocess.PIPE).stdout.decode("utf-8")
            size_list = size_output.split('\n')[1].split('\t')
            flash_size = int(size_list[0])
            sram_size = int(size_list[1]) + int(size_list[2])
        else:
            exit_status = make_result.returncode
            success = FAILED
            fail_count += 1

        print(build_format.format(board, success, "{:.2f}s".format(build_duration), flash_size, sram_size))

        if make_result.returncode != 0:
            print(make_result.stdout.decode("utf-8"))

# Build Summary
total_time = time.monotonic() - total_time
print(build_separator)
print("Build Sumamary: {} {}, {} {} and took {:.2f}s".format(success_count, SUCCEEDED, fail_count, FAILED, total_time))
print(build_separator)

sys.exit(exit_status)
