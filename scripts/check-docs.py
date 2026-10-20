#!/usr/bin/env python3
"""Check repository-relative Markdown/HTML links, anchors and the docs index offline."""
import html
from html.parser import HTMLParser
import re
import subprocess
import sys
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
# These are build outputs, deliberately absent from a source checkout. Their
# producing build and byte reproducibility are checked by qn90a-web-saver CI.
GENERATED = {
    'research/qn90a-screensaver/web/core.js': 'research/qn90a-screensaver/build-web.sh',
    'research/qn90a-screensaver/web/shaders.js': 'research/qn90a-screensaver/build-web.sh',
}


def prose(text):
    """Keep line numbers while removing fenced code and HTML comments."""
    lines = []; fence = None
    for line in text.splitlines(keepends=True):
        match = re.match(r'^\s{0,3}(`{3,}|~{3,})', line)
        if match and fence is None:
            fence = match[1]; lines.append('\n'); continue
        if fence is not None:
            if match and match[1][0] == fence[0] and len(match[1]) >= len(fence): fence = None
            lines.append('\n'); continue
        lines.append(line)
    return re.sub(r'<!--.*?-->', lambda m: '\n' * m[0].count('\n'), ''.join(lines), flags=re.S)


class Markup(HTMLParser):
    def __init__(self):
        super().__init__(); self.links = []; self.anchors = set()
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs: self.anchors.add(attrs['id'])
        if tag == 'a' and 'name' in attrs: self.anchors.add(attrs['name'])
        for key in ('href', 'src'):
            if attrs.get(key): self.links.append((self.getpos()[0], attrs[key]))


def slug(title):
    title = html.unescape(re.sub(r'<[^>]*>', '', title))
    title = re.sub(r'!?\[([^]]+)\]\([^)]*\)', r'\1', title)
    title = title.replace('`', '').replace('*', '').replace('~', '').lower().strip()
    return ''.join(c for c in title if c in '-_' or not unicodedata.category(c).startswith(('P', 'S'))).replace(' ', '-')


def parse(path):
    text = path.read_text(encoding='utf-8'); markdown = path.suffix.lower() == '.md'
    text = prose(text) if markdown else text
    markup = Markup(); markup.feed(re.sub(r'(`+)(.*?)\1', lambda m: '\n' * m[0].count('\n'), text, flags=re.S) if markdown else text)
    links = list(markup.links); anchors = set(markup.anchors)
    if markdown:
        used = set(); lines = text.splitlines()
        for i, line in enumerate(lines):
            heading = re.match(r'^\s{0,3}#{1,6}\s+(.+?)(?:\s+#+)?\s*$', line)
            title = heading[1] if heading else (lines[i-1] if i and re.fullmatch(r'\s{0,3}(?:=+|-+)\s*', line) and lines[i-1].strip() else None)
            if title:
                base = slug(title); value = base; suffix = 0
                while value in used: suffix += 1; value = base + '-' + str(suffix)
                used.add(value); anchors.add(value)
        # Ignore inline code examples, but retain link labels and destinations.
        text = re.sub(r'(`+)(.*?)\1', lambda m: re.sub(r'[^\n]', ' ', m[0]), text, flags=re.S)
        refs = {m[1].strip().casefold(): m[2].strip('<>') for m in re.finditer(r'^\s{0,3}\[([^]]+)\]:\s*(<[^>]+>|\S+)', text, re.M)}
        pattern = r'!?\[([^]\n]*(?:\[[^]\n]*\][^]\n]*)*)\]\(\s*(<[^>]*>|(?:[^\s()\\]|\\.|\([^()]*\))*)(?:\s+["\'][^\n]*?["\'])?\s*\)'
        for m in re.finditer(pattern, text):
            links.append((text.count('\n', 0, m.start()) + 1, m[2].strip('<>')))
        for m in re.finditer(r'!?\[([^]\n]+)\]\[([^]\n]*)\]', text):
            key = (m[2] or m[1]).strip().casefold()
            links.append((text.count('\n', 0, m.start()) + 1, refs.get(key, 'MISSING-REFERENCE:' + key)))
        for m in re.finditer(r'(?<!!)\[([^]\n]+)\](?![(:\[])', text):
            if m[1].strip().casefold() in refs:
                links.append((text.count('\n', 0, m.start()) + 1, refs[m[1].strip().casefold()]))
    return links, anchors


def check(root, files):
    root = root.resolve(); parsed = {}; errors = []; indexed = set()
    documents = sorted(p for p in files if p.suffix.lower() in ('.md', '.html'))
    for source in documents:
        parsed[source] = parse(root / source)
    for source in documents:
        for line, raw in parsed[source][0]:
            if raw.startswith('MISSING-REFERENCE:'):
                errors.append(f'{source}:{line}: undefined {raw}'); continue
            url = urlsplit(html.unescape(raw))
            # Site-root routes and non-file URLs are not relative repository links.
            if url.scheme or url.netloc or url.path.startswith('/'): continue
            path = unquote(re.sub(r'\\(.)', r'\1', url.path))
            target = ((root / source).parent / path).resolve() if path else root / source
            if not target.is_relative_to(root):
                errors.append(f'{source}:{line}: link escapes repository: {raw}'); continue
            relative = target.relative_to(root)
            if source == Path('docs/README.md'): indexed.add(relative)
            if not target.exists():
                producer = GENERATED.get(relative.as_posix())
                if producer and (root / producer).is_file(): continue
                errors.append(f'{source}:{line}: missing target: {raw}'); continue
            if url.fragment:
                fragment = unquote(url.fragment)
                if target.suffix.lower() in ('.md', '.html'):
                    if relative not in parsed: parsed[relative] = parse(target)
                    if fragment not in parsed[relative][1]: errors.append(f'{source}:{line}: missing anchor: {raw}')
                else:
                    span = re.fullmatch(r'L(\d+)(?:-L(\d+))?', fragment)
                    try: count = len(target.read_text().splitlines())
                    except (OSError, UnicodeError): count = 0
                    if not span or not (1 <= int(span[1]) <= int(span[2] or span[1]) <= count):
                        errors.append(f'{source}:{line}: invalid file anchor: {raw}')
    for path in documents:
        if path.parts[0] == 'docs' and path.suffix == '.md' and path != Path('docs/README.md') and path not in indexed:
            errors.append(f'docs/README.md: unindexed document: {path}')
    return errors


def main():
    files = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=ROOT).decode().split('\0')
    errors = check(ROOT, {Path(p) for p in files if p})
    if errors:
        print('\n'.join(errors)); return 1
    print('Documentation links, anchors and complete docs index passed.'); return 0


if __name__ == '__main__':
    sys.exit(main())
