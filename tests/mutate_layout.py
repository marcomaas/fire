#!/usr/bin/env python3
"""Prueft, ob die Layout-Pruefungen ueberhaupt beissen.

Dasselbe Verfahren wie tests/mutate_routing.py, nur gegen layout.test.html: jeder
Fehler, den eine Pruefung fangen soll, wird einmal absichtlich in eine Kopie des
Baums eingebaut, und genau die zugehoerige Pruefung muss rot werden. Wird sie es
nicht, ist sie zahnlos und wird hier gemeldet.

Der Harnisch selbst — Serverstart, Chrome-Aufruf, Auswertung, zwei Grundlaeufe
gegen einen wackelnden Aufbau — kommt aus mutate_routing.py und wird nicht
verdoppelt. Nur die Testseite und das Zeitbudget sind andere. Ein eigener
Einstiegspunkt statt einer Liste mehr dort drin, weil beide Seiten
unterschiedlich lange brauchen und ein gemeinsamer Lauf ueber zwanzig Minuten
liefe: wer eine Layout-Pruefung anfasst, will nicht die Routing-Mutationen mit
abwarten.

    python3 tests/mutate_layout.py               # alle Mutationen
    python3 tests/mutate_layout.py Hinweiszeile  # nur passende, Teilstring im Namen
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mutate_routing as harnisch  # noqa: E402 — erst nach sys.path-Ergaenzung moeglich
from mutate_routing import Mutation  # noqa: E402

# Die Layout-Seite baut vierzehn Rahmen auf und misst nach sechs Sekunden. Das
# Budget deckt das mit Reserve; run_layout_tests.py faehrt mit demselben Wert.
harnisch.SUITE = "tests/layout.test.html"
harnisch.BUDGET = 12000

CSS = "app/assets/css/fire.css"
JS = "app/assets/js/fire.js"
SEITE_DE = "app/index-de.html"

MUTATIONEN = [
    # ---- Hinweiszeile bei scrollenden Listen ----
    Mutation(
        "Hinweiszeile bleibt leer",
        JS,
        '      box.find(".list-hint").text(hinweis);',
        '      box.find(".list-hint").text("");',
        "Hinweiszeile sichtbar",
    ),
    Mutation(
        "Hinweiszeile nennt eine falsche Zahl",
        JS,
        "        hinweis = text.hiddenBelow(verdeckt.unten);",
        "        hinweis = text.hiddenBelow(verdeckt.unten + 1);",
        "Hinweiszeile nennt die Zahl",
    ),
    # Bewusst im Skript und nicht im Stylesheet: die Zeile ist absolut
    # positioniert und ohne Text null Pixel breit. Blendet das Stylesheet sie
    # faelschlich immer ein, ist trotzdem nichts zu sehen — der erste Versuch
    # dieser Mutation lief dort und blieb wirkungslos. Falsch ist eine Auskunft
    # ueber Eintraege, die es nicht gibt, und die entsteht hier.
    Mutation(
        "Hinweis steht auch ohne verdeckte Eintraege",
        JS,
        '      var hinweis = "";',
        "      var hinweis = text.hiddenBelow(0);",
        "ohne verdeckte Einträge ohne Hinweis",
    ),
    # ---- Kompakte Zustandsanzeige ----
    Mutation(
        "Nebenangaben bleiben aufgeklappt",
        JS,
        '    $("#fire-details").prop("open", !compact);',
        '    $("#fire-details").prop("open", true);',
        "Nebenangaben sind zugeklappt",
    ),
    # Der Griff sperrt Zeigerereignisse aus: fuer ein Skript weiterhin klickbar,
    # fuer einen Menschen unbedienbar. Genau deshalb gibt es die Pruefung auf
    # pointer-events — ein Klick aus dem Testlauf feuert auch dann, und die
    # Pruefung dahinter blieb gruen. Nachgemessen: erst mit dieser Mutation wird
    # der Unterschied sichtbar.
    Mutation(
        "Griff sperrt Zeigerereignisse aus",
        CSS,
        """#fire-details > summary {
	display: none;
	cursor: pointer;""",
        """#fire-details > summary {
	display: none;
	pointer-events: none;
	cursor: pointer;""",
        "Aufklapp-Griff nimmt Zeigerereignisse an",
    ),
    # Die Nebenangaben rutschen aus dem Aufklapper heraus — der Griff schaltet
    # dann etwas Leeres, und die Angaben stehen unabhaengig von ihm da. Das ist
    # der wahrscheinlichste Rueckfall, sobald jemand den Kasten umbaut.
    Mutation(
        "Nebenangaben liegen ausserhalb des Aufklappers",
        SEITE_DE,
        """				<details id="fire-details" open>
					<summary id="fire-details-label"></summary>
					<div id="timeline-summary"></div>

					<div id="fire-caption">
						<span id="fire-region"></span>
						<span id="fire-status"></span>
						<span><span id="fire-steps"></span> · Copernicus <a id="fire-source" href="#" target="_blank" rel="noopener"></a></span>
						<span id="fire-note"></span>
					</div>
				</details>""",
        """				<details id="fire-details" open>
					<summary id="fire-details-label"></summary>
					<div id="timeline-summary"></div>
				</details>

				<div id="fire-caption">
					<span id="fire-region"></span>
					<span id="fire-status"></span>
					<span><span id="fire-steps"></span> · Copernicus <a id="fire-source" href="#" target="_blank" rel="noopener"></a></span>
					<span id="fire-note"></span>
				</div>""",
        "Aufklappen zeigt die Nebenangaben",
    ),
    Mutation(
        "Aufklapper bleibt unbeschriftet",
        JS,
        '  $("#fire-details-label").text(text.details);',
        '  $("#fire-details-label").text("");',
        "Aufklapper ist sichtbar und beschriftet",
    ),
    Mutation(
        "Zahl und Datum wieder uebereinander",
        CSS,
        """	#map-controls {
		--compact-row: 1;
		display: grid;
		grid-template-columns: auto 1fr;""",
        """	#map-controls {
		--compact-row: 1;
		display: block;
		grid-template-columns: auto 1fr;""",
        "Zahl und Datum in einer Zeile",
    ),
    # Zwei Wege, den Zeitstrahl zu verlieren, und zwei verschiedene Pruefungen
    # dafuer. Das ist der Ertrag des ersten Mutationslaufs: die erste Fassung
    # dieser Mutation nahm #map-timeline aus der Regel "grid-column: 1 / -1"
    # heraus und erwartete, dass die Reihenfolge rot wird — sie blieb gruen, weil
    # die automatische Platzierung das Element in die naechste freie Zelle setzt,
    # also ebenfalls unter die erste Reihe. Es rutscht nicht nach oben, es wird
    # nur schmaler. Beides ist ein Fehler, aber ein anderer.
    Mutation(
        "Zeitstrahl verliert die zweite Spalte",
        CSS,
        """	#map-timeline,
	#fire-details {
		grid-column: 1 / -1;
	}""",
        """	#fire-details {
		grid-column: 1 / -1;
	}""",
        "Zeitstrahl nutzt die ganze Breite",
    ),
    Mutation(
        "Zeitstrahl rutscht neben das Datum",
        CSS,
        """		display: grid;
		grid-template-columns: auto 1fr;""",
        """		display: flex;
		grid-template-columns: auto 1fr;""",
        "Zeitstrahl unter Zahl und Datum",
    ),
    Mutation(
        "Griff erscheint auch bei Platz",
        CSS,
        """#fire-details > summary {
	display: none;
	cursor: pointer;""",
        """#fire-details > summary {
	display: block;
	cursor: pointer;""",
        "kein Aufklapp-Griff, wo Platz ist",
    ),
    # ---- Brandflaeche hinter den Kaesten ----
    Mutation(
        "Zustandsanzeige waechst ueber die Brandflaeche",
        CSS,
        """@media (max-height: 440px), (max-width: 460px), (max-height: 540px) and (max-width: 700px) {
	#map-controls {
		--compact: 1;
	}""",
        """@media (max-height: 440px), (max-width: 460px) {
	#map-controls {
		--compact: 1;
	}""",
        "Brandfläche nicht hinter den Kästen",
    ),
]


def main(argv):
    harnisch.MUTATIONEN = MUTATIONEN
    return harnisch.main(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
