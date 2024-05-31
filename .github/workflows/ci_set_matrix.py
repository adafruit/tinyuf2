import json
from pathlib import Path

# TOP is tinyusb root dir
TOP = Path(__file__).parent.parent.parent.resolve()


def set_matrix_json():
    ports_dir = Path(TOP / 'ports')
    matrix = {}
    for p in sorted(ports_dir.iterdir()):
        if p.is_dir() and p.name != 'template_port':
            matrix[p.name] = {}
            boards_dir = ports_dir / p / 'boards'
            if boards_dir.exists():
                matrix[p.name]['board'] = []
                for b in sorted(boards_dir.iterdir()):
                    if b.is_dir():
                        matrix[p.name]['board'].append(b.name)
    print(json.dumps(matrix))


if __name__ == '__main__':
    set_matrix_json()
