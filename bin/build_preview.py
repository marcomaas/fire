#!/usr/bin/env python3
"""Erzeugt das Vorschaubild fuer Social-Media-Karten aus der laufenden Anwendung.

Das Bild unter app/assets/img/preview.png ist das, was bei jedem geteilten Link
erscheint — auf LinkedIn, Mastodon, Bluesky, in Slack und WhatsApp. Es war bis zum
31.07.2026 handgemacht und entsprechend veraltet: neun Staedte statt fuenf, drei
Braende statt fuenf, 26.008 ha statt 31.534, und in der Herkunftszeile stand
"CC BY", obwohl der Code unter MIT steht. Eine falsche Lizenzangabe in dem einen
Bild, das jeder sieht, der den Link teilt.

Deshalb erzeugt es jetzt ein Skript aus derselben Quelle wie die Anwendung. Der
gezeigte Brand wird nicht festgelegt, sondern aus den Daten gewaehlt: der mit der
groessten kartierten Flaeche, mit seiner voreingestellten Vergleichsstadt. Damit
zeigt die Karte immer den aussagekraeftigsten Stand, ohne dass jemand daran denken
muss.

Geprueft wird vor dem Schuss, nicht danach: das Dokument wird ausgelesen und gegen
die Daten gehalten (Anzahl Staedte, Anzahl Braende, keine CC-Lizenzangabe, Zahl im
Kasten passt zum letzten Zeitschnitt). Ein Bild, dessen Inhalt nicht stimmt, wird
nicht geschrieben — sonst waere der Generator nur eine schnellere Art,
dasselbe Problem zu erzeugen.

    python3 bin/build_preview.py            # erzeugen und schreiben
    python3 bin/build_preview.py --check     # nur pruefen, nichts schreiben
"""

from __future__ import annotations

import argparse
import functools
import html
import http.server
import json
import re
import shutil
import struct
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"
ZIEL = APP / "assets" / "img" / "preview.png"

# Fingerabdruck neben dem Bild. Ein PNG sagt von sich aus nicht, aus welchem
# Datenstand es entstanden ist — genau deshalb blieb das handgemachte Bild
# monatelang unbemerkt falsch. Die Datei macht das pruefbar: tests/test_pages.py
# vergleicht sie mit den aktuellen Daten und wird rot, wenn die Karte veraltet.
FINGERABDRUCK = APP / "assets" / "img" / "preview.json"

BREITE, HOEHE = 1200, 630  # Mindestmass fuer Open-Graph-Karten, Verhaeltnis 1,91
PORT = 8730
BUDGET_MS = 24000  # laenger als die Animation, damit der Endstand im Bild steht

CHROME_KANDIDATEN = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
]


def finde_chrome() -> str | None:
    for pfad in CHROME_KANDIDATEN:
        if Path(pfad).exists():
            return pfad
    for name in ("google-chrome", "chromium", "chrome"):
        gefunden = shutil.which(name)
        if gefunden:
            return gefunden
    return None


def lade_daten(name: str) -> list[dict]:
    """Liest eine der erzeugten .js-Datendateien als JSON."""
    roh = (APP / "assets" / "data" / name).read_text(encoding="utf-8")
    return json.loads(roh[roh.index("=") + 1 :].strip().rstrip(";"))


def fingerabdruck(fires: list[dict], cities: list[dict], brand: dict) -> dict:
    """Der Datenstand, aus dem das Bild entstanden ist.

    Absichtlich wenige, sprechende Werte und kein Hash ueber die ganze Datei: ein
    Hash waere schon dann verschieden, wenn sich ein Stuetzpunkt um einen Meter
    verschiebt, und wuerde das Bild bei jedem Datenlauf als veraltet melden. Was
    im Bild sichtbar ist, sind diese vier Angaben.
    """
    return {
        "slug": brand["slug"],
        "size_ha": round(brand["steps"][-1]["size_ha"], 1),
        "fires": len(fires),
        "cities": len(cities),
    }


def waehle_brand(fires: list[dict]) -> dict:
    """Der Brand mit der groessten kartierten Flaeche im letzten Zeitschnitt.

    Bewusst aus den Daten und nicht als Kuerzel im Skript: die Auswahl soll dem
    Stand folgen, nicht einer Entscheidung von vorgestern.
    """

    def flaeche(f: dict) -> float:
        return f["steps"][-1]["size_ha"] if f.get("steps") else 0.0

    return max(fires, key=flaeche)


class StillerHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def serve() -> tuple[http.server.ThreadingHTTPServer, int]:
    handler = functools.partial(StillerHandler, directory=str(APP))
    letzter = None
    for port in range(PORT, PORT + 20):
        try:
            server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
        except OSError as err:
            letzter = err
            continue
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server, port
    raise SystemExit(f"Kein freier Port zwischen {PORT} und {PORT + 19}: {letzter}")


def chrome_lauf(chrome: str, url: str, *, screenshot: Path | None) -> str:
    befehl = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--hide-scrollbars",
        f"--window-size={BREITE},{HOEHE}",
        f"--virtual-time-budget={BUDGET_MS}",
    ]
    if screenshot:
        befehl.append(f"--screenshot={screenshot}")
    else:
        befehl.append("--dump-dom")
    befehl.append(url)
    ergebnis = subprocess.run(befehl, capture_output=True, text=True, timeout=180)
    return ergebnis.stdout


def pruefe_inhalt(dom: str, fires: list[dict], cities: list[dict], brand: dict) -> list[str]:
    """Vergleicht das gerenderte Dokument mit den Daten. Leere Liste heisst: passt."""
    maengel: list[str] = []

    if "CC BY" in dom or "creativecommons.org/licenses" in dom:
        maengel.append("Herkunftszeile nennt eine CC-Lizenz — der Code steht unter MIT")

    brand_eintraege = len(re.findall(r'data-fire="', dom))
    if brand_eintraege != len(fires):
        maengel.append(f"{brand_eintraege} Brand-Eintraege im Bild, {len(fires)} in den Daten")

    stadt_eintraege = len(re.findall(r'data-city="[^"]+"', dom))
    if stadt_eintraege != len(cities):
        maengel.append(f"{stadt_eintraege} Staedte im Bild, {len(cities)} in den Daten")

    # Die Zahl im Kasten muss der letzten Aufnahme entsprechen, nicht einer frueheren.
    letzte_ha = brand["steps"][-1]["size_ha"]
    treffer = re.search(r'id="map-size"[^>]*>([^<]*)<', dom)
    if not treffer:
        maengel.append("Flaechenangabe im Bild nicht gefunden")
    else:
        text = html.unescape(treffer.group(1))
        ziffern = re.sub(r"[^\d]", "", text.split("(")[-1]) or "0"
        gezeigt = int(ziffern)
        # Ganzzahlig gerundet, wie die Anwendung es ausgibt.
        if abs(gezeigt - round(letzte_ha)) > 1:
            maengel.append(
                f"Flaechenangabe im Bild ist {gezeigt} ha, letzte Aufnahme hat "
                f"{round(letzte_ha)} ha — die Animation war noch nicht am Ende"
            )

    # Leaflet haengt eigene Klassen an den Marker (leaflet-div-icon, ...), ein
    # exakter Vergleich auf class="city-label" trifft deshalb nie.
    if "city-label" not in dom:
        maengel.append("kein Stadtumriss beschriftet — der Groessenvergleich fehlt im Bild")

    return maengel


def pruefe_bild(pfad: Path) -> list[str]:
    maengel: list[str] = []
    if not pfad.exists():
        return [f"{pfad} wurde nicht geschrieben"]
    daten = pfad.read_bytes()
    if daten[:8] != b"\x89PNG\r\n\x1a\n":
        return [f"{pfad.name} ist kein PNG"]
    breite, hoehe = struct.unpack(">II", daten[16:24])
    if (breite, hoehe) != (BREITE, HOEHE):
        maengel.append(f"{breite}x{hoehe} statt {BREITE}x{HOEHE}")
    if len(daten) < 40_000:
        maengel.append(f"nur {len(daten)} Byte — vermutlich eine leere Karte")
    return maengel


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="nur pruefen, nichts schreiben")
    args = parser.parse_args(argv[1:])

    chrome = finde_chrome()
    if not chrome:
        print("Chrome nicht gefunden — Vorschaubild uebersprungen.", file=sys.stderr)
        return 0  # Kein Browser ist kein Fehler, sondern eine fehlende Voraussetzung.

    fires = lade_daten("fires.js")
    cities = lade_daten("cities.js")
    if not fires:
        print("Keine Branddaten — nichts zu zeigen.", file=sys.stderr)
        return 1

    brand = waehle_brand(fires)
    anker = f"#{brand['slug']}" + (f"/{brand['compare']}" if brand.get("compare") else "")
    print(
        f"Brand mit der groessten Flaeche: {brand['slug']} ({round(brand['steps'][-1]['size_ha']):,} ha)".replace(
            ",", "."
        )
    )
    print(f"Anker: {anker}")

    server, port = serve()
    try:
        url = f"http://127.0.0.1:{port}/index-de.html{anker}"

        dom = chrome_lauf(chrome, url, screenshot=None)
        if not dom.strip():
            print("Chrome lieferte kein Dokument.", file=sys.stderr)
            return 1

        maengel = pruefe_inhalt(dom, fires, cities, brand)
        if maengel:
            print("\nInhalt stimmt nicht — kein Bild geschrieben:", file=sys.stderr)
            for m in maengel:
                print(f"  · {m}", file=sys.stderr)
            return 1
        print("Inhalt geprueft: Braende, Staedte, Flaechenangabe und Lizenz passen.")

        if args.check:
            print("--check: nichts geschrieben.")
            return 0

        ZIEL.parent.mkdir(parents=True, exist_ok=True)
        chrome_lauf(chrome, url, screenshot=ZIEL)
    finally:
        server.shutdown()

    maengel = pruefe_bild(ZIEL)
    if maengel:
        print("\nBild taugt nicht:", file=sys.stderr)
        for m in maengel:
            print(f"  · {m}", file=sys.stderr)
        return 1

    FINGERABDRUCK.write_text(
        json.dumps(fingerabdruck(fires, cities, brand), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    groesse = ZIEL.stat().st_size / 1024
    print(f"{ZIEL.relative_to(ROOT)}: {BREITE}x{HOEHE}, {groesse:.0f} KB")
    print(f"{FINGERABDRUCK.relative_to(ROOT)}: {fingerabdruck(fires, cities, brand)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
