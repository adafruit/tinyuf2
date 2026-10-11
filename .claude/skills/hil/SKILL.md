---
name: hil
description: The TinyUF2 HIL contract. Use when a change needs hardware evidence on a rig board, when a debug or validation session must take, flash, restore or release a TinyUF2 rig board, or when a workflow asks for "the project's HIL contract". Runs the bootloader battery on the host's roster boards, owns the board lock, and reports pass/fail per board with target-side evidence.
---

# HIL contract

`scripts/hil_test.py` holds the mechanics: roster and source checks, firmware binding, locking, the probe and USB steps, cleanup and the JSON report. Agents call it instead of composing J-Link, mtools or lock commands. This page is the judgment.

## Host and roster

Run `hostname` first.
- `htpc`: the roster is `test/hil/local.json`, whose `host` names it; `run` refuses on any other host.
- Any other host has no TinyUF2 rig yet; ci.lan is a follow-up. An agent that cannot ask (`hil-operator`) returns an operator-authored row per requested board (Reporting) with `detail` naming the host.

A roster entry keeps tinyusb's shape (`name`, `uid`, `flasher {name, uid, args}`), so agentrc's `rtt.py`, `pc_sample.py` and `probe_state.py` resolve the probe with `--hil-config test/hil/local.json --board <name>`. Those scripts do not read the `tinyuf2` block: pass its J-Link settings yourself, `--interface swd --speed 4000` for `{"if": "SWD", "speed": "4000"}`. The `tinyuf2` block holds what only TinyUF2 needs:
- the J-Link interface and speed;
- the install and app ranges, cross-checked against the board's source before any hardware access;
- the pinned restoration image;
- the re-entry path and the recovery note.

The battery runs a board only after commissioning sets `reentry` and confirms `uid`; `install` and `restore` work without `reentry`, for commissioning. Only commissioned roster boards can be offered for a run. Adding a board is commissioning, the lead's (below), never a review-time or dispatch-time action: the runner refuses a build record from a dirty tree, an uncommitted roster entry included.

## Locks

Locks are tinyusb's: one kernel flock per board in `/tmp/tinyusb-hil-locks/`, taken through the helper the roster's `lock.helper` names. A board name is the same lock in both projects, so TinyUF2 and tinyusb runs exclude each other.
- **The battery locks itself,** as `hil_test.py`, which tinyusb's `release` refuses to kill. Never pre-hold a board you are about to run the battery on.
- **The lock fails closed.** An unusable lock dir refuses the run (exit 2); it never runs unlocked. `HIL_NO_BOARD_LOCK=1` bypasses the lock only when the task scope names forcing that board. The report then says `lockBypassed: true`.
- **Manual sessions** (hw-debugger, hw-validator):
  1. Take your own hold: `python3 <lock.helper> hold <board> --reason "<unique session reason>"`.
  2. Program a bootloader BIN, and restore the pinned one:

     ```bash
     python3 .claude/skills/hil/scripts/hil_test.py install -b <board> --firmware <bin> --sha256 <hash> --under-hold "<reason>" test/hil/local.json
     python3 .claude/skills/hil/scripts/hil_test.py restore -b <board> --under-hold "<reason>" test/hil/local.json
     ```

     `install` writes the BIN at 0x0 and a zero page at the app start, reads both back, and refuses a BIN that is outside the install range or lacks this board's `UF2_BOARD_ID`. Both need the automount exclusion rule (Commissioning). Both refuse unless the hold is provably yours: the record's reason, a live pid, a FLOCK on the lock file in that pid's own fds, and a failing probe of the flock.
  3. Release with `python3 <lock.helper> release <board>`, only after a `restore` that exited 0 with no `survivors`. Otherwise the board is not restored: keep the hold and report it as a blocker.

  Manual exits: 0 the operation succeeded (for `restore`, the board is restored and in DFU with the pinned version); 1 it failed and the board's state is unknown; 2 refused before any hardware access; 4 a child survived SIGKILL, so keep the hold until it is gone.

  On a refused hold, report the holder from `python3 <lock.helper> status` (no board argument; it prints every holder); never kill it. A `hil_test.py` holder whose record has `role: cleanup-holder` never frees on its own: report it as a blocker that needs the recovery dispatch (Exit 4), without waiting. Any other `hil_test.py` holder is a battery run; wait for it within the lock-wait budget.
- **Restoration firmware** for a hw-validator or hw-debugger dispatch is the roster's `tinyuf2.restore` (`bin`, `sha256`, `version`). `restore --under-hold` programs and verifies it, and its `restored.evidence` (DFU with that version on the board's serial) is the run-state observation that Cleanup records.
- **Lock-wait budget:** htpc has no CI runner, so it is the dev-bench row of chief's budget, 2 min, unless the dispatch names another.

## Run the battery

```bash
mkdir -p cmake-build/hil
python3 .claude/skills/build/scripts/check_build.py --board <board> --shared > cmake-build/hil/<board>.build.json
python3 .claude/skills/hil/scripts/hil_test.py run -b <board> --build-record cmake-build/hil/<board>.build.json test/hil/local.json
```

- **Admission.** Before taking the lock the run checks the host, the automount exclusion rule, and every span it could write, the candidate's and the restoration image's (BIN, zero page, ceiling, board id, version, pinned hash), so a run never discovers an unusable recovery image after touching the board.
- **Build record.** It is this contract's build receipt: build it on the clean, pinned HEAD and pass it with `--build-record`. It must come from the make backend (the only one supported yet). The run refuses a build record that is not clean, does not match the checkout now (HEAD, submodules, `get_deps` dependencies at their pins), or whose artifacts changed since. Commit first. A debug build goes through `install`, not the battery.
- **Background.** Run it in the background; one board takes about 2 minutes. Use one board per run.
- **Selection.** There are no examples or test names to select: a run is the whole battery on one board, and the board is the only selection.

The battery's steps on one board, all under one lock:
1. **identity:** the probe is selected by serial.
2. **install:** the candidate bootloader is written with a zero page at the app start, then read back.
3. **dfu:** the UF2 drive with this board's serial is found. `INFO_UF2.TXT` must name this build's version and board, and `CURRENT.UF2` must have its size.
4. **copy:** a generated app is copied to the drive.
5. **app-ran:** the probe shows the app counting in thread mode with VTOR at the app start.
6. **reenter:** the bootloader is re-entered by the commissioned path, and the drive reads the app back.
7. **restore** (reported as `restored`, not a step): the pinned release bootloader is written, the double-tap register cleared, and DFU is observed with its version.

A board's evidence is scoped as the report says. "app-ran" is execution after the bootloader handoff; a run triggered by the upload alone is unverified. "reenter" by `retained-register` is the forced-entry path, not a physical double tap.

`--fail-at <step>` exists only for acceptance: it fails that step to exercise cleanup.

## Reporting

The last stdout line is JSON, also written to its `reportPath`; read that path, never an older report. Its fields:
- `pass`, `caveat`;
- per board: `ran`, `pass`, `locked`, `lockBypassed`, `firmware` (path, sha256, version, build record), `steps[]` (`step`, `pass`, `evidence`, `detail`), `restored` (`pass`, `state`, `heldAfter`, `holder`, `survivors`), and `detail`;
- `error` on a refusal or an operation failure.

| Exit | Meaning |
|---|---|
| 0 | every board passed and was restored |
| 1 | a board failed or did not run; it was restored or never touched |
| 2 | refused before any hardware access (usage, roster, source, build record, lock helper, lock dir) |
| 4 | cleanup failed; the board is held when `restored.heldAfter` (not under `HIL_NO_BOARD_LOCK`). From `install` or `restore`: a child survived; keep your hold until it is gone |

A delegated run (`hil-operator`) returns `{pass, results, caveat, wedged}` and, beside them, `reportPaths`:
- `pass`, `results` and `caveat` are copied verbatim from the JSON;
- `wedged` lists the boards the operator saw stop responding;
- `reportPaths` maps each board to its JSON's `reportPath`, which a recovery dispatch needs.
- With several boards, the operator runs one battery per board, one after another: `results` holds every board's row, `pass` is true only when every run's is, and `caveat` joins the runs' non-empty caveats.
- On another host, where nothing was launched, the operator writes `pass: false`, `caveat: ""` and one row per requested board, exactly `{board, ran: false, pass: false, locked: false, detail}`, with `detail` naming the host.
- A launched run that ended without printing its JSON (killed, crashed) may have programmed the board and left it unrestored. The operator writes `pass: false`, `caveat: "run ended without a report; board state unknown"` and the same row shape with `ran: null`, and `detail` naming the exit status, the output tail and `python3 <lock.helper> status` at that moment.
- The operator runs the battery once and returns. It never waits on a lock and never retries: a `locked` row comes back as is, and the caller rules below are the caller's (chief's).
- A recovery dispatch names the board, the holder pid and the failed run's `reportPath`. It runs `restore --recover-holder` in the foreground and returns `{pass, results, caveat: "", wedged, exit, error, survivors}`: that JSON's `results`, `error` (`null` when absent) and `survivors` (`[]` when absent), and the exit status. Any exit but 0 is a blocker for the caller. A probe that cannot connect is `needs-user` (ISP0 below).

### Review mapping

A review (`pr-review`) maps each board's row:
- `pass`: `ran`, `pass` and `restored.pass` all true;
- `fail`: `ran` and not `pass`, with a step whose `pass` is false, and that step's `detail`;
- `not-run`: `ran` false (`locked`, a refusal or another host), with its `detail`;
- a blocker, never a `fail` row: exit 4, `ran: null` (no report), and an abort, which is `ran` and not `pass` with no failing step (an interruption or an unexpected error, named in the board's `detail`).

`testedHead` is the build record's `input.head`. `regression` is `unknown` unless the battery also ran on the merge base.

### Caller rules
- **Retry.** A failed test may be retried once, and only when no board is `locked`, `wedged` or `heldAfter`, `caveat` is empty, and every board was restored.
  - Keep both reports. A fail-then-pass is a pass with `flaky: true`, quoting both.
  - An abort (a failed run with no failing step), a cleanup failure, `heldAfter`, `wedged` or a missing report is never retried; it is a blocker until diagnosed.
  - A board whose run ended without a report gets a manual `restore --under-hold` before its next run, and only once no such process is left on the host. Killing the runner frees its lock but not its children, which `restore` cannot see, and nothing ties a surviving child to the run that died, so the check is host-wide: any other battery, holder or J-Link session also keeps the blocker. Run this as a command of its own, since a shell line carrying the plain name would match itself; none is left when it prints nothing:

    `pgrep -ax JLinkExe; pgrep -ax mcopy; pgrep -af '[h]il_test\.py'`

    The last one also covers the runner's `fat-read` subcommand. While a process is left, or this cannot be established, the blocker stays.
- **Locked.** `locked` is an admission refusal, not a test failure. The caller admits again after the holder releases, within the lock-wait budget; the operator does not wait. Otherwise report the board not covered, naming the holder.
- **Exit 4.**
  - The board stays held by a detached holder forked from the run: reason `hil_test.py`, `role: cleanup-holder`, with its pid in `restored.holder`. It ignores SIGTERM and SIGINT, so a timeout kill cannot free the board; only recovery releases it.
  - If no holder could be forked, `restored.holder.inProcess` is set and the runner itself is the holder: it prints the report, closes its stdio and does not exit until recovered, so no completion notice arrives. When a run's notice is overdue, read the task's output: a final JSON line with `restored.holder.inProcess` true is this case. Do not wait for its exit.
  - `restored.survivors` lists children that outlived SIGKILL (a J-Link, mtools or FAT read stuck on the device); recovery refuses while any of them is still alive.
  - tinyusb sees that holder as a battery run and waits, which is safe but means the board is out of service until recovered.
  - Do not release it by hand, and do not treat it as safe because tinyusb reflashes. The holder may stand for a stuck J-Link or mtools process.
  - Recovery is a separate `hil-operator` dispatch whose scope names forcing that board. After process, probe and host readiness are established, it runs:

    `python3 .claude/skills/hil/scripts/hil_test.py restore -b <board> --recover-holder <pid> --report <reportPath> test/hil/local.json`

    The command proves that pid holds the board as the failed run's cleanup holder and that none of the run's survivors and no J-Link process on the probe is alive, restores and verifies while the lock stays held, and only then releases the holder.
  - If the probe cannot connect, a human holds ISP0 (PIO0_5) low at reset; that recovery is the human's.

## Selection

`python3 .claude/skills/build/scripts/check_build.py --select-only (--diff-file <file> | --base <ref> [--worktree]) --hil-config test/hil/local.json` adds `hil.{boards, full, uncovered}`. Run the battery when `full` is set or `boards` is non-empty. An empty diff file selects nothing; a caller without the changed-file list passes `--base`. A fresh worktree, a review worktree included, needs CLAUDE.md's worktree setup (submodules and dependency links) before `check_build.py` can build in it. `uncovered` names what no roster board on this host can run; report it, never treat it as covered. The runner and roster (`.claude/skills/hil/scripts/`, `test/hil/*.json`) select every roster board; a wording change to this page selects none.

## Commissioning a board

Commissioning is the lead's, done interactively under a manual hold, not an agent's; a `commission` subcommand that does the probe work is pending, to be written and validated on the first board. Record each result in the board's commissioning note (agentrc `target-debug` project notes) and the roster. In this order:
- **Automount exclusion:** `/etc/udev/rules.d/99-tinyuf2-hil.rules`, one line per board, in exactly this form (the runner accepts only this form, with exact `==` matches):

  ```
  SUBSYSTEM=="block", ATTRS{idVendor}=="1fc9", ATTRS{idProduct}=="0094", ATTRS{serial}=="<uid>", ENV{UDISKS_IGNORE}="1"
  ```

  Write it with the roster's `uid`, before the serial can be confirmed: `install`, `restore` and `run` refuse without the rule, and a fresh board runs whatever tinyusb last flashed, not TinyUF2. A serial a running tinyusb example reports (`lsusb -v`) is an early cross-check, not a confirmation. Until the serial is confirmed, also inhibit automount for every board of this VID:PID with a temporary `/etc/udev/rules.d/98-tinyuf2-hil-commissioning.rules`:

  ```
  SUBSYSTEM=="block", ATTRS{idVendor}=="1fc9", ATTRS{idProduct}=="0094", ENV{UDISKS_IGNORE}="1"
  ```

  Then `sudo udevadm control --reload`.
- **Recovery:** `restore --under-hold` the pinned image and observe DFU with its version.
- **USB serial:** confirm the enumerated 1fc9:0094 serial equals `uid` (sysfs or `lsusb -v`), and record the USB port paths. If it differs, the restore cannot have observed DFU: fix `uid` and the rule together, reload, replug and restore again.
- **Exclusion proof:** delete the temporary rule, reload, and `restore` once more: it passes only when `udevadm info` on the enumerated block device shows `UDISKS_IGNORE=1` from the serial rule alone (`check_exclusive`).
- **Loader footprint:** one sentinel per programming operation; a page just past each written range must keep its pattern. Without SEGGER UM08001 the general footprint stays "documentation unavailable".
- **Re-entry path**, with a valid application running, since the bootloader enters DFU for an invalid one before it reads the double-tap register (`src/main.c`):
  1. Install the counter fixture through the drive and observe it running, as the battery's copy and app-ran steps do.
  2. Save GPREG[6], write a sentinel to it, and verify the write.
  3. Write the double-tap magic to the double-tap register, then SYSRESETREQ.
  4. Record separately whether the sentinel survived and whether DFU came up.
  5. Restore GPREG[6] to its saved value, on every path, failures included.

  Set `reentry: retained-register` only when the sentinel survived and DFU came up. Any other result leaves `reentry` unset: file a `followup` issue with the observations for diagnosis, not as a diagnosed bug. `app-invalidate` is set only after that path is validated on its own.
- **J-Link transcript shape:** that `regs` and `mem32` output parses (`after()`, `regs()`).

## Limits

- Not covered: self-update, an interrupted update, malformed UF2 input, the physical double tap, and boards other than lpcxpresso55s69.
- Every probe and USB path is unverified until commissioning has run on the board.
- If no cleanup holder can be forked (exit 4 with `restored.holder.inProcess`), the runner never exits until recovered.
- No reproducer for an instrumented build: the battery refuses a dirty build, and `install` only programs. A claim that needs one waits for the `commission` subcommand's steps, or is reported pending.
