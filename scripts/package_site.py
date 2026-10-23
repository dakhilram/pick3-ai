"""Package only the active V2 dashboard and its single published dataset."""
import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'web'
ASSETS = ('index.html', 'app.js', 'styles.css', 'icon.svg',
          'manifest.webmanifest', 'data/predictions.json')


def package(destination):
    destination = Path(destination)
    if destination.resolve() == WEB.resolve():
        raise ValueError('Cannot package over source web directory')
    for relative in ASSETS:
        source = WEB / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('destination', nargs='?', default=ROOT / 'site-dist')
    package(parser.parse_args().destination)
