---
name: hil
description: The TinyUF2 HIL contract. Use when a change needs hardware evidence on a rig board, when a debug or validation session must take, flash, clean up or release a TinyUF2 rig board, or when a workflow asks for "the project's HIL contract". Runs the bootloader battery on the host's roster boards, owns the board lock, and reports pass/fail per board with target-side evidence.
---

# HIL contract

`scripts/hil_test.py` holds the mechanics: roster and source checks, firmware binding, locking, the probe and USB steps, cleanup and the JSON report. Agents call it instead of composing J-Link, mtools or lock commands. This page is the judgment.

## Host and roster

Run `hostname` first.
- `htpc`: the roster is `test/hil/local.json`, whose `host` names it; `run` refuses on any other host.
- `TINYUSB_DIR` must name the tinyusb checkout whose `test/hil/helper/hil_lock.py` owns the board locks; every command refuses without it. Set it in the login profile, which headless sessions (chief, `hil-operator`) inherit.
- Any other host has no TinyUF2 rig yet; ci.lan is a follow-up. An agent that cannot ask (`hil-operator`) returns an operator-authored row per requested board (Reporting) with `detail` naming the host.

A roster entry is named by its TinyUF2 board (`ports/<port>/boards/<name>`, which also gives the port) and keeps tinyusb's shape (`name`, `uid`, `flasher {name, uid, args}`), so agentrc's `rtt.py`, `pc_sample.py` and `probe_state.py` resolve the probe with `--hil-config test/hil/local.json --board <name>`. The runner uses SWD at 4000 kHz; pass the same to those scripts, `--interface swd --speed 4000`. The roster holds the board's hardware only; layouts come from the candidate's source. The `tinyuf2` block holds:
- the board lock name (`lock`) when tinyusb names the board differently, as `mimxrt1060_evk` for `imxrt1060_evk`; both runners take that one lock, and the helper's `status`, holder records and the report rows' `lock` show it. It defaults to the board name;
- the commissioned re-entry path (`reentry`).

The battery runs a board only after commissioning sets `reentry` and confirms `uid`; `install` and `invalidate` work without `reentry`, for commissioning. Only commissioned roster boards can be offered for a run. Adding a board is commissioning, the lead's (below), never a review-time or dispatch-time action: the runner refuses a build record from a dirty tree, an uncommitted roster entry included.

## Locks

Locks are tinyusb's: one kernel flock per board in `/tmp/tinyusb-hil-locks/`, taken through `$TINYUSB_DIR/test/hil/helper/hil_lock.py`. A board's lock is `<lock>`: its roster `tinyuf2.lock`, else the board name. It is tinyusb's name for the board, so TinyUF2 and tinyusb runs exclude each other; the helper's `hold` and `release` take it and `status` (no board argument) shows it, while `hil_test.py -b` and the probe scripts take the board name.
- **The battery locks itself,** as `hil_test.py`, which tinyusb's `release` refuses to kill. Never pre-hold a board you are about to run the battery on.
- **The lock fails closed.** An unusable lock dir refuses the run (exit 2); it never runs unlocked. `HIL_NO_BOARD_LOCK=1` bypasses the lock only when the task scope names forcing that board. The report then says `lockBypassed: true`.
- **Manual sessions** (hw-debugger, hw-validator):
  1. Take your own hold: `python3 $TINYUSB_DIR/test/hil/helper/hil_lock.py hold <lock> --reason "<unique session reason>"`.
  2. Program a bootloader BIN, and invalidate the board when done:

     ```bash
     python3 .claude/skills/hil/scripts/hil_test.py install -b <board> --firmware <bin> --sha256 <hash> --under-hold "<reason>" test/hil/local.json
     python3 .claude/skills/hil/scripts/hil_test.py invalidate -b <board> --under-hold "<reason>" test/hil/local.json
     ```

     `install` writes one image from the board's flash base (the BIN, 0xFF up to the app start, then a zero page), reads it back, and refuses a BIN that is outside the install range or lacks this board's `UF2_BOARD_ID`; it needs the automount exclusion rule (Commissioning). `invalidate` is the cleanup (step 7 below). Both refuse unless the hold is provably yours: the record's reason, a live pid, a FLOCK on the lock file in that pid's own fds, and a failing probe of the flock.
  3. Release with `python3 $TINYUSB_DIR/test/hil/helper/hil_lock.py release <lock>`, only after an `invalidate` that exited 0 with no `survivors`. Otherwise the board is not cleaned up: keep the hold and report it as a blocker.

  Manual exits: 0 the operation succeeded (for `invalidate`, the zero page at the flash floor verified from a new session); 1 it failed and the board's state is unknown; 2 refused before any hardware access; 4 a child survived SIGKILL, so keep the hold until it is gone.

  On a refused hold, report the holder from `python3 $TINYUSB_DIR/test/hil/helper/hil_lock.py status` (no board argument; it prints every holder); never kill it. A `hil_test.py` holder whose record has `role: cleanup-holder` never frees on its own: report it as a blocker that needs the recovery dispatch (Exit 4), without waiting. Any other `hil_test.py` holder is a battery run; wait for it within the lock-wait budget.
- **Cleanup state** for a hw-validator or hw-debugger dispatch: no firmware is restored. `invalidate --under-hold` leaves the board unbootable, and its `cleanup.evidence` (the zero page at the flash floor verified from a new session after the reset) is the observation that Cleanup records. Whoever uses the board next flashes it first; tinyusb's HIL does.
- **Lock-wait budget:** htpc has no CI runner, so it is the dev-bench row of chief's budget, 2 min, unless the dispatch names another.

## Run the battery

```bash
mkdir -p cmake-build/hil
python3 .claude/skills/build/scripts/check_build.py --board <board> --backend cmake --shared > cmake-build/hil/<board>.build.json
python3 .claude/skills/hil/scripts/hil_test.py run -b <board> --build-record cmake-build/hil/<board>.build.json test/hil/local.json
```

`<board>` is the roster name, the TinyUF2 board name.

- **Admission.** Before taking the lock the run checks the host, the automount exclusion rule, and every span it could write (BIN, zero page, the device's flash limits, board id), with the install and app spans taken from the candidate's source.
- **Build record.** It is this contract's build receipt: build it on the clean, pinned HEAD and pass it with `--build-record`. It must be a cmake build (`--backend cmake`), whatever backend CI builds the port with; board facts are read from the port's CMake files too. The run refuses a build record that is not clean, does not match the checkout now (HEAD, submodules, `get_deps` dependencies at their pins), or whose artifacts changed since. Commit first. A debug build goes through `install`, not the battery.
- **Background.** Run it in the background; one board takes about 2 minutes. Use one board per run.
- **Selection.** There are no examples or test names to select: a run is the whole battery on one board, and the board is the only selection.

The battery's steps on one board, all under one lock:
1. **identity:** the probe is selected by serial.
2. **install:** one image is written from the flash base and read back: the candidate bootloader, 0xFF up to the app start, then a zero page.
3. **dfu:** the UF2 drive with this board's serial is found. `INFO_UF2.TXT` must name this build's version and board, and `CURRENT.UF2` must have its size.
4. **copy:** a generated app is copied to the drive.
5. **app-ran:** the probe shows the app counting in thread mode with VTOR at the app start.
6. **reenter:** the bootloader is re-entered by the commissioned path, and the drive's `CURRENT.UF2` reads the app back.
7. **cleanup** (reported as `cleanup`, not a step): a zero page is written at the device's flash floor (`FLASH_LIMITS`, never the candidate's layout) and read back, the target reset, and the zero page verified again from a new session, so the board boots nothing (on MIMXRT1062 with BOOT_MODE 10b, Internal Boot, an error falls to the Serial Downloader: IMXRT1060RM rev 4 §9.3.5 p199). The double-tap register is cleared in `dfu` instead, once the bootloader runs.

A board's evidence is scoped as the report says. "app-ran" is execution after the bootloader handoff; a run triggered by the upload alone is unverified. "reenter" by `retained-register` is the forced-entry path, not a physical double tap.

`--fail-at <step>` exists only for acceptance: it fails that step to exercise cleanup.

## Reporting

The last stdout line is JSON, also written to its `reportPath`; read that path, never an older report. Its fields:
- `pass`, `caveat`;
- per board: `ran`, `pass`, `locked`, `lockBypassed`, `firmware` (path, sha256, version, build record), `steps[]` (`step`, `pass`, `evidence`, `detail`), `cleanup` (`pass`, `state`, `evidence`, `heldAfter`, `holder`, `survivors`), `jlinkRetried` (J-Link sessions run again after a crash before the target connect; Limits), and `detail`;
- `error` on a refusal or an operation failure.

| Exit | Meaning |
|---|---|
| 0 | every board passed and was cleaned up |
| 1 | a board failed or did not run; it was cleaned up or never touched |
| 2 | refused before any hardware access (usage, roster, source, build record, lock helper, lock dir) |
| 4 | cleanup failed; the board is held when `cleanup.heldAfter` (not under `HIL_NO_BOARD_LOCK`). From `install` or `invalidate`: a child survived; keep your hold until it is gone |

A delegated run (`hil-operator`) returns `{pass, results, caveat, wedged}` and, beside them, `reportPaths`:
- `pass`, `results` and `caveat` are copied verbatim from the JSON;
- `wedged` lists the boards the operator saw stop responding;
- `reportPaths` maps each board to its JSON's `reportPath`, which a recovery dispatch needs.
- With several boards, the operator runs one battery per board, one after another: `results` holds every board's row, `pass` is true only when every run's is, and `caveat` joins the runs' non-empty caveats.
- On another host, where nothing was launched, the operator writes `pass: false`, `caveat: ""` and one row per requested board, exactly `{board, ran: false, pass: false, locked: false, detail}`, with `detail` naming the host.
- A launched run that ended without printing its JSON (killed, crashed) may have programmed the board and left it running a candidate. The operator writes `pass: false`, `caveat: "run ended without a report; board state unknown"` and the same row shape with `ran: null`, and `detail` naming the exit status, the output tail and `python3 $TINYUSB_DIR/test/hil/helper/hil_lock.py status` at that moment.
- The operator runs the battery once and returns. It never waits on a lock and never retries: a `locked` row comes back as is, and the caller rules below are the caller's (chief's).
- A recovery dispatch names the board, the holder pid and the failed run's `reportPath`. It runs `invalidate --recover-holder` in the foreground and returns `{pass, results, caveat: "", wedged, exit, error, survivors}`: that JSON's `results`, `error` (`null` when absent) and `survivors` (`[]` when absent), and the exit status. Any exit but 0 is a blocker for the caller. A probe that cannot connect is `needs-user` (the board's recovery note, Exit 4).

### Review mapping

A review (`pr-review`) maps each board's row, except a commissioning run's (`commissioning: true`, from `--try-reentry`), which is never validation:
- `pass`: `ran`, `pass` and `cleanup.pass` all true;
- `fail`: `ran` and not `pass`, with a step whose `pass` is false, and that step's `detail`;
- `not-run`: `ran` false (`locked`, a refusal or another host), with its `detail`;
- a blocker, never a `fail` row: exit 4, `ran: null` (no report), and an abort, which is `ran` and not `pass` with no failing step (an interruption or an unexpected error, named in the board's `detail`).

`testedHead` is the build record's `input.head`. `regression` is `unknown` unless the battery also ran on the merge base.

### Caller rules
- **Retry.** A failed test may be retried once, and only when no board is `locked`, `wedged` or `heldAfter`, `caveat` is empty, and every board was cleaned up.
  - Keep both reports. A fail-then-pass is a pass with `flaky: true`, quoting both.
  - An abort (a failed run with no failing step), a cleanup failure, `heldAfter`, `wedged` or a missing report is never retried; it is a blocker until diagnosed.
  - A board whose run ended without a report gets a manual `invalidate --under-hold` before its next run, and only once no such process is left on the host. Killing the runner frees its lock but not its children, which `invalidate` cannot see, and nothing ties a surviving child to the run that died, so the check is host-wide: any other battery, holder or J-Link session also keeps the blocker. Run this as a command of its own, since a shell line carrying the plain name would match itself; none is left when it prints nothing:

    `pgrep -ax JLinkExe; pgrep -ax mcopy; pgrep -af '[h]il_test\.py'`

    The last one also covers the runner's `fat-read` subcommand. While a process is left, or this cannot be established, the blocker stays.
- **Locked.** `locked` is an admission refusal, not a test failure. The caller admits again after the holder releases, within the lock-wait budget; the operator does not wait. Otherwise report the board not covered, naming the holder.
- **Exit 4.**
  - The board stays held by a detached holder forked from the run: reason `hil_test.py`, `role: cleanup-holder`, with its pid in `cleanup.holder`. It ignores SIGTERM and SIGINT, so a timeout kill cannot free the board; only recovery releases it.
  - If no holder could be forked, `cleanup.holder.inProcess` is set and the runner itself is the holder: it prints the report, closes its stdio and does not exit until recovered, so no completion notice arrives. When a run's notice is overdue, read the task's output: a final JSON line with `cleanup.holder.inProcess` true is this case. Do not wait for its exit.
  - `cleanup.survivors` lists children that outlived SIGKILL (a J-Link, mtools or FAT read stuck on the device); recovery refuses while any of them is still alive.
  - tinyusb sees that holder as a battery run and waits, which is safe but means the board is out of service until recovered.
  - Do not release it by hand, and do not treat it as safe because tinyusb reflashes. The holder may stand for a stuck J-Link or mtools process.
  - Recovery is a separate `hil-operator` dispatch whose scope names forcing that board. After process, probe and host readiness are established, it runs:

    `python3 .claude/skills/hil/scripts/hil_test.py invalidate -b <board> --recover-holder <pid> --report <reportPath> test/hil/local.json`

    The command proves that pid holds the board as the failed run's cleanup holder and that none of the run's survivors and no J-Link process on the probe is alive, invalidates and verifies while the lock stays held, and only then releases the holder.
  - If the probe cannot connect, recovery is the human's: on imxrt1060_evk, serial download mode (BOOT_MODE 01: SW7 OFF OFF OFF ON, inferred from the EVK guide).

## Selection

`python3 .claude/skills/build/scripts/check_build.py --select-only (--diff-file <file> | --base <ref> [--worktree]) --hil-config test/hil/local.json` adds `hil.{boards, full, uncovered}`. Run the battery when `full` is set or `boards` is non-empty. An empty diff file selects nothing; a caller without the changed-file list passes `--base`. A fresh worktree, a review worktree included, needs CLAUDE.md's worktree setup (submodules and dependency links) before `check_build.py` can build in it. `uncovered` names what no roster board on this host can run; report it, never treat it as covered. The runner and roster (`.claude/skills/hil/scripts/`, `test/hil/*.json`) select every roster board; a wording change to this page selects none.

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
- **Cleanup:** `invalidate` under the hold, then confirm from a new session the zero page at the flash floor and the ROM fallback (on MIMXRT1062, the serial downloader's USB device on the board's port), and that `install` succeeds from that state and DFU comes up. Record the reset notes J-Link prints with no boot image (`BENIGN`).
- **Exclusion proof:** delete the temporary rule and reload before the re-entry run below; its `dfu` step passes only when `udevadm info` on the enumerated block device shows `UDISKS_IGNORE=1` (`check_exclusive`). A host rule that ignores a whole VID, such as tinyusb's `88-tinyusb.rules` for 239a, sets the same property, so the proof cannot tell it from the serial rule; the runner still requires the serial line.
- **Loader footprint:** for each `loadbin` shape the runner issues, place sentinels just past the written range and elsewhere in its erase block. Confirm them from a fresh session before the operation under test, and again from another fresh session after it: a verify in the session that wrote them cannot show what a later operation destroys. Make the written data differ from what is on the flash, since a `loadbin` whose data already matches is skipped ("Contents already match") and erases nothing. Record the result in Limits.
- **Fixture prerequisites,** before anything executes the battery's fixture:
  - the app start meets VTOR's alignment for the fixture's vector table (`fixture()`);
  - its stack top, the `m_data` origin the runner reads (`ram_origin`) + 0x1000, is in RAM enabled when the bootloader hands off: the ROM default per read-doc, which TinyUF2 does not reconfigure (DTCM on imxrt1060_evk);
  - under a hold, a word just below that stack top takes a written value and reads it back, and then its saved value (0x20000FFC on imxrt1060_evk).
- **Re-entry:** commit the roster entry without `reentry`, build the record, release the manual hold, and run the battery in commissioning mode; it locks itself and ends with the cleanup, so it also proves a run from and back to an invalidated board:

  ```bash
  python3 .claude/skills/hil/scripts/hil_test.py run -b <board> --build-record cmake-build/hil/<board>.build.json --try-reentry retained-register test/hil/local.json
  ```

  `--try-reentry` is the lead's only, and is refused once `reentry` is set. The row's `reentryDecision` names the method when the run passed or failed only at `reenter`'s `CURRENT.UF2` readback, every observation of the tried method is true (`controlBootedApp`, `dfuCameUp` and `magicConsumed` for `retained-register`), and the board was cleaned up and not held. Set `reentry` to it and commit. A null decision leaves `reentry` unset: file a `followup` issue with the observations for diagnosis, not as a diagnosed bug. `app-invalidate` is set only after that path is validated on its own. When the drive copy itself fails, a fixture installed by hand with J-Link `loadbin` can isolate re-entry from the copy for diagnosis; it never sets `reentry`.
- **J-Link transcript shape:** that `regs` and `mem32` output parses (`after()`, `regs()`), and which reset notes are benign. A benign note is exempted by device and exact text in `BENIGN`: on MIMXRT1062xxx6A, "Could not find valid reset vector." followed by "Target halted on flash header read.", printed on every reset while the app is invalid. In a hand-written session, `-ExitOnError 0` still exits at a failed verify, before any later command runs, and leaves the target halted: resume it from a new session (`g`, or `r` then `g`), or keep verifies in a session ahead of the one that resumes.

## Limits

- Covered: imxrt1060_evk on htpc. Not covered: ports without a cmake build, lpc55 among them (no battery, `install` or `invalidate` for lpcxpresso55s69; its 0A silicon also hangs TinyUF2 on a UF2 copy, #500), ESP32 boards (#502), self-update, an interrupted update, malformed UF2 input and the physical double tap.
- Every probe and USB path is unverified until commissioning has run on the board, and commissioning is manual.
- The HIL's cmake image logs on the board UART: cmake builds leave `TUF2_LOG` at its default 1 (`src/board_api.h`), while make builds, the make ports' CI artifacts and the make-built releases pass 0. Its blocking writes at start, before the app jump and on DFU entry are timing the make image does not have.
- Cleanup leaves the board unbootable, so the next user, tinyusb's HIL included, must flash before it runs anything. The cleanup's zero-page write at the flash floor is a loader shape not yet measured on imxrt1060_evk: what else it erases, the reset notes J-Link prints with no boot image, and an `install` from that state are pending its commissioning (Commissioning, Cleanup).
- Never use a port's CMake flash or erase targets on a rig board: `tinyuf2-erase-external-jlink` erases [FLASH_BASE, FLASH_BASE + 64 KiB), the bootloader and the zero page with it.
- J-Link's QSPI loader on imxrt1060_evk is undocumented: SEGGER UM08001 has nothing on it. Measured at single sentinel points, with the 0.35.0 release BIN (30304 B) only:
  - a BIN `loadbin` at 0x60000000 erased every point measured past the BIN in its block (0x60007800, 0x6000A000, the zero page at 0x6000C000, 0x6000C200), and J-Link reports 65536 bytes per operation, so [BIN end, 0x60010000) is treated as lost;
  - a sentinel at 0x60010000, in the next block, survived a BIN `loadbin`;
  - a zero-page `loadbin`, after a bootloader written in an earlier session, kept the whole bootloader (`verifybin`) and a sentinel at 0x6000A000.
  - That a candidate BIN of another length behaves the same is an inference, not a measurement.
  - That `loadbin` erases only the 64 KiB blocks its range touches, and never the chip, is an unverified premise these points support.
  Under that premise, losses stay inside [0x60000000, 0x60010000), in regions the battery rewrites or never reads, while the install span and the zero page lie in that block.
- `JLinkExe` intermittently crashes in `libjlinkarm` at the probe connect on htpc; the cause is unknown. On 2026-10-12 it crashed in 2 of the runner's 94 sessions and once in a hand session, against 30 clean back-to-back connects. Two of the crashes are SIGSEGV at the same offset in the kernel log; the other is a glibc "double free" abort. Both runner crashes came in a session started right after the target's UF2 drive appeared or vanished; a race in the DLL's USB scan is a hypothesis. A session that died this way (SIGSEGV or SIGABRT, the probe's `S/N:` its last J-Link line, no target connect) runs once more after 2 s, since it never reached the target (`jlinkRetried`). A second crash fails the run, and so does a session that hangs after a crash, as one cleanup did for 120 s.
- A device hung mid-write makes the host controller retry its enumeration, which stalled a J-Link connect on the same hub for ~80 s (lpcxpresso55s69); that the hub is the cause is a hypothesis.
- If no cleanup holder can be forked (exit 4 with `cleanup.holder.inProcess`), the runner never exits until recovered.
- No reproducer for an instrumented build: the battery refuses a dirty build, and `install` only programs. A claim that needs one is reported pending.
