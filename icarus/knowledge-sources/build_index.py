#!/usr/bin/env python3
"""Build an ICARUS discovery index from local RADIO Markdown and curated records.

Standard-library only. This program never modifies source canon or records.json.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

CATEGORIES = {
    'radio-stories': 'work',
    'radio-cannon/characters': 'character',
    'radio-cannon/species': 'species',
    'radio-cannon/locations': 'location',
    'radio-cannon/vessels': 'vessel',
    'radio-cannon/timeline': 'event',
    'radio-music': 'music',
    'radio-games': 'game',
    'radio-clothing': 'clothing',
}
EXCLUDED = {'README.md', 'TEMPLATE.md', '.gitkeep'}


def slug(value):
    value = re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')
    return value or 'untitled'


def title_from_md(content, path):
    m = re.search(r'^#\s+(.+?)\s*$', content, flags=re.M)
    return m.group(1).strip() if m else path.stem.replace('-', ' ').title()


def short_summary(content):
    # Preserve source text only; do not invent a lore summary.
    lines = content.splitlines()
    for line in lines:
        s = line.strip()
        if not s or s.startswith('#') or s.startswith('**') or s.startswith('---') or s.startswith('>'):
            continue
        if len(s) >= 35:
            return s[:350] + ('…' if len(s) > 350 else '')
    return ''


def scan(root):
    found = []
    for folder, typ in CATEGORIES.items():
        directory = root / folder
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob('*.md')):
            if path.name in EXCLUDED or path.name.startswith('_'):
                continue
            rel = path.relative_to(root).as_posix()
            content = path.read_text(encoding='utf-8-sig')
            if not content.strip():
                continue
            found.append({
                'id': f'{typ}-{slug(path.stem)}',
                'type': typ,
                'name': title_from_md(content, path),
                'summary': short_summary(content),
                'sources': [rel],
                'discovery': {'path': rel, 'sha256': hashlib.sha256(content.encode()).hexdigest(), 'origin': 'filesystem'},
            })
    return found


def build(root):
    registry_path = root / 'icarus/knowledge-sources/records.json'
    registry = json.loads(registry_path.read_text(encoding='utf-8-sig'))
    curated = registry['records']
    by_id = {r['id']: dict(r) for r in curated}
    if len(by_id) != len(curated):
        raise ValueError('Duplicate IDs in curated records.json')
    by_source = {}
    for r in curated:
        for source in r.get('sources', []):
            if source.endswith('.md'):
                by_source.setdefault(source, []).append(r['id'])
    warnings = []
    discovered = scan(root)
    for item in discovered:
        path = item['discovery']['path']
        matches = by_source.get(path, [])
        # A single file may be cited by many character or location records.
        # Match only curated records of the same type, preferably with their own
        # canonical path (e.g. radio-cannon/characters/takar.md).
        own = [key for key in matches if by_id[key]['type'] == item['type'] and
               (item['type'] != 'work' or key.startswith('work-')) and
               (item['type'] == 'work' or path.startswith('radio-cannon/'))]
        own = [key for key in own if (item['type'] == 'work' or
               any(s == path for s in by_id[key].get('sources', [])))]
        if len(own) == 1:
            rec = by_id[own[0]]
            rec['discovery'] = item['discovery']
            continue
        if len(own) > 1:
            warnings.append(f'Ambiguous source mapping: {path}: {own}')
            continue
        # If a curated ID already exists, keep curated metadata and attach source.
        if item['id'] in by_id:
            rec = by_id[item['id']]
            if rec['type'] != item['type']:
                warnings.append(f'ID conflict: {item["id"]} at {path}')
                continue
            if path not in rec.get('sources', []):
                rec.setdefault('sources', []).append(path)
            rec['discovery'] = item['discovery']
            continue
        by_id[item['id']] = item
    # Curated entries are retained, including references to files not yet uploaded.
    return {'version': 1, 'generator': 'icarus/knowledge-sources/build_index.py',
            'records': sorted(by_id.values(), key=lambda x: (x['type'], x['name'].lower(), x['id'])),
            'warnings': warnings,
            'statistics': {'curated_records': len(curated), 'discovered_markdown_files': len(discovered),
                           'combined_records': len(by_id)}}


def main():
    parser = argparse.ArgumentParser(description='Generate ICARUS index without editing canon.')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--output', type=Path, default=Path('icarus/knowledge-sources/index.generated.json'))
    args = parser.parse_args()
    root = args.root.resolve()
    result = build(root)
    target = args.output if args.output.is_absolute() else root / args.output
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(result['statistics'], indent=2))
    for warning in result['warnings']:
        print('WARNING:', warning)


if __name__ == '__main__':
    main()
