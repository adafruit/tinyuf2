import argparse
import sys
import subprocess
from pathlib import Path
from multiprocessing import Pool

# Mandatory Dependencies that is always fetched
# path, url, commit, family (Alphabet sorted by path)
deps_mandatory = {}

# Optional Dependencies per MCU
# path, url, commit, family (Alphabet sorted by path)
deps_optional = {
    'lib/mcu/nxp/mcux-sdk': ['https://github.com/nxp-mcuxpresso/mcux-sdk.git',
                             '9990f264f98430f6d885041ab0f24224d68f4958',
                             'kinetis_k kinetis_k32l2 kinetis_kl lpc51 lpc54 lpc55 mcx mimxrt10xx'],
    'lib/mcu/st/cmsis_device_f3': ['https://github.com/STMicroelectronics/cmsis_device_f3.git',
                                   '5e4ee5ed7a7b6c85176bb70a9fd3c72d6eb99f1b',
                                   'stm32f3'],
    'lib/mcu/st/cmsis_device_f4': ['https://github.com/STMicroelectronics/cmsis_device_f4.git',
                                   '2615e866fa48fe1ff1af9e31c348813f2b19e7ec',
                                   'stm32f4'],
    'lib/mcu/st/cmsis_device_h7': ['https://github.com/STMicroelectronics/cmsis_device_h7.git',
                                   '60dc2c913203dc8629dc233d4384dcc41c91e77f',
                                   'stm32h7'],
    'lib/mcu/st/cmsis_device_l4': ['https://github.com/STMicroelectronics/cmsis_device_l4.git',
                                   '6ca7312fa6a5a460b5a5a63d66da527fdd8359a6',
                                   'stm32l4'],
    'lib/mcu/st/stm32f3xx_hal_driver': ['https://github.com/STMicroelectronics/stm32f3xx_hal_driver.git',
                                        '1761b6207318ede021706e75aae78f452d72b6fa',
                                        'stm32f3'],
    'lib/mcu/st/stm32f4xx_hal_driver': ['https://github.com/STMicroelectronics/stm32f4xx_hal_driver.git',
                                        '04e99fbdabd00ab8f370f377c66b0a4570365b58',
                                        'stm32f4'],
    'lib/mcu/st/stm32h7xx_hal_driver': ['https://github.com/STMicroelectronics/stm32h7xx_hal_driver.git',
                                        'd8461b980b59b1625207d8c4f2ce0a9c2a7a3b04',
                                        'stm32h7'],
    'lib/mcu/st/stm32l4xx_hal_driver': ['https://github.com/STMicroelectronics/stm32l4xx_hal_driver.git',
                                        'aee3d5bf283ae5df87532b781bdd01b7caf256fc',
                                        'stm32l4'],
    'lib/mcu/wch/ch32v20x': ['https://github.com/openwch/ch32v20x.git',
                             'c4c38f507e258a4e69b059ccc2dc27dde33cea1b',
                             'ch32v20x'],
    'lib/sct_neopixel': ['https://github.com/gsteiert/sct_neopixel.git',
                         '497ca8974927e3b853fd80c8fc35f4e557af79b9',
                         'lpc55'],
}

# combined 2 deps
deps_all = {**deps_mandatory, **deps_optional}

# TOP is tinyusb root dir
TOP = Path(__file__).parent.parent.resolve()


def run_cmd(cmd):
    r = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0:
        print(f'Error: {cmd} failed with {r.returncode}')
        print(r.stdout.decode("utf-8"))
    return r


def get_a_dep(d):
    if d not in deps_all.keys():
        print('{} is not found in dependency list')
        return 1
    url = deps_all[d][0]
    commit = deps_all[d][1]
    families = deps_all[d][2]

    print(f'cloning {d} with {url}')

    p = Path(TOP / d)
    git_cmd = f"git -C {p}"

    # Init git deps if not existed
    if not p.exists():
        p.mkdir(parents=True)
        run_cmd(f"{git_cmd} init")
        run_cmd(f"{git_cmd} remote add origin {url}")
        head = None
    else:
        # Check if commit is already fetched
        result = run_cmd(f"{git_cmd} rev-parse HEAD")
        head = result.stdout.decode("utf-8").splitlines()[0]
        run_cmd(f"{git_cmd} reset --hard")

    if commit != head:
        run_cmd(f"{git_cmd} fetch --depth 1 origin {commit}")
        run_cmd(f"{git_cmd} checkout FETCH_HEAD")

    return 0


def find_family(board):
    bsp_dir = Path(TOP / "ports")
    for family_dir in bsp_dir.iterdir():
        if family_dir.is_dir():
            board_dir = family_dir / 'boards' / board
            if board_dir.exists():
                return family_dir.name
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('families', nargs='*', default=[], help='Families to fetch')
    parser.add_argument('-b', '--board', action='append', default=[], help='Boards to fetch')
    parser.add_argument('--print', action='store_true', help='Print commit hash only')
    args = parser.parse_args()

    families = args.families
    boards = args.board
    print_only = args.print

    status = 0
    deps = list(deps_mandatory.keys())

    if 'all' in families:
        deps += deps_optional.keys()
    else:
        families = list(families)
        if boards is not None:
            for b in boards:
                f = find_family(b)
                if f is not None:
                    families.append(f)

        for f in families:
            for d in deps_optional:
                if d not in deps and f in deps_optional[d][2]:
                    deps.append(d)

    if print_only:
        pvalue = {}
        for d in deps:
            commit = deps_all[d][1]
            pvalue[d] = commit
        print(pvalue)
    else:
        with Pool() as pool:
            status = sum(pool.map(get_a_dep, deps))
    return status


if __name__ == "__main__":
    sys.exit(main())
