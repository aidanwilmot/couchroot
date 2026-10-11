"""Private subprocess boundary for the tracked, bounded root transport."""
import json
from pathlib import Path
import sys
from .root import execute

if __name__ == '__main__':
    execute(json.loads(Path(sys.argv[1]).read_text()), Path(sys.argv[2]).read_text(),
            int(sys.argv[3]) if len(sys.argv)>3 else None)
