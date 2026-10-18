# TinyUF2 Agent Instructions

## Working Rules

- Worktrees — `git submodule update --init lib/tinyusb lib/uf2 lib/agentrc`, then symlink the `deps_all` paths from `tools/get_deps.py` (`lib/mcu/...`, `lib/sct_neopixel`) to the primary checkout when it holds the pinned revisions. `get_deps.py` refuses to update through a symlink; fetch the pinned revision in the primary checkout before linking it. Where the primary's copy has local changes or another revision, use a detached `git worktree` of that dependency at its pin instead, outside the checkout and symlinked in.
- Code references — ports and boards: `ports/<port>/` (`boards/<board>/`, `board_flash.c`, `boards.c`), `supported_boards.md`; bootloader: `src/` (`main.c`, `ghostfat.c`, `msc.c`, `board_api.h`, the contract every port implements); apps: `apps/`, `ports/<port>/apps/`; build: `ports/make.mk`, `ports/rules.mk`, `ports/family_support.cmake`, `.github/workflows/build.yml` (which backend builds each port); deps: `tools/get_deps.py`.

## Code Rules

- Formatting follows `.clang-format`: 2-space indent, no tabs.
- Port-specific code stays in `ports/<port>/` behind the `board_api.h` interface.
- Some files use CRLF line endings; keep each file's own line endings when editing.

## Skills

- Agents, skills and workflows beyond this repo's `.claude/` come from [agentrc](https://github.com/hathach/agentrc); install it before agent work on TinyUF2.
- Skill script tests live in `.claude/test/test_*.py`; pre-commit runs them.
- Hardware diagnosis and repair use agentrc's `hw-debugger`; independent hardware claims and committed-fix validation use `hw-validator`; routine HIL runs use `hil-operator` — all orchestrated by `chief`.
- Bootloader audit: the `code-audit` workflow with `dirs` (e.g. `src`, `ports/<port>`) and `dimensions`: `UF2 and MSC input: block validation, bounds and arithmetic, completion and error paths`; `flash and app boundaries: erase/write range and alignment, write protection, update integrity and recovery`; `boot decisions and app handoff: app validity, double-tap and reset reasons, jump, vector table, peripheral teardown`; `ISR and shared state, and register use vs reference manual and errata: cross-check the reference manual AND errata sheets via the read-doc skill; a lookup that cannot run is pending and its conclusion unverified (never a web/filesystem substitute); a missing erratum workaround is a finding`; `build and configuration: the backend CI uses per port, board and config selection, code only some configurations compile`; `style: repo conventions and line endings`.

## Build and Validate

- Build contract: `.claude/skills/build/SKILL.md`. It resolves a change to boards and builds each the way CI does, outside the source tree.
- HIL contract: `.claude/skills/hil-contract/SKILL.md`. Hardware validation comes from its report, never from a build; what no roster board on the host covers is reported pending.
- ESP-IDF: the build contract uses CI's docker image; for interactive work, `. "$IDF_PATH/export.sh"` and `idf.py -C ports/espressif -DBOARD=<board> flash monitor`.
- Before submitting, and again after a rebase: `pre-commit run --all-files`.
- For code changes: `python3 .claude/skills/build/scripts/check_build.py --base master --worktree`.

## PRs and Follow-ups

- Before opening or updating a PR, follow Build and Validate.
- After opening a PR, ask the human to authorize one headless `chief` invocation to drive reviews and CI to green under agentrc chief's Authorization exception. Name the PR URL, head repository and branch, and actions: push commits to that branch, post replies to the PR's review feedback, and resolve review threads through `pr-babysit` with `autoPush: true`. On an affirmative answer, launch it in the PR worktree through agentrc's `headless-chief` skill (`chief_run.py`), never a bare `claude -p`, and relay its exit as that skill directs. The task names the PR, head repository and branch, expected HEAD and scope, and includes the question and answer verbatim; a relaunch for the same PR may carry that exchange copied verbatim from the earlier launch task. Leave the checkout to chief until it exits. TinyUF2 `pr-babysit` args:
  `{"pr": <num>, "protected": "^(lib/(tinyusb|uf2)|test/hil/[^/]+\\.json)$"}`; reviewers are agentrc's default.
  (`protected` keeps the submodule pins and the HIL rosters out of automated fixes).
- The follow-up label is `followup`.
