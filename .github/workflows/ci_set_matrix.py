import argparse
import json
import sys
from pathlib import Path

# TOP is tinyuf2 root dir
TOP = Path(__file__).parent.parent.parent.resolve()
GHOSTFAT = 'test_ghostfat'


def full_matrix():
    """Every board of every port: built without the selector, so a broken one still falls back here."""
    ports_dir = Path(TOP / 'ports')
    matrix = {}
    for p in sorted(ports_dir.iterdir()):
        if p.is_dir() and p.name != 'template_port':
            matrix[p.name] = {}
            boards_dir = ports_dir / p / 'boards'
            if boards_dir.exists():
                matrix[p.name]['board'] = sorted(b.name for b in boards_dir.iterdir() if b.is_dir())
    return matrix


def narrow(full, manifest):
    """The full matrix cut to check_build.py --select-only's build.ci; ValueError when unusable."""
    if not isinstance(manifest, dict) or type(manifest.get('version')) is not int or manifest['version'] != 1:
        raise ValueError('not a v1 selection manifest')
    ci = manifest.get('build', {}).get('ci')
    if not isinstance(ci, dict) or not isinstance(ci.get('full'), bool) or not isinstance(ci.get('ghostfat'), bool) \
            or not isinstance(ci.get('ports'), dict):
        raise ValueError('no build.ci in the selection')
    if ci['full']:
        return full
    matrix = {p: ({'board': []} if 'board' in v else {}) for p, v in full.items()}
    for port, boards in ci['ports'].items():
        known = full.get(port, {}).get('board')
        if port == GHOSTFAT or known is None or not isinstance(boards, list) or not set(boards) <= set(known):
            raise ValueError(f'selection names boards the tree lacks: {port} {boards}')
        matrix[port]['board'] = sorted(boards)
    if ci['ghostfat']:
        matrix[GHOSTFAT]['board'] = full[GHOSTFAT]['board']
    return matrix


def set_matrix_json(select_file=None):
    matrix = full_matrix()
    if select_file:
        try:
            matrix = narrow(matrix, json.loads(Path(select_file).read_text()))
        except Exception as e:  # any failure builds everything rather than nothing
            # the runner reads workflow commands from stderr too, so stdout stays the JSON alone
            print(f'::warning::build selection unusable ({e}), building the full matrix', file=sys.stderr)
    print(json.dumps(matrix))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--select-file', help='check_build.py --select-only output; without it, the full matrix')
    set_matrix_json(ap.parse_args().select_file)
