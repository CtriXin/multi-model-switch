#!/usr/bin/env python3
import re
import sys
from pathlib import Path

REQUIRED = [
    r'^# Progress\s+—\s+.+$',
    r'^-\s+Title:\s+.+$',
    r'^-\s+Task ID:\s+.+$',
    r'^-\s+CLI:\s+.+$',
    r'^-\s+Status:\s+.+$',
    r'^-\s+Updated:\s+.+$',
    r'^## Summary$',
    r'^## Next Action$',
]


def main() -> int:
    if len(sys.argv) != 2:
        print('usage: validate_progress.py <progress.md>')
        return 2
    path = Path(sys.argv[1])
    text = path.read_text(encoding='utf-8')
    for pattern in REQUIRED:
        if not re.search(pattern, text, re.MULTILINE):
            print(f'missing: {pattern}')
            return 1
    print('ok')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
