import os
import glob
import sys
import subprocess
import time
from multiprocessing import Pool

SUCCEEDED = "\033[32msucceeded\033[0m"
FAILED = "\033[31mfailed\033[0m"

build_format = '| {:32} | {:18} | {:6} | {:6} | {:6} |'
build_separator = '-' * 74


# return 1 if succeeded, 0 if failed
def build_board(port, board):
    start_time = time.monotonic()
    make_result = subprocess.run("make -j -C {} BOARD={} all".format(port, board), shell=True, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT)
    subprocess.run("make -j -C {} BOARD={} self-update".format(port, board), shell=True, stdout=subprocess.PIPE,
                   stderr=subprocess.STDOUT)
    build_duration = time.monotonic() - start_time

    succeeded = 0
    flash_size = "-"
    sram_size = "-"

    if make_result.returncode == 0:
        succeeded = 1
        build_dir = "{}/_build/{}".format(port, board)
        out_file = glob.glob(build_dir + "/*.elf")[0]
        size_output = subprocess.run('size {}'.format(out_file), shell=True, stdout=subprocess.PIPE).stdout.decode(
            "utf-8")
        size_list = size_output.split('\n')[1].split('\t')
        flash_size = int(size_list[0])
        sram_size = int(size_list[1]) + int(size_list[2])

    print(build_format.format(board, SUCCEEDED if succeeded else FAILED, "{:.2f}s".format(build_duration), flash_size, sram_size))
    if make_result.returncode != 0:
        print(make_result.stdout.decode("utf-8"))

    return succeeded


# return [succeeded, failed]
def build_port(port):
    # All supported boards
    all_boards = []
    for entry in os.scandir(port + "/boards"):
        if entry.is_dir():
            all_boards.append(entry.name)
    all_boards.sort()

    success_count = 0
    with Pool(processes=os.cpu_count()) as pool:
        pool_args = list((map(lambda b: [port, b], all_boards)))
        success_count = sum(pool.starmap(build_board, pool_args))

    return [success_count, len(all_boards)-success_count]


if __name__ == '__main__':
    # Default is all ports
    all_ports = []
    for entry in os.scandir("ports"):
        if entry.is_dir() and entry.name != 'template_port':
            all_ports.append(entry.name)
    if len(sys.argv) > 1:
        all_ports = list(set(all_ports).intersection(sys.argv))
    all_ports.sort()

    os.chdir("ports")

    print(build_separator)
    print(build_format.format('Board', '\033[39mResult\033[0m', 'Time', 'Flash', 'SRAM'))
    print(build_separator)

    total_time = time.monotonic()

    # succeeded, failed
    total_result = [0, 0]

    for port in all_ports:
        print(build_separator)
        print('| {:^71} |'.format('Port ' + port))
        print(build_separator)
        r = build_port(port)
        total_result = list(map(lambda x, y: x + y, total_result, r))

    # Build Summary
    total_time = time.monotonic() - total_time
    print(build_separator)
    print("Build Sumamary: {} {}, {} {} and took {:.2f}s".format(total_result[0], SUCCEEDED, total_result[1], FAILED, total_time))
    print(build_separator)

    sys.exit(total_result[1])
