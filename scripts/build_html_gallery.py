"""Rebuild the developer gallery without creating a canonical research session."""
import json
from pathlib import Path
import html_sessions as sessions

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures/html'


def build():
    state = json.loads((FIXTURES / 'session-component-gallery.json').read_text(encoding='utf-8'))
    # This authored teaching schematic belongs only to this synthetic gallery.
    figure = '<figure class="ros-figure ros-wide"><div class="ros-figure-panels"><figure><svg viewBox="0 0 400 160" role="img" aria-label="Analytic vector schematic"><path d="M40 120 L340 120 M40 120 L40 20" stroke="currentColor" fill="none"/><path d="M40 120 L280 40" stroke="currentColor" stroke-width="3"/><text x="290" y="40" fill="currentColor">v</text></svg><figcaption>(a) Analytic vector schematic.</figcaption></figure><figure><svg viewBox="0 0 400 160" role="img" aria-label="Illustrative inverse square root curve"><path d="M40 120 L340 120 M40 120 L40 20" stroke="currentColor" fill="none"/><path d="M45 25 Q80 90 320 108" fill="none" stroke="currentColor" stroke-width="3"/></svg><figcaption>(b) Qualitative schematic; no measured data.</figcaption></figure></div><figcaption>Multi-panel figure with captions kept beside the visual context.</figcaption></figure>'
    result = sessions.render_html(state, '../../../assets/html-runtime',
                                  resource_images={'example-image': state['resources'][0]['path']})
    marker = '>Figures</h2>'
    assert result.count(marker) == 1
    result = result.replace(marker, marker + figure)
    result = result.replace('<table>', '<table><caption>Illustrative analytic values, not measured data.</caption>', 1)
    (FIXTURES / 'session-component-gallery.html').write_text(result, encoding='utf-8', newline='\n')


if __name__ == '__main__':
    build()
