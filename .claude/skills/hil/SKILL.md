---
name: hil
description: The TinyUF2 HIL contract. Use when a change needs hardware evidence on a rig board, when a debug or validation session must take, flash, clean up or release a TinyUF2 rig board, or when a workflow asks for "the project's HIL contract". Runs the bootloader battery on the roster's boards, owns the board lock, and reports pass/fail per board with target-side evidence.
---

# HIL contract

`scripts/hil_test.py` holds the mechanics: roster and source checks, firmware binding, locking, the probe and USB steps, cleanup and the JSON report. Agents call it instead of composing J-Link, mtools or lock commands. This page is the judgment.

## Roster

- The roster is `test/hil/local.json`, the boards on htpc's bench. On a machine without a board, its run fails at `identity`, where J-Link finds no probe with that serial, before anything is written. ci.lan has no TinyUF2 rig yet (a follow-up).
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
  2. Program a bootloader BIN, and restore the board when done:

     ```bash
     python3 .claude/skills/hil/scripts/hil_test.py install -b <board> --firmware <bin> --sha256 <hash> --under-hold "<reason>" test/hil/local.json
     python3 .claude/skills/hil/scripts/hil_test.py restore -b <board> --build-record <record> --under-hold "<reason>" test/hil/local.json
     ```

     `install` writes one image from the board's flash base (0xFF up to where the port's build places the BIN, `_flash_base` + (`_fcfb_origin` & 0xFFF), 0x400 in on RT1011; the BIN; 0xFF up to the app start; then a zero page), reads it back, and refuses a BIN that is outside the install range or lacks this board's `UF2_BOARD_ID`; it needs the automount exclusion rule (Commissioning). On an esptool board it takes `--build-record <record>` instead of `--firmware` and `--sha256`, and writes the record's four IDF segments (Run the battery). `restore` is the cleanup (step 7 below), from a clean build record of HEAD. Both refuse unless the hold is provably yours: the record's reason, a live pid, a FLOCK on the lock file in that pid's own fds, and a failing probe of the flock.
  3. Release with `python3 $TINYUSB_DIR/test/hil/helper/hil_lock.py release <lock>`, only after a `restore` that exited 0 with no `survivors`. Otherwise the board is not cleaned up: keep the hold and report it as a blocker.

  Manual exits: 0 the operation succeeded (for `restore`, DFU left after the blinky copy and stayed away); 1 it failed and the board's state is unknown (for `restore`, it failed before writing); 2 refused before any hardware access; 4 a child survived SIGKILL, or a `restore` failed after it began writing: keep the hold.

  On a refused hold, report the holder from `python3 $TINYUSB_DIR/test/hil/helper/hil_lock.py status` (no board argument; it prints every holder); never kill it. A `hil_test.py` holder whose record has `role: cleanup-holder` never frees on its own: report it as a blocker that needs the recovery dispatch (Exit 4), without waiting. Any other `hil_test.py` holder is a battery run; wait for it within the lock-wait budget.
- **Cleanup state** for a hw-validator or hw-debugger dispatch: `restore --under-hold` leaves the board on the record's TinyUF2 with `apps/blinky` copied through it, and its `cleanup.evidence` (DFU left after the copy and stayed away) is the observation that Cleanup records. Blinky running is not checked. Whoever uses the board next flashes it first; tinyusb's HIL does.
- **Lock-wait budget:** htpc has no CI runner, so it is the dev-bench row of chief's budget, 2 min, unless the dispatch names another.

## Run the battery

```bash
mkdir -p cmake-build/hil
python3 .claude/skills/build/scripts/check_build.py --board <board> --backend cmake --shared > cmake-build/hil/<board>.build.json
python3 .claude/skills/hil/scripts/hil_test.py run -b <board> --build-record cmake-build/hil/<board>.build.json test/hil/local.json
```

`<board>` is the roster name, the TinyUF2 board name. An espressif board builds without `--backend cmake`: ESP-IDF in CI's docker image, as CI does.

- **Admission.** Before taking the lock the run checks the automount exclusion rule, and every span it could write (BIN, zero page, the device's flash limits, board id), with the install and app spans taken from the candidate's source.
- **Build record.** It is this contract's build receipt: build it on the clean, pinned HEAD and pass it with `--build-record`. For a J-Link board it must be a cmake build (`--backend cmake`), whatever backend CI builds the port with; board facts are read from the port's CMake files too. For an espressif board it must be an IDF build from CI's `espressif/idf` image; the run binds its generated `sdkconfig`, `flash_args`, the four segments (bootloader, partition table, otadata, `tinyuf2.bin` in the factory partition) and `apps/dfu_runtime.uf2`, and checks every segment against the generated partition table and the candidate's partition CSV. The run refuses a build record that is not clean, does not match the checkout now (HEAD, submodules, `get_deps` dependencies at their pins), or whose artifacts changed since. Commit first. A debug build goes through `install`, not the battery.
- **Background.** Run it in the background; one board takes about 2 minutes. Use one board per run.
- **Selection.** There are no examples or test names to select: a run is the whole battery on one board, and the board is the only selection.

The battery's steps on one board, all under one lock:
1. **identity:** the probe is selected by serial.
2. **install:** one image is written from the flash base and read back: 0xFF up to the BIN's place (`install` above), the candidate bootloader, 0xFF up to the app start, then a zero page.
3. **dfu:** the UF2 drive with this board's serial is found. `INFO_UF2.TXT` must name this build's version and board, and `CURRENT.UF2` must have its size. The double-tap register is then cleared and read back, once the bootloader runs.
4. **copy:** a generated app is copied to the drive.
5. **app-ran:** the probe shows the app counting in thread mode with VTOR at the app start.
6. **reenter:** the bootloader is re-entered by the commissioned path, and the drive's `CURRENT.UF2` reads the app back.
7. **cleanup** (reported as `cleanup`, not a step, state `blinky copied`): the record's TinyUF2 is installed again as in install, DFU is found, the record's `apps/blinky.uf2` (admitted with the record: one family, every block in the app region) is copied to the drive, and the DFU device must leave and stay away for a quiet period. Any failure keeps the board held (Exit 4).

A board's evidence is scoped as the report says. "app-ran" is execution after the bootloader handoff; on a J-Link board a run triggered by the upload alone is unverified (an esptool board's app-ran observes the copied app itself over USB). "reenter" by `retained-register` is the forced-entry path, not a physical double tap.

On an esptool board, each esptool connection is a child of the runner (`esp_session.py`), and so is each USB control request (`usb_dfu.py`, pyusb):
1. **identity:** the roster's bridge selects the board (it is wired to that board only, so the chip's MAC is not checked); the chip has no secure boot, secure download or flash encryption, and flash at least the candidate's size. The MD5s of every partition the battery never writes (nvs, ota_1, ffat on the 8 MB layout) are taken as the run's snapshot, kept in the report. The session ends with a reset.
2. **install:** one connection writes the four segments, reads each back and takes the preserved regions' MD5s, then resets once. After the reset the runner compares the read-back bytes with the segments and the MD5s with the identity snapshot; any difference fails the step. The evidence lists each write's span and the 4 KiB-aligned span covering it. Blank otadata boots the factory partition, TinyUF2.
3. **dfu:** as above; `INFO_UF2.TXT` reports the app partition (ota_0) as its flash, and no register is written.
4. **copy:** `apps/dfu_runtime` from the record, plus a block carrying a fresh nonce in ota_0's last 256 bytes, where the app reads it, renumbered under one `numBlocks`; the image itself is never patched. The record is refused when the image reaches that block or TinyUF2's 64 KiB flash cache window over it (`FLASH_CACHE_SIZE`) leaves ota_0. The evidence lists the image and nonce spans and the cache windows covering them.
5. **app-ran:** the app enumerates with its own VID:PID and the board's serial on the DFU's USB path, its DFU runtime interface string read from the device is `HIL <nonce>`, and TinyUF2 stays away for a quiet period.
6. **reenter** (`dfu-detach`): DFU_DETACH to the app is acknowledged, the app leaves, TinyUF2 comes back on the same path, and `CURRENT.UF2` reads back the image and the nonce block.
7. **recopy:** a copy with a fresh nonce boots the app again.
8. **cleanup:** as on a J-Link board, with the install as in step 2: the preserved regions' MD5s after the writes, and again after the blinky copy, must equal the identity snapshot (a recovery takes it from the failed report; a manual `restore` takes MD5s before the writes in the same connection). A mismatch fails the cleanup and keeps the hold.

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
| 4 | cleanup failed; the board is held when `cleanup.heldAfter` (not under `HIL_NO_BOARD_LOCK`). From `install` or `restore`: a child survived, or a `restore` failed after it began writing; keep your hold |

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
- `fail`: `ran` and not `pass`, with a failing step other than `identity`, and that step's `detail`;
- `not-run`: `ran` false (`locked` or a refusal), or a failing `identity`, with its `detail`. `identity` runs before anything is written, so its failure is the rig's: no probe with that serial on this machine, or one unplugged or dead;
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
  - `cleanup.survivors` lists children that outlived SIGKILL (a J-Link, mtools or FAT read stuck on the device); recovery refuses while any of them is still alive.
  - tinyusb sees that holder as a battery run and waits, which is safe but means the board is out of service until recovered.
  - Do not release it by hand, and do not treat it as safe because tinyusb reflashes. The holder may stand for a stuck J-Link or mtools process.
  - Recovery is a separate `hil-operator` dispatch whose scope names forcing that board. After process, probe and host readiness are established, it runs:

    `python3 .claude/skills/hil/scripts/hil_test.py restore -b <board> --build-record <record> --recover-holder <pid> --report <reportPath> test/hil/local.json`

    `<record>` is the failed report's `firmware.buildRecord`, or a record rebuilt on the clean HEAD when it no longer verifies. The command proves that pid holds the board as the failed run's cleanup holder and that none of the run's survivors and no J-Link process on the probe is alive, restores the board while the lock stays held, and only then releases the holder. On an esptool board the restore checks the preserved regions against the snapshot in the failed report, and recovery is refused for a touched run without one or one whose regions differ from the checkout's. A candidate whose drive cannot take the blinky copy fails the restore; the board stays held until a record that can restore it is given. A second recovery of the same board while one runs is refused (exit 2).
  - If the probe cannot connect, recovery is the human's: on imxrt1060_evk, serial download mode (BOOT_MODE 01: SW7 OFF OFF OFF ON, inferred from the EVK guide); on espressif_esp32s3_devkitc_1, ROM download mode: hold Boot (SW1, GPIO0 low), press and release RST (SW2, CHIP_PU), then release Boot (DevKitC-1 schematic V1.0; the TRM's strap table also needs GPIO46 low, its default pull-down).

## Selection

`python3 .claude/skills/build/scripts/check_build.py --select-only (--diff-file <file> | --base <ref> [--worktree]) --hil-config test/hil/local.json` adds `hil.{boards, full, uncovered}`. Run the battery when `full` is set or `boards` is non-empty. An empty diff file selects nothing; a caller without the changed-file list passes `--base`. A fresh worktree, a review worktree included, needs CLAUDE.md's worktree setup (submodules and dependency links) before `check_build.py` can build in it. `uncovered` names what no roster board on this host can run; report it, never treat it as covered. An app source (`apps/`, `ports/<port>/apps/`) selects no board and is uncovered, except `dfu_runtime`, which selects the esptool boards of the ports that build it: the battery runs the bootloader with its generated fixture on J-Link boards and with `dfu_runtime` on esptool boards. The runner, the build scripts it imports and the roster (`.claude/skills/hil/scripts/`, `.claude/skills/build/scripts/`, `test/hil/*.json`) select every roster board; a wording change to this page selects none.

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
- **Bootloader:** `install` a known-good TinyUF2 BIN under the hold and observe DFU.
- **USB serial:** confirm the enumerated serial equals `uid` (sysfs or `lsusb -v`), and record the USB port paths. If it differs, fix `uid` and the rule together, reload, and `install` again; its reset re-enumerates the board and udev applies the reloaded rules, so no replug should be needed (by mechanism, not yet observed on a uid fix).
- **Cleanup:** `restore` under the hold and observe DFU leave after the blinky copy. Record the reset notes J-Link prints on install (`BENIGN`).
- **Exclusion proof:** delete the temporary rule and reload before the re-entry run below; its `dfu` step passes only when `udevadm info` on the enumerated block device shows `UDISKS_IGNORE=1` (`check_exclusive`). A host rule that ignores a whole VID, such as tinyusb's `88-tinyusb.rules` for 239a, sets the same property, so the proof cannot tell it from the serial rule; the runner still requires the serial line.
- **Loader footprint:** for each `loadbin` shape the runner issues, place sentinels just past the written range and elsewhere in its erase block. Confirm them from a fresh session before the operation under test, and again from another fresh session after it: a verify in the session that wrote them cannot show what a later operation destroys. Make the written data differ from what is on the flash, since a `loadbin` whose data already matches is skipped ("Contents already match") and erases nothing. Record the result in Limits.
- **Fixture prerequisites,** before anything executes the battery's fixture:
  - the app start meets VTOR's alignment for the fixture's vector table (`fixture()`);
  - its stack top, the `m_data` origin the runner reads (`ram_origin`) + 0x1000, is in RAM enabled when the bootloader hands off: the ROM default per read-doc, which TinyUF2 does not reconfigure (DTCM on imxrt1060_evk);
  - under a hold, a word just below that stack top takes a written value and reads it back, and then its saved value (0x20000FFC on imxrt1060_evk).
- **Re-entry:** commit the roster entry without `reentry`, build the record, release the manual hold, and run the battery in commissioning mode; it locks itself and ends with the cleanup, so it also proves the restore:

  ```bash
  python3 .claude/skills/hil/scripts/hil_test.py run -b <board> --build-record cmake-build/hil/<board>.build.json --try-reentry retained-register test/hil/local.json
  ```

  `--try-reentry` is the lead's only, and is refused once `reentry` is set. The row's `reentryDecision` names the method when the run passed or failed only at `reenter`'s `CURRENT.UF2` readback, every observation of the tried method is true (`controlBootedApp`, `dfuCameUp` and `magicConsumed` for `retained-register`), and the board was cleaned up and not held. Set `reentry` to it and commit. A null decision leaves `reentry` unset: file a `followup` issue with the observations for diagnosis, not as a diagnosed bug. When the drive copy itself fails, a fixture installed by hand with J-Link `loadbin` can isolate re-entry from the copy for diagnosis; it never sets `reentry`.
- **On an esptool board,** in place of the J-Link items: cable the native USB connector as well as the bridge's; read the chip and flash from an esptool `identity`; record the bridge serial and the chip's MAC (`uid`, TinyUF2's USB serial); `install` from the record and observe DFU, then `restore` and observe DFU leave. Re-entry is `--try-reentry dfu-detach`, whose decision needs `detachAcked`, `appLeft` and `dfuCameUp`; before setting it, repeat DFU_DETACH ten times under the hold and check the host log shows no USB reset on the DETACH transitions (USB DFU 1.1 bitWillDetach).
- **J-Link transcript shape:** that `regs` and `mem32` output parses (`after()`, `regs()`), and which reset notes are benign. A benign note is exempted by device and exact text in `BENIGN`: on MIMXRT1062xxx6A, "Could not find valid reset vector." followed by "Target halted on flash header read.", printed on every reset while the app is invalid; on MIMXRT1011DAE5A the same note on every reset of a TinyUF2 image. In a hand-written session, `-ExitOnError 0` still exits at a failed verify, before any later command runs, and leaves the target halted: resume it from a new session (`g`, or `r` then `g`), or keep verifies in a session ahead of the one that resumes.

## Limits

- Covered: imxrt1060_evk, metro_m7_1011 and espressif_esp32s3_devkitc_1 on htpc. Not covered: ports without a cmake build, lpc55 among them (no battery, `install` or `restore` for lpcxpresso55s69; its 0A silicon also hangs TinyUF2 on a UF2 copy, #500), espressif chips other than the ESP32-S3, self-update, an interrupted update, malformed UF2 input and the physical double tap.
- esptool boards: the runner needs esptool 5.2.0 and pyusb with libusb-1.0 for its own Python. Re-entry by DFU_DETACH is the only method built; the GPIO0 detection window is not. The bridge's UART carries every esptool session. A helper that survives SIGKILL is handled like a stuck J-Link, but no way to wedge one on the board was found, so that path is unit-tested only. At the end of a UF2 copy TinyUF2 restarts while the host's usb-storage is still talking to it: the host log shows a reset of that device and read errors on its block device. Seen on the S3; other ports are unchecked.
- Every probe and USB path is unverified until commissioning has run on the board, and commissioning is manual.
- The HIL's cmake image logs on the board UART: cmake builds leave `TUF2_LOG` at its default 1 (`src/board_api.h`), while make builds, the make ports' CI artifacts and the make-built releases pass 0. Its blocking writes at start, before the app jump and on DFU entry are timing the make image does not have.
- `install` from a blank board, or one whose ROM found no boot image, brings up DFU (measured on imxrt1060_evk 2026-10-12 and metro_m7_1011 2026-10-13). With no boot image a new J-Link session reads the flash wrong (imxrt1060_evk: zeros; metro_m7_1011: bytes shifted) until a `loadbin` has run; a `loadbin` compare reads it right. On metro_m7_1011, J-Link then prints "Invalid flash header detected." at the install's first reset.
- Never use a port's CMake flash or erase targets on a rig board: `tinyuf2-erase-external-jlink` erases [FLASH_BASE, FLASH_BASE + 64 KiB), the bootloader and the zero page with it.
- J-Link's QSPI loader on imxrt1060_evk is undocumented: SEGGER UM08001 has nothing on it. Measured at sampled sentinel points only:
  - the install image (the cmake BIN, 0xFF up to 0x6000C000, then the zero page, ending at 0x6000C200) left 0x6000C200 and 0x6000FF00 reading 0xFF in the same session, before any reset. Earlier, a 0.35.0 release BIN `loadbin` (30304 B) erased every point measured past it in its block (0x60007800, 0x6000A000, 0x6000C000, 0x6000C200). J-Link reports 65536 bytes per operation, so [image end, 0x60010000) is treated as lost;
  - a sentinel at 0x60010000, in the next block, survived both;
  - a zero-page `loadbin` at the flash base kept sentinels at 0x60000200, 0x6000A000, 0x6000FF00 and 0x60010000, and 16-byte sentinel `loadbin`s kept their neighbours in the same block, so what makes J-Link erase the rest of a block is not established.
  - That a candidate BIN of another length behaves the same is an inference, not a measurement.
  - That `loadbin` erases only the 64 KiB blocks its range touches, and never the chip, is an unverified premise these points support.
  Under that premise, losses stay inside [0x60000000, 0x60010000), in regions the battery rewrites or never reads, while the install span and the zero page lie in that block.
- On metro_m7_1011, same method: the install image (ending at 0x6000C200) lost 0x6000C200 and 0x6000FF00 and kept 0x60010000; a zero-page `loadbin` at 0x60000400 kept 0x60000000, 0x60000600, 0x60001100, 0x6000BF00, 0x6000FF00 and 0x60010000.
- `JLinkExe` sometimes crashes in `libjlinkarm` at the probe connect on htpc (SIGSEGV; once a glibc double-free abort); the cause is unknown. A session that crashed this way, before the target connect, runs once more after 2 s (`jlinkRetried`); a second crash fails the run. Seen in 2 of 94 runner sessions on 2026-10-12.
- A device hung mid-write makes the host controller retry its enumeration, which stalled a J-Link connect on the same hub for ~80 s (lpcxpresso55s69); that the hub is the cause is a hypothesis.
- If no cleanup holder can be forked (exit 4 with `cleanup.holder.inProcess`), the runner never exits until recovered.
- No reproducer for an instrumented build: the battery refuses a dirty build, and `install` only programs. A claim that needs one is reported pending.
