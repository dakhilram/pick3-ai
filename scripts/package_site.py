"""Package only the active V2 dashboard and its single published dataset."""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'web'
ASSETS = ('index.html', 'app.js', 'styles.css', 'icon.svg',
          'manifest.webmanifest', 'data/predictions.json')
OUTPUTS = (*ASSETS, 'deployment.json')


def package(destination):
    destination = Path(destination)
    if destination.resolve() == WEB.resolve():
        raise ValueError('Cannot package over source web directory')
    hashes = {}
    for relative in ASSETS:
        source = WEB / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        hashes[relative] = hashlib.sha256(source.read_bytes()).hexdigest()
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    publication = json.loads((WEB / 'data/predictions.json').read_text(encoding='utf-8'))
    manifest = {'commit_sha': commit, 'generated_at': publication['generated_at'],
                'assets': hashes}
    (destination / 'deployment.json').write_text(json.dumps(manifest, indent=2) + '\n',
                                                  encoding='utf-8')
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('destination', nargs='?', default=ROOT / 'site-dist')
    package(parser.parse_args().destination)
