#!/usr/bin/env python3
from __future__ import annotations

from html import escape, unescape
from html.parser import HTMLParser
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from botw_companion.i18n.presentation import translate_text
from tools.i18n import main


def markup(value, locale='en'):
    # Translate text and display attributes without rewriting technical markup.
    class Preview(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=False)
            self.parts = []

        def handle_starttag(self, tag, attrs):
            raw = self.get_starttag_text()
            self.parts.append(re.sub(r'((?:aria-label|title|placeholder|alt)\s*=\s*)(["\'])(.*?)(\2)',
                lambda m: m[1] + m[2] + escape(translate_text(unescape(m[3]), locale), quote=True) + m[4], raw, flags=re.S))

        def handle_endtag(self, tag):
            self.parts.append('</' + tag + '>')

        def handle_data(self, text):
            self.parts.append(escape(translate_text(text, locale), quote=False))

        def handle_entityref(self, name):
            self.parts.append('&' + name + ';')

        def handle_charref(self, name):
            self.parts.append('&#' + name + ';')
    parsed = Preview()
    parsed.feed(value)
    return ''.join(parsed.parts)


if __name__ == '__main__':
    # Keep the legacy command on the shared build/check path.
    raise SystemExit(main(['check' if '--check' in sys.argv[1:] else 'build']))
