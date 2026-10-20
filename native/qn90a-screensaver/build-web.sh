#!/bin/sh
set -eu
cd "$(dirname "$0")"
emcc core.c -std=c99 -O2 -Wall -Wextra -Werror -Wno-unused-function \
  -s MODULARIZE=1 -s EXPORT_NAME=AsteroidsCore -s ENVIRONMENT=web \
  -s SINGLE_FILE=1 -s WASM_ASYNC_COMPILATION=1 -s FILESYSTEM=0 \
  -s INITIAL_MEMORY=2097152 -s TOTAL_STACK=65536 -s ALLOW_MEMORY_GROWTH=0 \
  -s MIN_CHROME_VERSION=76 \
  -s 'EXPORTED_FUNCTIONS=["_saver_init","_saver_frame","_saver_vertices","_saver_light","_saver_steps"]' \
  -o web/core.js
python3 - <<'PY'
from pathlib import Path
import re,json
source=Path('../system-screensaver/renderer.c').read_text()
def shader(name):
    code=re.search(r'static const char \*'+name+r' =([\s\S]*?);\n',source).group(1)
    return ''.join(json.loads(x) for x in re.findall(r'"(?:[^"\\]|\\.)*"',code))
Path('web/shaders.js').write_text('window.SaverShaders='+json.dumps({'vertex':shader('vertex_shader'),'fragment':Path('fragment.glsl').read_text()})+';\n')
PY
