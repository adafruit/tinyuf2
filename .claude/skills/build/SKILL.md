---
name: build
description: The TinyUF2 build contract. Use when a change must be verified by building, when an agent needs the boards a diff affects, or when a workflow asks for "the project's build". Resolves scope to boards, builds each the way CI does in a private dir, runs the ghostfat self-test when its inputs change, reports pass/fail with the first error.
---

# Build contract

`scripts/check_build.py` is the entry point for verifying a change; every agent and workflow that does so calls it rather than composing make, cmake or idf.py lines. A debug build for a probe session is not verification and uses the port's own build directly (below).

```bash
B=.claude/skills/build/scripts/check_build.py
python3 $B --scope <changed paths or dirs>     # boards a change affects
python3 $B --base master                        # same, from the branch diff
python3 $B --base master --worktree             # same, plus uncommitted and untracked changes
python3 $B --select-only (--scope ... | --base REF [--worktree] | --diff-file FILE) [--hil-config ROSTER]   # the selection alone
python3 $B --board feather_stm32f405_express [--board ...]
python3 $B --board lpcxpresso55s69 -D LOG=2     # a define, passed to the board's backend
python3 $B ... --shared                         # keep cmake-build/cmake-build-<board>, the dir a flash or HIL run uses
python3 $B --board imxrt1060_evk --backend cmake --shared   # the HIL's receipt: cmake whatever CI uses
python3 $B ... --idf local                      # exported ESP-IDF instead of CI's docker image
```

The last stdout line is JSON. An agent acts on `pass`; `firstError`, and `error` on exit 2, naming the cause or the remedy; `boards[]` (`status` `ok`, `failed` or `error`, `log`, `artifacts`, `notImplemented`); `built`, the artifacts of `--shared` roots, the only ones kept after a pass, with each one's hash in `boards[].sha256`; `nothingToBuild` and `uncovered`, each path with its reason; and `idf.matchesCi`. `input` and `defines` record what a build used (HEAD, `dirty`, submodule and `get_deps` dependency commits, `dirtyInputs` for any of those with local changes): the HIL contract binds firmware to this record. `paths` gives every changed path's `rule` and `reason`, the answer to why a path selected what it did. Exit 0 pass, 1 a build, self-test or test failed, 2 usage, resolution or a missing prerequisite, 3 an uncovered path; 2 outranks 1, and 1 outranks 3. `-v` streams the build to stderr; each build's log is `<buildDir>/check_build.log`.

`--select-only` prints the selection (`build.{ports,builds,ghostfat,tests,paths}`) and stops before any toolchain check: what any agent or CI step reads for "what does this change affect". With `--hil-config <the host's roster>` it adds `hil.{boards,full,uncovered}`: the roster boards the change puts under the HIL battery, and each selected port with no roster board on this host.

## Reporting

An agent that reports `buildOk` and `notes` (agentrc's `code-writer`) maps the JSON this way: `buildOk` is `pass`. A pass with no board, self-test or test run is "nothing to build": quote each `nothingToBuild` reason in `notes`, so nobody mistakes it for a build that ran. Exit 3 is `buildOk` false with each `uncovered` reason quoted verbatim: that path is firmware no CI build compiles, and a human adds coverage or accepts the gap. Exit 1 or 2 quotes `firstError` (and `error`). A pass on `--idf local` whose `idf.matchesCi` is false is supplemental evidence only: say so in `notes`; acceptance needs CI's IDF.

## Judgment

- **Selection is the script's**, first match per path, and `paths[].reason` says why. A mixed change takes the union, and an uncovered path fails it whatever else built. The policy behind the rules:
  - A change to a port, board, app or dependency builds the boards that compile it: a board's own files that board; other port files the port's `REPRESENTATIVES` (rig boards first, both ESP32-S2 and -S3, both i.MX RT10xx and RT1170); an app or dependency the representatives of the ports whose CI backend compiles it.
  - Shared code (`src/`, `lib/`, the shared build files) and anything unclassified builds every port's representatives, plus the ghostfat self-test when a ghostfat input changed.
  - A change to how boards build (this script, `build.yml`, `build_util.yml`, `ci_set_matrix.py`, `.github/actions/`) runs the contract's own tests and one smoke build per backend; no firmware build verifies workflow syntax or orchestration. A change to the contract's tests runs the tests only.
  - CodeQL's make build of feather_stm32f405_express counts as coverage for the make files it reads.
  - Firmware no CI build compiles is uncovered: `ports/template_port/`, `ports/ch32v20x/` (`--board ch32v203_r0_1v0` builds it on request, with a note), a build file the port's CI backend never reads, a stub app.
  - Docs and agent, editor and repo metadata build nothing.
- **Builds are CI's.** Each port uses the backend `build.yml` gives it (`BACKENDS` in the script; `test_build.py` fails when the two disagree): make `all self-update`, then `copy-artifact`, then every `ports/<port>/apps/*` but `self_update`; cmake `-G Ninja -DCMAKE_BUILD_TYPE=MinSizeRel`; Espressif `idf.py build`. A board passes only with the artifacts its build must produce (`expected_artifacts()`): the bootloader images and the self-update and app images the port builds. A port without self-update, or a stub app, is listed in `notImplemented`, which is not a failure.
- **`--backend cmake`** is for the HIL's receipt only, with `--board` and `--shared`: CI still builds each port with its `build.yml` backend, so it is no CI evidence. A port without `CMakeLists.txt`, or Espressif, is refused. `-D` takes the cmake spellings: `LOGGER=RTT`, not `rtt`; `DEBUG` is ignored, the build stays MinSizeRel; `LOG` sets `CFG_TUSB_DEBUG` only, not `TUF2_LOG`; raw flags go through `CFLAGS_CLI`.
- **ESP-IDF** builds in CI's image, `espressif/idf:<build.yml's toolchain_version>`, through docker by default; a missing image is exit 2 naming the `docker pull`. `--idf local` uses the exported IDF and records its version and `matchesCi`: evidence from a different IDF is supplemental, not acceptance.
- **ghostfat** builds each `ports/test_ghostfat/boards/*` config natively and runs it against its known-good image in the private dir, one config at a time: `huge` needs about 3 GiB of disk while it runs. A passing config's dir is removed; a failing one keeps its log.
- **Private dirs for parallel agents.** Each build starts from an empty `cmake-build/cmake-build-agent-<pid>-<board>` (with `-<backend>` when a board builds with another backend than its port's) and is removed when it passes (`removed`; its `artifacts` say what it produced, nothing is left to flash); a failed one is kept for its log. Nothing is written into the source tree: make takes `BUILD_ROOT=<dir>`, cmake and idf `-DARTIFACT_PATH=<dir>/_bin`. `--shared` rebuilds `cmake-build/cmake-build-<board>` from clean and keeps it for flashing; it needs exclusive ownership of that board.
- **Dependencies are never fetched here.** `lib/tinyusb` and `lib/uf2` are submodules (`git submodule update --init lib/tinyusb lib/uf2`); a port's `tools/get_deps.py` rows must exist. In a worktree, symlink them from the primary checkout (CLAUDE.md), never run `get_deps.py` through a symlink: it runs `git reset --hard` in each dependency.
- **Debug builds** for a probe session use the port's backend directly: make `make -C ports/<port> BOARD=<b> DEBUG=1 LOG=2 LOGGER=rtt all` (`LOGGER=swo` too); cmake `-DCMAKE_BUILD_TYPE=Debug -DLOG=2 -DLOGGER=RTT` (only `RTT` adds the RTT sources). Flash targets: make `flash-jlink`, `flash-pyocd`, `flash-stlink`, `flash-uf2`; cmake `tinyuf2-jlink`, `-stlink`, `-openocd`; Espressif `idf.py -C ports/espressif -DBOARD=<b> flash`.
- **Printing a command is not verification.** A verdict is the JSON of a run that happened; an agent that cannot run the script reports the build as not run.
