import json
import os
import sys
from pathlib import Path

path = Path('/home/rhyan/.cache/tcc-experimento/host-atual.json')
path.parent.mkdir(parents=True, exist_ok=True)
for line in sys.stdin:
    if len(line) > 8192:
        raise ValueError('Amostra do notebook excedeu o limite')
    sample = json.loads(line)
    temporary = path.with_suffix('.' + str(os.getpid()))
    temporary.write_text(json.dumps(sample))
    temporary.replace(path)
