"""Embed data/dashboard_data.json into src/template.html -> dashboard.html + index.html.

Both outputs are byte-identical (index.html lets static hosts resolve '/').
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLACEHOLDER = '/*__DATA__*/null'


def main():
    tpl = (ROOT / 'src' / 'template.html').read_text(encoding='utf-8')
    assert tpl.count(PLACEHOLDER) == 1, 'template must contain exactly one data placeholder'
    data = (ROOT / 'data' / 'dashboard_data.json').read_text(encoding='utf-8')
    html = tpl.replace(PLACEHOLDER, data.replace('</', '<\\/'))
    for name in ('dashboard.html', 'index.html'):
        (ROOT / name).write_text(html, encoding='utf-8', newline='\n')
    print(f'wrote dashboard.html + index.html ({len(html.encode("utf-8")):,} bytes)')


if __name__ == '__main__':
    main()
