#!/usr/bin/env python3
"""Fuehrt die Browser-Regressionstests aus.

Startet einen lokalen Webserver, laedt die Testseiten unter tests/ in Chrome ohne
Fenster und liest das Ergebnis aus dem fertig gerenderten Dokument. Beendet sich
mit Code 1, sobald eine Pruefung fehlschlaegt.

Zwei Testseiten:
  layout.test.html   — Geometrie und Bedienbarkeit in Rahmen mehrerer Groessen
  routing.test.html  — Adresse und Auswahl: Anker, ?nur=, Rueckfaelle
  burn.test.html     — eine Invariante ueber die Animation: verbrannte Flaeche
                       verschwindet nicht wieder

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

# Testseiten mit dem Zeitbudget, das sie brauchen. Die Layout-Seite baut zehn
# Rahmen auf und wartet, bis Karten und Schriften stehen; die Routing-Seite laedt
# mehr Rahmen, aber ohne auf die Kartenkacheln zu warten.
SUITES = [
    ("tests/layout.test.html", 8000),
    ("tests/routing.test.html", 40000),
    # Laeuft laenger als die anderen, weil sie die ganze Animation abtastet: drei
    # Faelle je 16 Sekunden virtuelle Zeit.
    ("tests/burn.test.html", 60000),
]

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
    """Startet den Testserver und gibt (Server, Port) zurueck.

    Weicht auf den naechsten freien Port aus. Ein voriger Lauf kann den Port noch
    im Zustand TIME_WAIT halten oder ein haengender Prozess ihn belegen — der Lauf
    scheiterte dann mit "Address already in use", was wie ein Testfehler aussieht
    und keiner ist.
    """
    handler = functools.partial(QuietHandler, directory=str(ROOT))
    letzter = None
    for port in range(PORT, PORT + 20):
        try:
            server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
        except OSError as err:
            letzter = err
            continue
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, port
    raise SystemExit(f"Kein freier Port zwischen {PORT} und {PORT + 19}: {letzter}")


def run_suite(chrome, port, path, budget):
    """Fuehrt eine Testseite aus und gibt (Fehlerzeilen, Zusammenfassung) zurueck.

    Bei einem Abbruch ist die Zusammenfassung None — der Aufrufer wertet das als
    Fehlschlag, nicht als "keine Fehler gefunden".
    """
    url = f"http://127.0.0.1:{port}/{path}"
    result = subprocess.run(
        [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            # Die Testseiten warten, bevor sie messen. Das Budget endet knapp
            # danach: unter virtueller Zeit rechnen die Animationen in zehn
            # Rahmen sonst weiter, ohne dass das Ergebnis sich noch aendert —
            # das kostete real ueber drei Minuten.
            f"--virtual-time-budget={budget}",
            "--dump-dom",
            url,
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )

    dom = result.stdout
    if not dom.strip():
        print(f"{path}: Chrome lieferte kein Dokument.", file=sys.stderr)
        print(result.stderr[-2000:], file=sys.stderr)
        return [], None

    match = re.search(r'<pre id="results">(.*?)</pre>', dom, re.S)
    if not match:
        print(f"{path}: Ergebnisblock nicht gefunden - lief das Skript?", file=sys.stderr)
        return [], None

    report = html.unescape(match.group(1)).strip()
    lines = [line.strip() for line in report.splitlines() if line.strip()]

    if not any(line.startswith("DONE") for line in lines):
        print(f"{path}: Testlauf unvollständig - kein DONE. Zeitbudget zu klein?",
              file=sys.stderr)
        print(report[-2000:], file=sys.stderr)
        return [], None

    failures = [line for line in lines if line.startswith("FAIL")]
    summary = next(line for line in lines if line.startswith("DONE"))
    return failures, summary


def main():
    chrome = find_chrome()
    if not chrome:
        print("Chrome nicht gefunden - Browser-Tests übersprungen.", file=sys.stderr)
        print("Gesucht an:", ", ".join(CHROME_CANDIDATES), file=sys.stderr)
        return 0  # Kein Browser ist kein Testfehler.

    server, port = serve()
    schlecht = False
    try:
        for path, budget in SUITES:
            if not (ROOT / path).exists():
                print(f"{path}: Testseite fehlt.", file=sys.stderr)
                schlecht = True
                continue
            failures, summary = run_suite(chrome, port, path, budget)
            for line in failures:
                print(line)
            name = Path(path).name
            print(f"{name}: {summary}" if summary else f"{name}: ABGEBROCHEN")
            if failures or not summary:
                schlecht = True
    finally:
        server.shutdown()

    return 1 if schlecht else 0


if __name__ == "__main__":
    sys.exit(main())
