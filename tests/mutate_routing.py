#!/usr/bin/env python3
"""Prueft, ob die Routing-Pruefungen ueberhaupt beissen.

Eine gruene Testseite beweist nichts, solange niemand gesehen hat, dass sie auch
rot werden kann. Dieses Skript baut jeden Fehler, den routing.test.html abfangen
soll, einmal absichtlich ein und verlangt, dass genau die zugehoerige Pruefung
fehlschlaegt. Schlaegt sie nicht fehl, ist sie zahnlos und wird hier gemeldet.

Gearbeitet wird auf einer Kopie des Baums in einem Temporaerverzeichnis, nie im
Arbeitsbaum: das Skript laeuft auch dann, wenn parallel jemand an app/ arbeitet,
und es kann keine mutierte Datei zuruecklassen, wenn es abbricht.

Eine Mutation, deren Textstelle nicht mehr gefunden wird, gilt als Fehlschlag —
nicht als "nichts zu tun". Sonst faerbte sich das Skript nach jeder Umbenennung
im Code still gruen, ohne noch etwas zu pruefen.

    python3 tests/mutate_routing.py            # alle Mutationen
    python3 tests/mutate_routing.py Rueckfall  # nur passende, Teilstring im Namen
"""

import functools
import html
import http.server
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = 8792  # bewusst neben run_layout_tests.py (8791), damit beide nebeneinander laufen
SUITE = "tests/routing.test.html"
BUDGET = 45000

# Was aus dem Baum in die Kopie muss. data/ und bin/ bleiben draussen — die
# Testseite laedt nur app/ und tests/.
COPY = ["app", "tests"]

JS = "app/assets/js/fire.js"
EINSTIEG = "app/index.html"


class Mutation:
    """Ein absichtlich eingebauter Fehler und die Pruefung, die ihn fangen muss.

    erwartet ist ein Teilstring der FAIL-Zeile. Bewusst nicht der ganze Text:
    die Formulierung einer Pruefung darf sich aendern, ohne dieses Skript
    mitzuschleppen — der kennzeichnende Teil bleibt.
    """

    def __init__(self, name, datei, alt, neu, erwartet):
        self.name = name
        self.datei = datei
        self.alt = alt
        self.neu = neu
        self.erwartet = erwartet


MUTATIONEN = [
    Mutation(
        "Einstiegsseite verliert die Auswahl",
        EINSTIEG,
        "page + window.location.search + window.location.hash",
        "page + window.location.hash",
        "Einstiegsseite | Auswahl kommt an",
    ),
    Mutation(
        "Einstiegsseite verliert den Anker",
        EINSTIEG,
        "page + window.location.search + window.location.hash",
        "page + window.location.search",
        "Einstiegsseite | Anker kommt an",
    ),
    Mutation(
        "Rueckfall ignoriert die Auswahl",
        JS,
        "if (!next) next = sichtbar[0];",
        "if (!next) next = _fires[0];",
        "Anker ausserhalb | oeffnet ihn nicht",
    ),
    Mutation(
        "Auswahl wird nirgends angewandt",
        JS,
        "return selection || _fires;",
        "return _fires;",
        "?nur= | Liste zeigt nur die genannten Braende",
    ),
    Mutation(
        "Reihenfolge kommt aus der Adresse",
        JS,
        """    var gefiltert = _fires.filter(function (f) {
      return gewuenscht.indexOf(f.slug) !== -1;
    });""",
        """    var gefiltert = gewuenscht
      .map(function (t) {
        return _fires.filter(function (f) {
          return f.slug === t;
        })[0];
      })
      .filter(Boolean);""",
        "Reihenfolge | folgt den Daten",
    ),
    Mutation(
        "Schreibweise wird nicht normalisiert",
        JS,
        "return t.trim().toLowerCase();",
        "return t;",
        "Schreibweise |",
    ),
    Mutation(
        "leere Auswahl bleibt leer",
        JS,
        "return gefiltert.length ? gefiltert : null;",
        "return gefiltert;",
        "nur Unbekanntes |",
    ),
    # Die Textstelle steht seit dem Formatierer ueber vier Zeilen. In der
    # einzeiligen Fassung lief diese Mutation ins Leere und meldete "Textstelle
    # nicht gefunden" — gefunden beim Mutationslauf zum voreingestellten
    # Vergleich, nicht durch die Aenderung dort verursacht.
    Mutation(
        "Verweis schleppt die Auswahl mit",
        JS,
        """    var ziel =
      FULL_APP_URL +
      (lang === "de" ? "" : "index-en.html") +
      window.location.hash;""",
        """    var ziel =
      FULL_APP_URL +
      (lang === "de" ? "" : "index-en.html") +
      window.location.search +
      window.location.hash;""",
        "Verweis nimmt die Auswahl nicht mit",
    ),
    Mutation(
        "Zeitversatz wieder fest verdrahtet",
        JS,
        "    var stunden = offsetHours(millis, zoneOf(fire));",
        "    var stunden = 5;",
        "Zeitangabe | stimmt mit der Ortszeit der Aufnahme ueberein",
    ),
    Mutation(
        "Kuerzel passt nicht zum Versatz",
        JS,
        '    if (lang === "de") return stunden === 1 ? "MEZ" : "MESZ";',
        '    if (lang === "de") return "Uhr";',
        "Zeitangabe | nennt Datum, Uhrzeit und Kuerzel",
    ),
    Mutation(
        "Brandwechsel wirft die Auswahl weg",
        JS,
        'window.history.replaceState(null, "", target);',
        'window.history.replaceState(null, "", window.location.pathname + target);',
        "Brandwechsel | Adresse behaelt die Auswahl",
    ),
    # ---- Voreingestellter Groessenvergleich ----
    Mutation(
        "Voreinstellung wird nicht eingeblendet",
        JS,
        "      var ziel = citySlug || defaultCity();",
        "      var ziel = citySlug;",
        "ohne Angabe | Standardvergleich ist eingeblendet",
    ),
    Mutation(
        "Voreinstellung steht nicht im Anker",
        JS,
        'var teil = activeCity\n      ? "/" + activeCity',
        'var teil = false\n      ? "/" + activeCity',
        "ohne Angabe | Anker nennt die eingeblendete Stadt",
    ),
    # Zwei Mutationen fuer das Kuerzel, weil zwei verschiedene Fehler moeglich
    # sind. Ein uebersehenes NO_COMPARE laesst "none" als Stadtkuerzel
    # durchlaufen: gezeigt wird dann trotzdem nichts, weil es keine Stadt dieses
    # Namens gibt — rot wird nur der Anker, der die Angabe verliert. Der zweite
    # Fehler ist der gefaehrliche: die Voreinstellung ueberstimmt die
    # ausdrueckliche Ansage. Dann zeigt die Einbettung einen Vergleich, den die
    # Redaktion abgewaehlt hat.
    Mutation(
        "Kuerzel fuer ohne Vergleich wirkungslos",
        JS,
        "    if (citySlug === NO_COMPARE) {",
        "    if (false) {",
        "ohne Vergleich | Anker bleibt erhalten",
    ),
    Mutation(
        "ohne Vergleich wird von der Voreinstellung ueberstimmt",
        JS,
        """    if (citySlug === NO_COMPARE) {
      compareOff = true;
    } else {""",
        """    if (citySlug === NO_COMPARE) {
      compareOff = true;
      showCity(fire.compare);
    } else {""",
        "ohne Vergleich | keine Stadt eingeblendet",
    ),
    # Die Daten sind hier Teil der Aussage: steht in fires.js eine Stadt, die
    # nicht zum Brand passt, ist der Vergleich falsch voreingestellt — auch wenn
    # jede Zeile Code stimmt.
    Mutation(
        "Voreinstellung zeigt bei jedem Brand auf dieselbe Stadt",
        "app/assets/data/fires.js",
        '"compare":"paris"',
        '"compare":"bordeaux"',
        "Voreinstellung | anderer Brand, andere Stadt",
    ),
    # Befund 5 des Sprints: die weisse Fuellung wusch die Brandflaeche aus. Der
    # alte Wert war 0,35.
    Mutation(
        "Fuellung des Stadtumrisses zurueck auf 0,35",
        JS,
        '    fillColor: "#FFFFFF",\n    fillOpacity: 0.1,',
        '    fillColor: "#FFFFFF",\n    fillOpacity: 0.35,',
        "Signalfarbe | Rot bleibt gesaettigt unter dem Umriss",
    ),
]


def find_chrome():
    kandidaten = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    ]
    for pfad in kandidaten:
        if Path(pfad).exists():
            return pfad
    for name in ("google-chrome", "chromium", "chrome"):
        gefunden = shutil.which(name)
        if gefunden:
            return gefunden
    return None


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def lauf(chrome, wurzel):
    """Laedt die Testseite aus wurzel und gibt (PASS-Zeilen, FAIL-Zeilen) zurueck.

    Bei einem Abbruch ohne DONE ist das Ergebnis None — der Aufrufer darf das
    nicht als "keine Fehler" lesen.
    """
    handler = functools.partial(QuietHandler, directory=str(wurzel))

    # Jede Mutation bekommt eine eigene Kopie des Baums und damit einen eigenen
    # Server. Ein fester Port scheitert dabei zuverlaessig: der vorige liegt noch
    # in TIME_WAIT. Deshalb auf den naechsten freien ausweichen — und den
    # tatsaechlich benutzten in die Adresse einsetzen.
    server = None
    port = None
    letzter = None
    for kandidat in range(PORT, PORT + 40):
        try:
            server = http.server.ThreadingHTTPServer(("127.0.0.1", kandidat), handler)
        except OSError as err:
            letzter = err
            continue
        port = kandidat
        break
    if server is None:
        raise SystemExit(f"Kein freier Port zwischen {PORT} und {PORT + 39}: {letzter}")

    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        ergebnis = subprocess.run(
            [
                chrome,
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                f"--virtual-time-budget={BUDGET}",
                "--dump-dom",
                f"http://127.0.0.1:{port}/{SUITE}",
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
    finally:
        server.shutdown()
        server.server_close()

    treffer = re.search(r'<pre id="results">(.*?)</pre>', ergebnis.stdout, re.S)
    if not treffer:
        return None
    zeilen = [z.strip() for z in html.unescape(treffer.group(1)).splitlines() if z.strip()]
    if not any(z.startswith("DONE") for z in zeilen):
        return None
    return (
        [z for z in zeilen if z.startswith("PASS")],
        [z for z in zeilen if z.startswith("FAIL")],
    )


def entumlauten(text):
    """Vergleichsform ohne Umlaute.

    Die Testseite schreibt korrekte Umlaute, die Mutationsnamen hier stehen in
    Ersatzschreibung — ein Vergleich ueber beide Schreibweisen erspart es, die
    Erwartungen doppelt zu pflegen.
    """
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(a, b).replace(a.upper(), b.upper())
    return text.lower()


def passt(erwartet, zeilen):
    ziel = entumlauten(erwartet)
    return [z for z in zeilen if ziel in entumlauten(z)]


def kopiere(ziel):
    for name in COPY:
        shutil.copytree(ROOT / name, ziel / name, symlinks=True)


def main(argv):
    filter_text = argv[1] if len(argv) > 1 else None
    chrome = find_chrome()
    if not chrome:
        print("Chrome nicht gefunden — Mutationslauf nicht möglich.", file=sys.stderr)
        return 1

    ausgewaehlt = [m for m in MUTATIONEN if not filter_text or filter_text.lower() in m.name.lower()]
    if not ausgewaehlt:
        print(f"Keine Mutation passt zu {filter_text!r}.", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix="fire-mutate-") as tmp:
        sauber = Path(tmp) / "sauber"
        sauber.mkdir()
        kopiere(sauber)

        # Zweimal, nicht einmal: die Testseite liest jeden Rahmen nach einer festen
        # Wartezeit aus. Ist sie fuer einen Rahmen zu knapp, wird dessen Pruefung
        # rot, obwohl am Code nichts falsch ist. Ein einzelner Grundlauf koennte
        # das nicht von einem echten Fehler unterscheiden — und ein Wackler auf
        # der Zielpruefung einer Mutation wuerde diese faelschlich als "gefangen"
        # ausweisen.
        GRUND_LAEUFE = 2
        grund_pass = None
        for nr in range(1, GRUND_LAEUFE + 1):
            print(f"Grundlauf ohne Mutation ({nr}/{GRUND_LAEUFE}) …")
            grund = lauf(chrome, sauber)
            if grund is None:
                print(
                    "FEHLER: Grundlauf unvollständig — kein DONE. Ohne grüne "
                    "Ausgangslage sagt ein Mutationslauf nichts.",
                    file=sys.stderr,
                )
                return 1
            lauf_pass, lauf_fail = grund
            if lauf_fail:
                print("FEHLER: Grundlauf ist schon rot:", file=sys.stderr)
                for z in lauf_fail:
                    print("  " + z, file=sys.stderr)
                print(
                    "\nIst der Code in Ordnung, ist die Wartezeit in routing.test.html "
                    "zu knapp:\n  eine leere Liste in der Meldung heisst, der Rahmen war "
                    "noch nicht fertig.\n  Ein wackelnder Harnisch ist schlimmer als "
                    "keiner — ein echtes Rot gilt dann als Wackler.",
                    file=sys.stderr,
                )
                return 1
            if grund_pass is not None and set(lauf_pass) != set(grund_pass):
                print(
                    "FEHLER: zwei Grundläufe, zwei Ergebnisse — der Harnisch wackelt.",
                    file=sys.stderr,
                )
                for z in sorted(set(grund_pass) ^ set(lauf_pass)):
                    print("  nur in einem Lauf: " + z, file=sys.stderr)
                return 1
            grund_pass = lauf_pass
        print(f"  {len(grund_pass)} Prüfungen bestanden, 0 fehlgeschlagen.\n")

        schlecht = []
        for nr, m in enumerate(ausgewaehlt):
            arbeit = Path(tmp) / f"m-{nr}"
            kopiere(arbeit)
            pfad = arbeit / m.datei
            inhalt = pfad.read_text(encoding="utf-8")

            anzahl = inhalt.count(m.alt)
            if anzahl != 1:
                print(f"✗ {m.name}")
                print(f"    Textstelle {anzahl}× in {m.datei} gefunden, erwartet genau 1×.")
                print("    Der Code hat sich geändert — Mutation neu fassen.")
                schlecht.append(m.name)
                shutil.rmtree(arbeit)
                continue

            # Die Zielpruefung muss vorher gruen gewesen sein. Sonst hiesse "rot
            # nach der Mutation" nur, dass sie schon vorher rot war — oder dass es
            # die Pruefung gar nicht gibt und der Name sich vertippt hat.
            if not passt(m.erwartet, grund_pass):
                print(f"✗ {m.name}")
                print(f"    Zielprüfung {m.erwartet!r} war im Grundlauf nicht grün.")
                print("    Entweder ist sie umbenannt worden, oder sie existiert nicht.")
                schlecht.append(m.name)
                shutil.rmtree(arbeit)
                continue

            pfad.write_text(inhalt.replace(m.alt, m.neu), encoding="utf-8")
            ergebnis = lauf(chrome, arbeit)
            shutil.rmtree(arbeit)

            if ergebnis is None:
                print(f"✗ {m.name}")
                print("    Lauf unvollständig — kein DONE. Rot aus Abbruch zählt nicht.")
                schlecht.append(m.name)
                continue

            _, fails = ergebnis
            getroffen = passt(m.erwartet, fails)
            if getroffen:
                print(f"✓ {m.name}")
                print(f"    {getroffen[0]}")
                if len(fails) > len(getroffen):
                    # Mehr Rot als erwartet ist kein Fehler, aber eine Information:
                    # die Mutation trifft breiter als die eine Pruefung.
                    print(f"    (zusaetzlich {len(fails) - len(getroffen)} weitere Prüfung(en) rot)")
            else:
                print(f"✗ {m.name}")
                print(f"    erwartet rot: {m.erwartet!r}")
                print(f"    tatsaechlich rot: {len(fails)} Prüfung(en)")
                for z in fails[:5]:
                    print("      " + z)
                schlecht.append(m.name)

        print()
        print(
            f"{len(ausgewaehlt) - len(schlecht)} von {len(ausgewaehlt)} Mutationen wurden von einer Prüfung gefangen."
        )
        if schlecht:
            print("Nicht gefangen:")
            for name in schlecht:
                print("  - " + name)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
