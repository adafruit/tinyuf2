---
name: hil
description: The TinyUF2 HIL contract. Use when a change needs hardware evidence on a rig board, when a debug or validation session must take, flash, clean up or release a TinyUF2 rig board, or when a workflow asks for "the project's HIL contract". Runs the bootloader battery on the roster's boards, owns the board lock, and reports pass/fail per board with target-side evidence.
---

# HIL contract

`scripts/hil_test.py` holds the mechanics: roster and source checks, firmware binding, locking, the probe and USB steps, cleanup and the JSON report. Agents call it instead of composing J-Link, mtools or lock commands. This page is the judgment.

## Roster

- The roster is `test/hil/local.json`, the boards on htpc's bench. On a machine without a board, its run fails at `install`, where J-Link finds no probe with that serial, before anything is written: `cleanup.state` is `untouched` and nothing stays held. ci.lan has no TinyUF2 rig yet (a follow-up).
- `TINYUSB_DIR` must name the tinyusb checkout whose `test/hil/helper/hil_lock.py` owns the board locks; every command refuses without it. Set it in the login profile, which headless sessions (chief, `hil-operator`) inherit.

A roster entry is named by its TinyUF2 board (`ports/<port>/boards/<name>`, which also gives the port) and keeps tinyusb's shape (`name`, `uid`, `flasher {name, uid, args}`), so agentrc's `rtt.py`, `pc_sample.py` and `probe_state.py` resolve the probe with `--hil-config test/hil/local.json --board <name>`. A J-Link entry has `args` exactly `-device <name>`; the runner uses SWD at 4000 kHz, so pass the same to those scripts, `--interface swd --speed 4000`. An espressif entry has `flasher.name` `esptool`, `flasher.uid` the USB-UART bridge's serial (`/dev/serial/by-id/*_<flasher.uid>-if*`), `flasher.args` exactly `--chip <chip>`, and the top-level `uid` the chip's factory MAC, which is TinyUF2's USB serial. The roster holds the board's hardware only; layouts come from the candidate's source. The `tinyuf2` block holds:
- the board lock name (`lock`) when tinyusb names the board differently, as `mimxrt1060_evk` for `imxrt1060_evk`; both runners take that one lock, and the helper's `status`, holder records and the report rows' `lock` show it. It defaults to the board name;
- the commissioned re-entry path (`reentry`).

The battery runs a board only after commissioning sets `reentry` and confirms `uid`; `install` and `restore` work without `reentry`, for commissioning. Only commissioned roster boards can be offered for a run. Adding a board is commissioning, the lead's (below), never a review-time or dispatch-time action: the runner refuses a build record from a dirty tree, an uncommitted roster entry included.

## Locks

Locks are tinyusb's: one kernel flock per board in `/tmp/tinyusb-hil-locks/`, taken through `$TINYUSB_DIR/test/hil/helper/hil_lock.py`. A board's lock is `<lock>`: its roster `tinyuf2.lock`, else the board name. It is tinyusb's name for the board, so TinyUF2 and tinyusb runs exclude each other; the helper's `hold` and `release` take it and `status` (no board argument) shows it, while `hil_test.py -b` and the probe scripts take the board name.
- **The battery locks itself,** as `hil_test.py`, which tinyusb's `release` refuses to kill. Never pre-hold a board you are about to run the battery on.
- **The lock fails closed.** An unusable lock dir refuses the run (exit 2); it never runs unlocked. `HIL_NO_BOARD_LOCK=1` bypasses the lock only when the task scope names forcing that board. The report then says `lockBypassed: true`.
- **Manual sessions** (hw-debugger, hw-validator):
  1. Take your own hold: `python3 $TINYUSB_DIR/test/hil/helper/hil_lock.py hold <lock> --reason "<unique session reason>"`.
  2. Install a build record's TinyUF2, and restore the board when done:

     ```bash
     python3 .claude/skills/hil/scripts/hil_test.py install -b <board> --build-record <record> --under-hold "<reason>" test/hil/local.json
     python3 .claude/skills/hil/scripts/hil_test.py restore -b <board> --build-record <record> --under-hold "<reason>" test/hil/local.json
     ```

     `install` is the battery's install step from the record (Run the battery: a J-Link board runs the record's `tinyuf2-jlink` target, an esptool board takes the four IDF segments), then waits for DFU; it takes the record the battery takes, admitted the same way, so it needs the automount exclusion rule (Commissioning) and a clean build of HEAD. `--try-reentry <method>`, while the roster's `reentry` is unset, gives DFU's fallback (Run the battery, dfu) for commissioning; `restore` takes it too. `restore` is the cleanup (below), from a clean build record of HEAD. Both refuse unless the hold is provably yours: the record's reason, a live pid, a FLOCK on the lock file in that pid's own fds, and a failing probe of the flock.
  3. Release with `python3 $TINYUSB_DIR/test/hil/helper/hil_lock.py release <lock>`, only after a `restore` that exited 0 with no `survivors`. Otherwise the board is not cleaned up: keep the hold and report it as a blocker.

  Manual exits: 0 the operation succeeded (for `install`, DFU came up; for `restore`, DFU left after the blinky copy and stayed away); 1 it failed before writing; 2 refused before any hardware access; 4 a child survived SIGKILL, or an `install` or `restore` failed after it began writing: keep the hold.

  On a refused hold, report the holder from `python3 $TINYUSB_DIR/test/hil/helper/hil_lock.py status` (no board argument; it prints every holder); never kill it. A `hil_test.py` holder whose record has `role: cleanup-holder` never frees on its own: report it as a blocker that needs the recovery dispatch (Exit 4), without waiting. Any other `hil_test.py` holder is a battery run; wait for it within the lock-wait budget.
- **Cleanup state** for a hw-validator or hw-debugger dispatch: `restore --under-hold` leaves the board on the record's TinyUF2 with `apps/blinky` copied through it, and its `cleanup.evidence` (DFU left after the copy and stayed away) is the observation that Cleanup records. Blinky running is not checked. Whoever uses the board next flashes it first; tinyusb's HIL does.
- **Lock-wait budget:** htpc has no CI runner, so it is the dev-bench row of chief's budget, 2 min, unless the dispatch names another.

## Run the battery

```bash
mkdir -p cmake-build/hil
python3 .claude/skills/build/scripts/check_build.py --board <board> --backend cmake --shared --hil-config test/hil/local.json > cmake-build/hil/<board>.build.json
python3 .claude/skills/hil/scripts/hil_test.py run -b <board> --build-record cmake-build/hil/<board>.build.json test/hil/local.json
```

`<board>` is the roster name, the TinyUF2 board name. An espressif board builds without `--backend cmake`: ESP-IDF in CI's docker image, as CI does.

- **Admission.** Before taking the lock the run checks the automount exclusion rule, and every span it could write (the HEX the flash target loads, inside the install span and the device's flash limits and laid out as the BIN; the BIN's board id), with the install and app spans taken from the candidate's source.
- **Build record.** It is this contract's build receipt: build it on the clean, pinned HEAD with `--hil-config` and pass it with `--build-record`. `--hil-config` binds the build's own flash target to the roster's probe or bridge (build contract); the run refuses a record whose binding names another flasher, and checks the files that target reads against the record. The build dir's lock covers that target only: the files the runner reads itself (the BIN it verifies, the segments it reads back, `apps/blinky.uf2` and `apps/dfu_runtime.uf2`) are copies in the run dir, taken at admission from bytes that hash as recorded, so a rebuild after the target cannot change them. For a J-Link board it must be a cmake build (`--backend cmake`), whatever backend CI builds the port with; board facts are read from the port's CMake files too. For an espressif board it must be an IDF build from CI's `espressif/idf` image; the run binds its generated `sdkconfig`, `flash_args`, the four segments (bootloader, partition table, otadata, `tinyuf2.bin` in the factory partition) and `apps/dfu_runtime.uf2`, and checks every segment against the generated partition table and the candidate's partition CSV. The run refuses a build record that is not clean, does not match the checkout now (HEAD, submodules, `get_deps` dependencies at their pins), or whose artifacts changed since. Commit first; ESP-IDF's records also go stale at the next commit (build contract).
- **Background.** Run it in the background; one board takes about 2 minutes. Use one board per run.
- **Selection.** There are no examples or test names to select: a run is the whole battery on one board, and the board is the only selection.

The battery's steps on one board, all under one lock. The roster's probe serial selects the board (each probe is wired to one target), so no step identifies the chip:
1. **install:** the record's `tinyuf2-jlink` target runs (`cmake --build <dir> --target tinyuf2-jlink`) under its build dir's lock, once the files it reads hash as recorded and its dry run shows nothing but the flasher; JLinkExe can exit 0 with every command failed, so the transcript must show the record's HEX downloaded (programmed, or skipped as already matching), `O.K.` and the script completed, with no failure line. The files are hashed again after it, and a session of the runner's verifies the BIN at its flash address (`verifybin`), then resets. The board is touched from the target's start; only a transcript that ends at "Connecting to J-Link ...FAILED", before any target connect, leaves it untouched.
2. **dfu:** the UF2 drive with this board's serial is found. On the RT boards the install has left the app start erased on the bench (Limits), so DFU comes up; if it never enumerates, as when a valid app boots (an install on stm32f303disco keeps the app, Limits), the commissioned `retained-register` re-entry brings DFU up (its claim says so); any other DFU failure fails the step. `INFO_UF2.TXT` must name this build's version and board, and `CURRENT.UF2` must have its size. The double-tap register is then cleared and read back, once the bootloader runs.
3. **copy:** a generated app is copied to the drive.
4. **app-ran:** the probe shows the app counting in thread mode with VTOR at the app start.
5. **reenter:** the bootloader is re-entered by the commissioned path, and the drive's `CURRENT.UF2` reads the app back.
6. **cleanup** (reported as `cleanup`, not a step, state `blinky copied`, or `untouched` with nothing to do when no session reached the board): the record's TinyUF2 is installed again as in install, DFU is found, the record's `apps/blinky.uf2` (admitted with the record: one family, every block in the app region) is copied to the drive, and the DFU device must leave and stay away for a quiet period. Any failure keeps the board held (Exit 4).

A board's evidence is scoped as the report says. "app-ran" is execution after the bootloader handoff; on a J-Link board a run triggered by the upload alone is unverified (an esptool board's app-ran observes the copied app itself over USB). "reenter" by `retained-register` is the forced-entry path, not a physical double tap.

On an esptool board, each esptool connection is a child of the runner (`esp_session.py`), and so is each USB control request (`usb_dfu.py`, pyusb):
1. **install:** a first connection takes the MD5s of every partition the battery never writes (nvs, ota_1, ffat on the 8 MB layout) as the run's snapshot, kept in the row's `snapshot` however the run ends; that session is the first to touch the board, which only a missing bridge (no tty with its serial), a container left by an earlier flash, or a failed or interrupted `docker create` of the flash container leaves untouched. Then ESP-IDF's `flash` target runs in CI's image (`cmake --build <dir> --target flash`), with the same lock, hash and dry-run checks as a J-Link install: the bridge's tty is the only device passed in, as `ESPPORT`, with `IDF_FLASH_FULL=1` so ESP-IDF v6 writes segments already in flash too, and the container is named `tinyuf2-hil-<board>` so a survivor is found and ended by name. Its transcript must show every segment written at its offset and hash-verified, then the hard reset. A runner session then reads each segment back and takes those MD5s again, then resets once; the runner compares the read-back bytes with the build's segment files and the MD5s with the snapshot, and any difference fails the step. esptool rewrites the bootloader header from `flash_args`, which the build already holds (dio, 80 MHz, 8 MB): on the bench (2026-10-13, esptool 5.3.1 in espressif/idf:v6.1) all four segments read back identical to the files. The roster's bridge selects the board (it is wired to that board only), so the chip is not identified, and its security eFuses and flash size are commissioning's to check. The evidence lists each write's span and the 4 KiB-aligned span covering it. Blank otadata boots the factory partition, TinyUF2.
2. **dfu:** as above; `INFO_UF2.TXT` reports the app partition (ota_0) as its flash, and no register is written.
3. **copy:** `apps/dfu_runtime` from the record, plus a block carrying a fresh nonce in ota_0's last 256 bytes, where the app reads it, renumbered under one `numBlocks`; the image itself is never patched. The record is refused when the image reaches that block or TinyUF2's 64 KiB flash cache window over it (`FLASH_CACHE_SIZE`) leaves ota_0. The evidence lists the image and nonce spans and the cache windows covering them.
4. **app-ran:** the app enumerates with its own VID:PID and the board's serial on the DFU's USB path, its DFU runtime interface string read from the device is `HIL <nonce>`, and TinyUF2 stays away for a quiet period.
5. **reenter** (`dfu-detach`): DFU_DETACH to the app is acknowledged, the app leaves, TinyUF2 comes back on the same path, and `CURRENT.UF2` reads back the image and the nonce block.
6. **recopy:** a copy with a fresh nonce boots the app again.
7. **cleanup:** as on a J-Link board, with the install as in step 1: the preserved regions' MD5s after the writes, and again after the blinky copy, must equal the run's snapshot (a recovery takes it from the failed report's `snapshot`; a manual `restore` takes its own first). A mismatch fails the cleanup and keeps the hold.

`--fail-at <step>` exists only for acceptance: it fails that step to exercise cleanup.

## Reporting

The last stdout line is JSON, also written to its `reportPath`; read that path, never an older report. Its fields:
- `pass`, `caveat`;
- per board: `ran`, `pass`, `locked`, `lockBypassed`, `firmware` (path, sha256, version, build record), `steps[]` (`step`, `pass`, `evidence`, `detail`), `cleanup` (`pass`, `state`, `evidence`, `heldAfter`, `holder`, `survivors`), `jlinkRetried` (J-Link boards only: sessions run again after a crash before the target connect; Limits), and `detail`;
- `error` on a refusal or an operation failure.

| Exit | Meaning |
|---|---|
| 0 | every board passed and was cleaned up |
| 1 | a board failed or did not run; it was cleaned up or never touched |
| 2 | refused before any hardware access (usage, roster, source, build record, lock helper, lock dir) |
| 4 | cleanup failed; the board is held when `cleanup.heldAfter` (not under `HIL_NO_BOARD_LOCK`). From `install` or `restore`: a child survived, or the operation failed after it began writing; keep your hold |

A delegated run (`hil-operator`) returns `{pass, results, caveat, wedged}` and, beside them, `reportPaths`:
- `pass`, `results` and `caveat` are copied verbatim from the JSON;
- `wedged` lists the boards the operator saw stop responding;
- `reportPaths` maps each board to its JSON's `reportPath`, which a recovery dispatch needs.
- With several boards, the operator runs one battery per board, one after another: `results` holds every board's row, `pass` is true only when every run's is, and `caveat` joins the runs' non-empty caveats.
- A launched run that ended without printing its JSON (killed, crashed) may have programmed the board and left it running a candidate. The operator writes `pass: false`, `caveat: "run ended without a report; board state unknown"` and one row per board, exactly `{board, ran: null, pass: false, locked: false, detail}`, with `detail` naming the exit status, the output tail and `python3 $TINYUSB_DIR/test/hil/helper/hil_lock.py status` at that moment.
- The operator runs the battery once and returns. It never waits on a lock and never retries: a `locked` row comes back as is, and the caller rules below are the caller's (chief's).
- A recovery dispatch names the board, the holder pid and the failed run's `reportPath`. It runs `restore --recover-holder` in the foreground and returns `{pass, results, caveat: "", wedged, exit, error, survivors}`: that JSON's `results`, `error` (`null` when absent) and `survivors` (`[]` when absent), and the exit status. Any exit but 0 is a blocker for the caller. A probe that cannot connect is `needs-user` (the board's recovery note, Exit 4).

### Review mapping

A review (`pr-review`) maps each board's row, except a commissioning run's (`commissioning: true`, from `--try-reentry`), which is never validation. A blocker takes precedence over every other mapping:
- `pass`: `ran`, `pass` and `cleanup.pass` all true;
- `fail`: `ran` and not `pass`, with a failing step, `cleanup.state` other than `untouched`, and that step's `detail`;
- `not-run`: `ran` false (`locked` or a refusal), or a failing step with `cleanup.state` `untouched`, with its `detail`. Nothing was written, so the failure is the rig's: no probe with that serial on this machine, one unplugged or dead, or no esptool bridge with that serial;
- a blocker, never a `fail` row: exit 4, `ran: null` (no report), and an abort, which is `ran` and not `pass` with no failing step (an interruption or an unexpected error, named in the board's `detail`).

`testedHead` is the build record's `input.head`. `regression` is `unknown` unless the battery also ran on the merge base.

### Caller rules
- **Retry.** A failed test may be retried once, and only when no board is `locked`, `wedged` or `heldAfter`, `caveat` is empty, and every board was cleaned up.
  - Keep both reports. A fail-then-pass is a pass with `flaky: true`, quoting both.
  - An abort (a failed run with no failing step), a cleanup failure, `heldAfter`, `wedged` or a missing report is never retried; it is a blocker until diagnosed.
  - A board whose run ended without a report gets a manual `restore --under-hold` before its next run, and only once no such process is left on the host. Killing the runner frees its lock but not its children, which `restore` cannot see, and nothing ties a surviving child to the run that died, so the check is host-wide: any other battery, holder or J-Link session also keeps the blocker. Run this as a command of its own, since a shell line carrying the plain name would match itself; none is left when it prints nothing:

    `pgrep -ax JLinkExe; pgrep -ax mcopy; pgrep -af '[h]il_test\.py'; pgrep -af '[e]sp_session\.py'; pgrep -af '[u]sb_dfu\.py'`

    The `hil_test.py` check also covers the runner's `fat-read` subcommand. While a process is left, or this cannot be established, the blocker stays.
- **Locked.** `locked` is an admission refusal, not a test failure. The caller admits again after the holder releases, within the lock-wait budget; the operator does not wait. Otherwise report the board not covered, naming the holder.
- **Exit 4.**
  - The board stays held by a detached holder forked from the run: reason `hil_test.py`, `role: cleanup-holder`, with its pid in `cleanup.holder`. It ignores SIGTERM and SIGINT, so a timeout kill cannot free the board; only recovery releases it.
  - If no holder could be forked, `cleanup.holder.inProcess` is set and the runner itself is the holder: it prints the report, closes its stdio and does not exit until recovered, so no completion notice arrives. When a run's notice is overdue, read the task's output: a final JSON line with `cleanup.holder.inProcess` true is this case. Do not wait for its exit.
  - `cleanup.survivors` lists children that outlived SIGKILL (a J-Link, mtools or FAT read stuck on the device), and a flash container that outlived `docker rm -f` (`{"container": "tinyuf2-hil-<board>"}`); recovery refuses while any of them is still alive. A runner killed outright leaves its container to run out; the next install refuses while `docker ps -a` lists it. Each child runs in a session of its own and the kill reaches the whole session, so a JLinkExe that ninja runs in a process group of its own under the flash target is killed and reported too.
  - tinyusb sees that holder as a battery run and waits, which is safe but means the board is out of service until recovered.
  - Do not release it by hand, and do not treat it as safe because tinyusb reflashes. The holder may stand for a stuck J-Link or mtools process.
  - Recovery is a separate `hil-operator` dispatch whose scope names forcing that board. After process, probe and host readiness are established, it runs:

    `python3 .claude/skills/hil/scripts/hil_test.py restore -b <board> --build-record <record> --recover-holder <pid> --report <reportPath> test/hil/local.json`

    `<record>` is the failed report's `firmware.buildRecord`, or a record rebuilt on the clean HEAD when it no longer verifies. The command proves that pid holds the board as the failed run's cleanup holder and that none of the run's survivors and no J-Link process on the probe is alive, restores the board while the lock stays held, and only then releases the holder. On an esptool board the restore checks the preserved regions against the snapshot in the failed report, and recovery is refused for a touched run without one or one whose regions differ from the checkout's. A candidate whose drive cannot take the blinky copy fails the restore; the board stays held until a record that can restore it is given. A second recovery of the same board while one runs is refused (exit 2).
  - If the probe cannot connect, recovery is the human's: on imxrt1060_evk, serial download mode (BOOT_MODE 01: SW7 OFF OFF OFF ON, inferred from the EVK guide); on espressif_esp32s3_devkitc_1, ROM download mode: hold Boot (SW1, GPIO0 low), press and release RST (SW2, CHIP_PU), then release Boot (DevKitC-1 schematic V1.0; the TRM's strap table also needs GPIO46 low, its default pull-down); on espressif_p4_function_ev, the same with BOOT (SW2, GPIO35 low) and RST (SW1, CHIP_PU) (Function-EV-Board schematic rev 1.4).

## Selection

`python3 .claude/skills/build/scripts/check_build.py --select-only (--diff-file <file> | --base <ref> [--worktree]) --hil-config test/hil/local.json` adds `hil.{boards, full, uncovered}`. Run the battery when `full` is set or `boards` is non-empty. An empty diff file selects nothing; a caller without the changed-file list passes `--base`. A fresh worktree, a review worktree included, needs CLAUDE.md's worktree setup (submodules and dependency links) before `check_build.py` can build in it. `uncovered` names what no roster board on this host can run; report it, never treat it as covered. An app source (`apps/`, `ports/<port>/apps/`) selects no board and is uncovered, except `dfu_runtime`, which selects the esptool boards of the ports that build it, and leaves uncovered each port that builds it without one (mimxrt10xx today): the battery runs the bootloader with its generated fixture on J-Link boards and with `dfu_runtime` on esptool boards. The runner, the build scripts it imports and the roster (`.claude/skills/hil/scripts/`, `.claude/skills/build/scripts/`, `test/hil/*.json`) select every roster board; a wording change to this page selects none.

## Commissioning a board

Commissioning is the lead's, never `hil-operator`'s or a review's. It runs under a manual hold, except for the re-entry run, which locks itself. Record each result in the board's commissioning note (agentrc `target-debug` project notes), and `uid`, `lock` and `reentry` in the roster. In this order:
- **Cabling:** cable the USB port TinyUF2 enumerates on (`BOARD_TUD_RHPORT`). It can differ from the one tinyusb examples use: P10, not P9, on lpcxpresso55s69; USB OTG1 on imxrt1060_evk. A DFU device "not seen" with no new device in `dmesg` is a cabling problem first. Keep the probe on a hub apart from the target's (Limits).
- **Silicon revision,** before any other result: read it from the chip marking or registers, and check that revision's errata through read-doc. RT1060's DIGPROG does not tell A from B, so the marking decides.
- **Automount exclusion:** `/etc/udev/rules.d/99-tinyuf2-hil.rules`, one line per board, with the VID and PID from the board's source, in exactly this form (the runner accepts only this form, with exact `==` matches):

  ```
  SUBSYSTEM=="block", ATTRS{idVendor}=="<vid>", ATTRS{idProduct}=="<pid>", ATTRS{serial}=="<uid>", ENV{UDISKS_IGNORE}="1"
  ```

  Write it with the roster's `uid`, before the serial can be confirmed: `install` and `run` refuse without the rule, and a fresh board runs whatever tinyusb last flashed, not TinyUF2. A serial a running tinyusb example reports (`lsusb -v`) is an early cross-check, not a confirmation. Until the serial is confirmed, also inhibit automount for every board of this VID:PID with a temporary `/etc/udev/rules.d/98-tinyuf2-hil-commissioning.rules`:

  ```
  SUBSYSTEM=="block", ATTRS{idVendor}=="<vid>", ATTRS{idProduct}=="<pid>", ENV{UDISKS_IGNORE}="1"
  ```

  Then `sudo udevadm control --reload`.
- **Bootloader:** `install` a clean HIL record of HEAD under the hold and observe DFU (add `--try-reentry retained-register` if a valid app could keep DFU away).
- **USB serial:** confirm the enumerated serial equals `uid` (sysfs or `lsusb -v`), and record the USB port paths. If it differs, fix `uid` and the rule together, reload, and `install` again; its reset re-enumerates the board and udev applies the reloaded rules, so no replug should be needed (by mechanism, not yet observed on a uid fix).
- **Cleanup:** `restore` under the hold and observe DFU leave after the blinky copy. Record the reset notes J-Link prints on install (`BENIGN`).
- **Exclusion proof:** delete the temporary rule and reload before the re-entry run below; its `dfu` step passes only when `udevadm info` on the enumerated block device shows `UDISKS_IGNORE=1` (`check_exclusive`). A host rule that ignores a whole VID, such as tinyusb's `88-tinyusb.rules` for 239a, sets the same property, so the proof cannot tell it from the serial rule; the runner still requires the serial line.
- **Loader footprint:** for the flash target's `loadfile`, place sentinels just past the written range and elsewhere in its erase block. Confirm them from a fresh session before the operation under test, and again from another fresh session after it: a verify in the session that wrote them cannot show what a later operation destroys. Make the written data differ from what is on the flash, since a download whose data already matches is skipped ("Contents already match") and erases nothing. Record the result in Limits.
- **Fixture prerequisites,** before anything executes the battery's fixture:
  - the app start meets VTOR's alignment for the fixture's vector table (`fixture()`);
  - its stack top, the `m_data` origin the runner reads (`ram_origin`) + 0x1000, is in RAM enabled when the bootloader hands off: the ROM default per read-doc, which TinyUF2 does not reconfigure (DTCM on imxrt1060_evk);
  - under a hold, a word just below that stack top takes a written value and reads it back, and then its saved value (0x20000FFC on imxrt1060_evk).
- **Re-entry:** commit the roster entry without `reentry`, build the record, release the manual hold, and run the battery in commissioning mode; it locks itself and ends with the cleanup, so it also proves the restore:

  ```bash
  python3 .claude/skills/hil/scripts/hil_test.py run -b <board> --build-record cmake-build/hil/<board>.build.json --try-reentry retained-register test/hil/local.json
  ```

  `--try-reentry` is the lead's only, and is refused once `reentry` is set. The row's `reentryDecision` names the method when the run passed or failed only at `reenter`'s `CURRENT.UF2` readback, every observation of the tried method is true (`controlBootedApp`, `dfuCameUp` and `magicConsumed` for `retained-register`), and the board was cleaned up and not held. Set `reentry` to it and commit. A null decision leaves `reentry` unset: file a `followup` issue with the observations for diagnosis, not as a diagnosed bug. When the drive copy itself fails, a fixture installed by hand with J-Link `loadbin` can isolate re-entry from the copy for diagnosis; it never sets `reentry`.
- **On an esptool board,** in place of the J-Link items: cable the native USB connector as well as the bridge's; check once by hand that the chip has no secure boot, secure download or flash encryption and that its flash holds the candidate's layout (`esptool get-security-info`, `esptool flash-id`), since the runner never checks them; record the bridge serial and the chip's MAC (`uid`, TinyUF2's USB serial); `install` from the record and observe DFU, then `restore` and observe DFU leave. Re-entry is `--try-reentry dfu-detach`, whose decision needs `detachAcked`, `appLeft` and `dfuCameUp`; before setting it, repeat DFU_DETACH ten times under the hold and check the host log shows no USB reset on the DETACH transitions (USB DFU 1.1 bitWillDetach).
- **J-Link transcript shape:** that `regs` and `mem32` output parses (`after()`, `regs()`), and which reset notes are benign. A benign note is exempted by device and exact text in `BENIGN`: on MIMXRT1062xxx6A, "Could not find valid reset vector." followed by "Target halted on flash header read.", printed on every reset while the app is invalid; on MIMXRT1011DAE5A the same note on every reset of a TinyUF2 image; on stm32f303vc, "Active write protection detected.", "Device will be unsecured now.", "Failed to unlock device." and "Can not attach to CPU. Trying connect under reset.", the connect that removes TinyUF2's write protection (Limits). A reset session (`w4` to AIRCR) passes only once J-Link reports the write issued ("Writing VALUE -> ADDR") with no failure before it. In a hand-written session, `-ExitOnError 0` still exits at a failed verify, before any later command runs, and leaves the target halted: resume it from a new session (`g`, or `r` then `g`), or keep verifies in a session ahead of the one that resumes.

## Limits

- Covered: imxrt1060_evk, metro_m7_1011, espressif_esp32s3_devkitc_1 and espressif_p4_function_ev on htpc. Not covered: ports without source facts in the runner, lpc55 among them (no battery, `install` or `restore` for lpcxpresso55s69; its 0A silicon also hangs TinyUF2 on a UF2 copy, #500), espressif chips other than the ESP32-S3 and ESP32-P4, self-update, an interrupted update, malformed UF2 input and the physical double tap.
- esptool boards: the runner needs esptool 5.2.0 and pyusb with libusb-1.0 for its own Python. Re-entry by DFU_DETACH is the only method built; the GPIO0 detection window is not. The bridge's UART carries every esptool session. A helper that survives SIGKILL is handled like a stuck J-Link, but no way to wedge one on the board was found, so that path is unit-tested only. At the end of a UF2 copy TinyUF2 restarts while the host's usb-storage is still talking to it: the host log shows a reset of that device and read errors on its block device. Seen on the S3 and the P4; other ports are unchecked. On the P4, while an esptool session holds the chip, the host log shows a full-speed device on TinyUF2's USB path that never answers its descriptor request (htpc 2026-10-14); the battery passed with it.
- Every probe and USB path is unverified until commissioning has run on the board, and commissioning is manual.
- cmake builds pass `TUF2_LOG=0` unless `LOG` is set, as make does, so the HIL image does not log on the board UART.
- `install` from a blank board, or one whose ROM found no boot image, brings up DFU (measured on imxrt1060_evk 2026-10-12 and metro_m7_1011 2026-10-13). With no boot image a new J-Link session reads the flash wrong (imxrt1060_evk: zeros; metro_m7_1011: bytes shifted) until a `loadbin` has run; a `loadbin` compare reads it right. On metro_m7_1011, J-Link then prints "Invalid flash header detected." at the install's first reset.
- Of a port's CMake flash targets the runner runs only `tinyuf2-jlink` and ESP-IDF's `flash`, bound by the record to the roster's probe or chip (the bridge's tty is passed at flash time). Never use the erase targets on a rig board (`tinyuf2-erase-external-jlink` erases [FLASH_BASE, FLASH_BASE + 64 KiB), the bootloader with it), nor ESP-IDF's `combined-flash`, which has no port selection and writes nvs and both OTA slots blank.
- On metro_m7_1011 (2026-10-13, J-Link V9.84), `tinyuf2-jlink`'s `loadfile` of the cmake HEX (0x60000400 on) reported "1 range affected (65536 bytes)" and, from a fresh session after it, 0x60000000, 0x6000BF00, 0x6000C000-0x6000C00F, 0x6000C200 and 0x6000FF00 read 0xFF while 0x60010000 kept its data. Its compare covered the whole block: over blinky it programmed, and right after a program it skipped ("Contents already match"). DFU came up within 2 s in each of these three runs. That every install by the target leaves [0x6000C000, 0x60010000), the app's first 16 KiB, erased is an inference from these samples and this HEX, not a measurement of every case; the re-entry fallback (Run the battery, dfu) covers an install that leaves a valid app. On imxrt1060_evk (2026-10-13), the same target over blinky also reported "1 range affected (65536 bytes)"; from a fresh session after it, blinky's vectors at 0x6000C000-0x6000C00F and 0x6000C200 read 0xFF, while the FCB at 0x60000000 and 0x60010000 kept their data.
- On stm32f303disco (2026-10-14, J-Link V9.84 on the board's J-Link OB), `tinyuf2-jlink`'s `loadfile` compared [0x08000000, 0x08004000) and reprogrammed only the 2 KiB pages that differed, erasing the rest of such a page past the image (a sentinel at 0x08003F00 read 0xFF from a fresh session after it), while 0x08004000 (the app start) and 0x08004800 kept their data. So an install keeps a valid app, and DFU then comes up through the retained-register fallback.
- On stm32f303vc, TinyUF2 write-protects its pages 0-7 at boot through the option bytes unless RCC_CSR's OBLRSTF is set, and it never clears that flag, so after any option-byte reload it skips protection until a power-on reset. A J-Link connect to a chip with that protection set prints the `BENIGN` unlock note and, read from a fresh `-device Cortex-M4` session after it, leaves the option bytes at RDP 0xAA with no WRP and flash intact (three samples, 2026-10-14). A battery therefore runs unprotected after its install; the protection itself is not covered.
- stm32f303disco does not signal a disconnect when TinyUF2 comes up after a reset (the F303 has no internal D+ pull-up, DS9118 Rev 14 Table 66 note 2; the MB1035 schematic is not in the library, and on the bench the host kept the old device), so the host does not re-enumerate it. The runner does nothing about this; on the bench its USB USER port (Port Authority hub 1-1, port 3) is power-cycled by hand with `uhubctl` after each reset. Without that, `dfu` times out.
- A `JLinkExe` crash inside the target is not retried (the crash retry below covers the runner's own sessions only): it fails the install, touched.
- J-Link's QSPI loader is undocumented (SEGGER UM08001 has nothing on it). Historically, at sampled sentinel points on both RT boards, the runner's former `loadbin` install (no longer issued) lost the rest of its 64 KiB block past the image while a sentinel at 0x60010000, in the next block, survived; a sample, not a guarantee for every image.
- `JLinkExe` sometimes crashes in `libjlinkarm` at the probe connect on htpc (SIGSEGV; once a glibc double-free abort); the cause is unknown. A session that crashed this way, before the target connect, runs once more after 2 s (`jlinkRetried`); a second crash fails the run. Seen in 2 of 94 runner sessions on 2026-10-12.
- A device hung mid-write makes the host controller retry its enumeration, which stalled a J-Link connect on the same hub for ~80 s (lpcxpresso55s69); that the hub is the cause is a hypothesis.
- If no cleanup holder can be forked (exit 4 with `cleanup.holder.inProcess`), the runner never exits until recovered.
- No reproducer for an instrumented build: the battery and `install` take only a clean build record. A claim that needs one is reported pending.
