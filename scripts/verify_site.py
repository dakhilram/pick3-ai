"""Confirm GitHub Pages serves the exact packaged Pick3 AI commit and assets."""
import argparse
import hashlib
import json
import time
import urllib.request
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parents[1]
SITE = 'https://dakhilram.github.io/pick3-ai/'


def matches_live(expected, fetch):
    published = json.loads(fetch('deployment.json'))
    if published != expected:
        return False, f"deployed commit {published.get('commit_sha')}"
    for relative, digest in expected['assets'].items():
        actual = hashlib.sha256(fetch(relative)).hexdigest()
        if actual != digest:
            return False, f'{relative} differs from packaged artifact'
    return True, f"commit {expected['commit_sha']} and all {len(expected['assets'])} assets match"


def verify(site=SITE, directory=ROOT / 'site-dist', attempts=30, interval=6):
    expected = json.loads((Path(directory) / 'deployment.json').read_text(encoding='utf-8'))
    marker = expected['commit_sha']

    def fetch(relative):
        url = urljoin(site, relative) + '?deployment=' + marker
        request = urllib.request.Request(url, headers={'Cache-Control': 'no-cache',
                                                       'User-Agent': 'Pick3AI-Deployment-Check'})
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()

    detail = 'not checked'
    for attempt in range(attempts):
        try:
            matched, detail = matches_live(expected, fetch)
            if matched:
                print('Verified production:', detail)
                return True
        except (OSError, ValueError, KeyError) as error:
            detail = str(error)
        if attempt < attempts - 1:
            time.sleep(interval)
    raise RuntimeError(f"Production did not match {marker}: {detail}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--site', default=SITE)
    parser.add_argument('--directory', type=Path, default=ROOT / 'site-dist')
    args = parser.parse_args()
    verify(args.site, args.directory)
