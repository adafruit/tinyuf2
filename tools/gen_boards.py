#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path


BOARD_H_GLOB = "ports/*/boards/*/board.h"
SKIP_FAMILIES = {"test_ghostfat", "template_port"}
SKIP_BOARDS = {"ch32v203_r0_1v0"}
# listing fixes for boards whose board.h strings are shared with another board and stay as the device reports them
BOARD_OVERRIDES = {
    "m5stack_dial": {"name": "M5Stack Dial", "url": "https://docs.m5stack.com/en/core/M5Dial"},
}


def _first_match(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, flags=re.MULTILINE)
    return match.group(1).strip() if match else None


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    value = value.strip()
    if value.lower().startswith("0x"):
        try:
            return int(value, 16)
        except ValueError:
            return None
    try:
        return int(value, 10)
    except ValueError:
        return None


def _fmt_vid_pid(vid: int | None, pid: int | None) -> str:
    if vid is None or pid is None:
        return "N/A"
    return f"0x{vid:04X}:0x{pid:04X}"


def _escape_md(value: str) -> str:
    return value.replace("|", "\\|")


def _load_board(board_h: Path, repo_root: Path, text: str | None = None) -> dict[str, str]:
    if text is None:
        text = board_h.read_text(errors="ignore")
    rel = board_h.relative_to(repo_root)
    parts = rel.parts
    family = parts[1] if len(parts) >= 4 else "unknown"
    board = parts[3] if len(parts) >= 4 else board_h.parent.name

    if family in SKIP_FAMILIES or board in SKIP_BOARDS:
        return {}

    vid = _parse_int(_first_match(r"^\s*#define\s+USB_VID\s+([0-9A-Fa-fxX]+)", text))
    pid = _parse_int(_first_match(r"^\s*#define\s+USB_PID\s+([0-9A-Fa-fxX]+)", text))
    manufacturer = _first_match(r'^\s*#define\s+USB_MANUFACTURER\s+"([^"]+)"', text)
    product = _first_match(r'^\s*#define\s+USB_PRODUCT\s+"([^"]+)"', text)
    name = None
    if manufacturer and product:
        name = f"{manufacturer} {product}"
    elif product:
        name = product
    elif manufacturer:
        name = manufacturer
    else:
        name = _first_match(r'^\s*#define\s+UF2_PRODUCT_NAME\s+"([^"]+)"', text)

    url = _first_match(r'^\s*#define\s+UF2_INDEX_URL\s+"([^"]+)"', text)

    return {
        "family": family,
        "board": board,
        "name": name or "N/A",
        "vid_pid": _fmt_vid_pid(vid, pid),
        "url": url or "N/A",
        **BOARD_OVERRIDES.get(board, {}),
    }


def indexed_board_headers(repo_root: Path) -> dict[Path, str | None]:
    """Each indexed board.h with its index content where the worktree cannot give it, else None."""
    # a hook under `git --literal-pathspecs commit` inherits GIT_LITERAL_PATHSPECS=1, which would match no glob
    out = subprocess.run(["git", "ls-files", "-t", "-z", "--", f":(glob){BOARD_H_GLOB}"], cwd=repo_root,
                         env={**os.environ, "GIT_LITERAL_PATHSPECS": "0"}, capture_output=True, check=True).stdout
    headers: dict[Path, str | None] = {}
    for tag_name in out.decode().split("\0"):
        if not tag_name:
            continue
        tag, name = tag_name.split(" ", 1)
        path = repo_root / name
        # a sparse checkout's skip-worktree entry is absent from the worktree but still a board
        if tag == "S":
            headers[path] = subprocess.run(["git", "show", f":{name}"], cwd=repo_root, capture_output=True,
                                           check=True).stdout.decode(errors="ignore")
        # run --all-files does not stash, so an unstaged deletion leaves an indexed header missing from the worktree
        elif path.is_file():
            headers[path] = None
    return headers


def generate(repo_root: Path, output: Path, board_headers: dict[Path, str | None] | None = None) -> None:
    boards: dict[str, list[dict[str, str]]] = {}
    if board_headers is None:
        board_headers = dict.fromkeys(repo_root.glob(BOARD_H_GLOB))
    for board_h in sorted(board_headers):
        entry = _load_board(board_h, repo_root, board_headers[board_h])
        if not entry:
            continue
        boards.setdefault(entry["family"], []).append(entry)

    lines: list[str] = []
    lines.append("# Supported Boards")
    lines.append("")
    for family in sorted(boards.keys(), key=str.lower):
        lines.append(f"## {family}")
        lines.append("")
        lines.append("| Board | Name | VID PID | URL |")
        lines.append("| --- | --- | --- | --- |")
        for entry in sorted(boards[family], key=lambda e: e["board"].lower()):
            lines.append(
                f"| {_escape_md(entry['board'])} | {_escape_md(entry['name'])} | "
                f"{_escape_md(entry['vid_pid'])} | {_escape_md(entry['url'])} |"
            )
        lines.append("")

    output.write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate supported_boards.md from ports/*/boards/*/board.h"
    )
    parser.add_argument(
        "--output",
        default="supported_boards.md",
        help="Output markdown file (default: supported_boards.md)",
    )
    parser.add_argument(
        "--require-indexed",
        action="store_true",
        help="Fail unless the output is in git's index (for the pre-commit hook)",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    output = Path(args.output)
    if not output.is_absolute():
        output = repo_root / output

    # the hook lists the index, so an untracked board.h neither fails an unrelated commit nor enters the list
    generate(repo_root, output, indexed_board_headers(repo_root) if args.require_indexed else None)
    # pre-commit's diff check ignores untracked files, so a recreated list would otherwise pass
    if args.require_indexed and subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", str(output)], cwd=repo_root, capture_output=True
    ).returncode:
        sys.exit(f"{output} is not in git's index; add it")


if __name__ == "__main__":
    main()
