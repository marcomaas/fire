"""Strukturprüfungen der HTML-Seiten.

Diese Tests fangen die Fehlerklasse, die in dieser Anwendung dreimal aufgetreten
ist: eine Aussage steht als Text in der Seite, die Daten ändern sich, und der Text
ist still falsch. Dazu kommen zwei Klassen aus derselben Familie — eine
Sprachfassung wird nachgezogen, die andere nicht, und ein Pflichtverweis fehlt auf
einer einzelnen Seite.

Es sind bewusst reine Textprüfungen ohne Browser: sie laufen in Millisekunden und
brauchen kein Chrome, damit sie in jedem Lauf mitgehen und nicht nur im
Layout-Testlauf.
"""

import json
import re
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app"

SEITEN = ["index-de.html", "index-en.html", "beispiel.html", "beispiel-en.html"]

# Paare, die strukturgleich sein müssen: dieselben Element-IDs, dieselbe Anzahl
# Codebeispiele. Der Inhalt darf sich unterscheiden, das Gerüst nicht.
PAARE = [("index-de.html", "index-en.html"), ("beispiel.html", "beispiel-en.html")]

# Deutsche Wörter, die in dieser Anwendung schon einmal als ASCII-Ersatz in
# sichtbarem Text standen. Absichtlich eine kurze, konkrete Liste statt einer
# Regex auf "ae|oe|ue" — sonst schlägt sie bei Slugs wie "koeln" oder
# "waldbraende" an, die genau so heißen müssen.
ASCII_ERSATZ = [
    "Flaeche",
    "Groesse",
    "fuer",
    "ueber",
    "Braende",
    "kueste",
    "noerdlich",
    "oestlich",
    "westliche Atlantikkueste",
    "ergaenzen",
    "Europaeische",
    "unveraendert",
]


def lade(name):
    return (APP / name).read_text(encoding="utf-8")


def ids_von(markup):
    return set(re.findall(r'\bid="([^"]+)"', markup))


def fires_daten():
    roh = (APP / "assets" / "data" / "fires.js").read_text(encoding="utf-8")
    return json.loads(roh[roh.index("=") + 1 :].strip().rstrip(";"))


class TestSeitenGeruest(unittest.TestCase):
    def test_alle_seiten_existieren(self):
        for name in SEITEN:
            self.assertTrue((APP / name).is_file(), f"{name} fehlt")

    def test_sprachfassungen_haben_dieselben_ids(self):
        """Wenn eine Fassung ein Element bekommt, die andere nicht, bleibt dort
        eine Zahl oder ein Hinweis leer — ohne dass es auffällt."""
        for a, b in PAARE:
            fehlt_in_b = ids_von(lade(a)) - ids_von(lade(b))
            fehlt_in_a = ids_von(lade(b)) - ids_von(lade(a))
            self.assertEqual(
                (set(), set()),
                (fehlt_in_b, fehlt_in_a),
                f"{a} und {b} haben unterschiedliche Element-IDs: "
                f"nur in {a}: {sorted(fehlt_in_b)}, nur in {b}: {sorted(fehlt_in_a)}",
            )

    def test_beispielseiten_zeigen_gleich_viele_codebloecke(self):
        for a, b in [PAARE[1]]:
            self.assertEqual(
                lade(a).count("<pre"),
                lade(b).count("<pre"),
                f"{a} und {b} zeigen unterschiedlich viele Codebeispiele",
            )
            self.assertEqual(
                lade(a).count("<iframe"),
                lade(b).count("<iframe"),
                f"{a} und {b} zeigen unterschiedlich viele Rahmen",
            )


class TestPflichtverweise(unittest.TestCase):
    def test_jede_seite_verweist_aufs_impressum(self):
        """Harte Regel für veröffentlichte Seiten. In der Anwendung selbst steckt
        der Verweis zusätzlich in der Herkunftszeile der Karte, weil das die
        einzige im Rahmen sichtbare Stelle ist."""
        for name in SEITEN:
            self.assertIn(
                "datenfreunde.com/impressum",
                lade(name),
                f"{name} hat keinen Impressum-Verweis",
            )

    def test_lizenzangabe_nennt_mit_und_nicht_cc_by(self):
        """Der Code steht unter MIT. CC-BY stand vorher an vier Stellen und
        widersprach der LICENSE-Datei."""
        for name in SEITEN:
            markup = lade(name)
            self.assertNotIn(
                "creativecommons.org/licenses",
                markup,
                f"{name} verweist noch auf eine CC-Lizenz",
            )
            self.assertIn("LICENSE", markup, f"{name} verlinkt die Lizenzdatei nicht")

    def test_anwendung_verlinkt_die_beispielseite(self):
        for seite, beispiel in [
            ("index-de.html", "beispiel.html"),
            ("index-en.html", "beispiel-en.html"),
        ]:
            self.assertIn(
                f'href="{beispiel}"',
                lade(seite),
                f"{seite} verlinkt {beispiel} nicht — dann findet sie niemand",
            )


class TestKeineFestenZahlenImText(unittest.TestCase):
    """Zahlen, die sich mit den Daten ändern, dürfen nicht im Text stehen."""

    def test_anzahl_der_braende_kommt_aus_den_daten(self):
        for name in SEITEN:
            markup = lade(name)
            self.assertRegex(
                markup,
                r'id="(info-count|count-words|count-fires)"',
                f"{name} nennt die Zahl der Brände nicht über ein füllbares Element",
            )

    def test_kein_fester_stundenbereich_im_infokasten(self):
        """ "21 bis 106 Stunden" stand fest in der Seite und war mit dem fünften
        Brand falsch."""
        for name in ("index-de.html", "index-en.html"):
            self.assertNotRegex(
                lade(name),
                r"\d+\s*(bis|to)\s*\d+\s*(Stunden|hours)",
                f"{name} nennt eine feste Stundenspanne",
            )

    def test_ankerliste_wird_erzeugt(self):
        """Die Liste der Anker stand handgeschrieben in der Seite und verlor den
        fünften Brand."""
        for name in ("beispiel.html", "beispiel-en.html"):
            markup = lade(name)
            self.assertIn('id="anchor-list"', markup)
            for fire in fires_daten():
                self.assertNotIn(
                    f"#{fire['slug']}  ",
                    markup,
                    f"{name} listet #{fire['slug']} noch als festen Text",
                )

    def test_jeder_brand_ist_ueber_seinen_anker_erreichbar(self):
        """Kein Test auf die Liste selbst, sondern auf die Daten: jeder Brand
        braucht einen Slug, aus dem ein Anker werden kann."""
        slugs = [f["slug"] for f in fires_daten()]
        self.assertEqual(len(slugs), len(set(slugs)), "doppelte Slugs")
        for slug in slugs:
            self.assertRegex(slug, r"^[a-z0-9-]+$", f"Slug {slug!r} taugt nicht als Anker")


class TestRechtschreibung(unittest.TestCase):
    def test_keine_ascii_ersetzungen_in_sichtbarem_text(self):
        for name in SEITEN:
            markup = lade(name)
            for wort in ASCII_ERSATZ:
                self.assertNotIn(wort, markup, f"{name} enthält die ASCII-Ersetzung {wort!r}")

    def test_keine_ascii_ersetzungen_in_den_daten(self):
        """Die Regionsangaben stehen sichtbar unter der Karte."""
        for fire in fires_daten():
            text = json.dumps(fire.get("region", {}), ensure_ascii=False) + json.dumps(
                fire.get("name", {}), ensure_ascii=False
            )
            for wort in ASCII_ERSATZ:
                self.assertNotIn(wort, text, f"{fire['slug']}: ASCII-Ersetzung {wort!r} in den Daten")

    def test_keine_escapten_anfuehrungszeichen_im_markup(self):
        r"""Ein \" im HTML kommt aus einem Skript, das die Seite bearbeitet hat —
        das Attribut ist dann kaputt, ohne dass der Browser meckert."""
        for name in SEITEN:
            self.assertNotIn('\\"', lade(name), f"{name} enthält escapte Anführungszeichen")


class TestVerweiseZeigenAufVorhandenes(unittest.TestCase):
    def test_lokale_verweise_existieren(self):
        muster = re.compile(r'(?:href|src)="(?!https?:|javascript:|#|mailto:)([^"#?]+)')
        for name in SEITEN:
            for ziel in set(muster.findall(lade(name))):
                self.assertTrue(
                    (APP / ziel).exists(),
                    f"{name} verweist auf {ziel}, das es nicht gibt",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
