#!/usr/bin/env python3
"""Fuehrt die Layout-Regressionstests in einem echten Browser aus.

Startet einen lokalen Webserver, laedt tests/layout.test.html in Chrome ohne
Fenster und liest das Ergebnis aus dem fertig gerenderten Dokument. Beendet sich
mit Code 1, sobald eine Pruefung fehlschlaegt.

Bewusst ohne Playwright oder Selenium: die Pruefungen brauchen nur echtes Layout
und ein paar Klicks, das leistet Chrome mit --dump-dom und --virtual-time-budget
allein. Damit kommen keine weiteren Abhaengigkeiten und keine hundert Megabyte
Browser-Download dazu.

    python3 tests/run_layout_tests.py
"""

import functools
import html
import http.server
import re
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = 8791

# Chrome an den Orten, an denen er auf einem Mac und auf einem CI-Laeufer liegt.
CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
]


def find_chrome():
    for path in CHROME_CANDIDATES:
        if Path(path).exists():
            return path
    from shutil import which

    for name in ("google-chrome", "chromium", "chrome"):
        found = which(name)
        if found:
            return found
    return None


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def serve():
    handler = functools.partial(QuietHandler, directory=str(ROOT))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def main():
    chrome = find_chrome()
    if not chrome:
        print("Chrome nicht gefunden - Layout-Tests uebersprungen.", file=sys.stderr)
        print("Gesucht an:", ", ".join(CHROME_CANDIDATES), file=sys.stderr)
        return 0  # Kein Browser ist kein Testfehler.

    server = serve()
    try:
        url = f"http://127.0.0.1:{PORT}/tests/layout.test.html"
        result = subprocess.run(
            [
                chrome,
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                # Die Seite wartet sechs Sekunden, bevor sie messt.
                "--virtual-time-budget=20000",
                "--dump-dom",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
    finally:
        server.shutdown()

    dom = result.stdout
    if not dom.strip():
        print("Chrome lieferte kein Dokument.", file=sys.stderr)
        print(result.stderr[-2000:], file=sys.stderr)
        return 1

    match = re.search(r'<pre id="results">(.*?)</pre>', dom, re.S)
    if not match:
        print("Ergebnisblock nicht gefunden - lief das Skript der Testseite?", file=sys.stderr)
        return 1

    report = html.unescape(match.group(1)).strip()
    lines = [line.strip() for line in report.splitlines() if line.strip()]

    if not any(line.startswith("DONE") for line in lines):
        print("Testlauf unvollstaendig - kein DONE. Zeitbudget zu klein?", file=sys.stderr)
        print(report[-2000:], file=sys.stderr)
        return 1

    failures = [line for line in lines if line.startswith("FAIL")]
    summary = next(line for line in lines if line.startswith("DONE"))

    for line in failures:
        print(line)
    print(summary)

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
