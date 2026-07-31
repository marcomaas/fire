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

import ast
import json
import re
import unittest
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
APP = WURZEL / "app"

# Verzeichnisse, deren Inhalt nicht von uns stammt oder nicht ausgeliefert wird.
FREMD = {"vendor", "node_modules", ".venv", ".git", ".pytest_cache", "__pycache__"}

SEITEN = [
    "index-de.html",
    "index-en.html",
    "beispiel.html",
    "beispiel-en.html",
    "konfigurieren.html",
]

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

# Dieselbe Fehlerklasse in den Meldungen der Pipeline. Die stehen zwar nicht in der
# Anwendung, aber auf der Konsole von jemandem, der die Daten nachzieht — deutscher
# Text bleibt deutscher Text.
ASCII_ERSATZ_KONSOLE = ASCII_ERSATZ + [
    "geprueft",
    "UNGEPRUEFT",
    "unvollstaendig",
    "Spaeter",
    "uebersprungen",
    "naechst",
    "moeglich",
    "noetig",
    "zurueck",
]


def lade(name):
    return (APP / name).read_text(encoding="utf-8")


def eigene_dateien(endung):
    """Alle Dateien dieser Endung, die von uns stammen — ohne Fremdverzeichnisse.

    Bewusst über den ganzen Baum statt über eine Liste: eine neu angelegte Seite
    oder Dokumentationsdatei soll von den folgenden Prüfungen automatisch erfasst
    werden. Genau daran hing der Lizenzwiderspruch — README.md stand in keiner
    Prüfliste und behauptete deshalb monatelang unbemerkt CC BY 3.0.
    """
    return [p for p in WURZEL.rglob(f"*{endung}") if not FREMD.intersection(p.relative_to(WURZEL).parts)]


def konsolentexte(pfad):
    """Die festen Textbausteine aller print-Aufrufe einer Python-Datei.

    Über den Syntaxbaum statt über eine Regex, damit Kommentare und Docstrings
    außen vor bleiben: die sieht niemand außer beim Lesen des Codes, und dort ist
    die Schreibweise eine andere Frage als bei einer Meldung an den Aufrufer.
    """
    baum = ast.parse(pfad.read_text(encoding="utf-8"))
    texte = []
    for knoten in ast.walk(baum):
        if not isinstance(knoten, ast.Call):
            continue
        if not (isinstance(knoten.func, ast.Name) and knoten.func.id == "print"):
            continue
        for argument in knoten.args:
            for teil in ast.walk(argument):
                if isinstance(teil, ast.Constant) and isinstance(teil.value, str):
                    texte.append((teil.lineno, teil.value))
    return texte


def ids_von(markup):
    return set(re.findall(r'\bid="([^"]+)"', markup))


def fires_daten():
    roh = (APP / "assets" / "data" / "fires.js").read_text(encoding="utf-8")
    return json.loads(roh[roh.index("=") + 1 :].strip().rstrip(";"))


def cities_daten():
    roh = (APP / "assets" / "data" / "cities.js").read_text(encoding="utf-8")
    return json.loads(roh[roh.index("=") + 1 :].strip().rstrip(";"))


def gebaute_staedte():
    """Die Kürzel aus der Liste CITIES in bin/build_cities.py, in ihrer Reihenfolge.

    Über den Syntaxbaum statt über eine Regex: die Liste enthält Umlaute in den
    Anzeigenamen und wird von Hand gepflegt.
    """
    baum = ast.parse((WURZEL / "bin" / "build_cities.py").read_text(encoding="utf-8"))
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Assign):
            ziele = [z.id for z in knoten.targets if isinstance(z, ast.Name)]
            if "CITIES" in ziele and isinstance(knoten.value, ast.List):
                kuerzel = []
                for eintrag in knoten.value.elts:
                    werte = dict(
                        zip(
                            [k.value for k in eintrag.keys],
                            [v.value if isinstance(v, ast.Constant) else None for v in eintrag.values],
                        )
                    )
                    kuerzel.append(werte["slug"])
                return kuerzel
    raise AssertionError("CITIES nicht in bin/build_cities.py gefunden")


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

    def test_keine_datei_im_baum_behauptet_eine_cc_lizenz(self):
        """Die Prüfung oben sah nur die vier Seiten. README.md stand in keiner
        Liste und nannte deshalb weiter CC BY 3.0 — und verwies für diese
        Behauptung auf genau die LICENSE-Datei, die MIT sagt.
        """
        for pfad in eigene_dateien(".md") + eigene_dateien(".html"):
            self.assertNotIn(
                "creativecommons.org/licenses",
                pfad.read_text(encoding="utf-8"),
                f"{pfad.relative_to(WURZEL)} verweist auf eine CC-Lizenz, LICENSE sagt aber MIT",
            )

    def test_lizenzdatei_nennt_mit_und_beide_urheberjahre(self):
        """Die Fassung von 2013 stammt von OpenDataCity, die von 2026 von den
        Datenfreunden. Die alte Zeile wird ergänzt, nicht ersetzt.
        """
        lizenz = (WURZEL / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("MIT License", lizenz, "LICENSE nennt die MIT-Lizenz nicht")
        for jahr, halter in [("2013", "OpenDataCity"), ("2026", "Datenfreunde")]:
            self.assertRegex(
                lizenz,
                rf"Copyright \(c\) {jahr} {halter}",
                f"LICENSE nennt keine Copyright-Zeile {jahr} {halter}",
            )

    def test_readme_nennt_die_mit_lizenz(self):
        readme = (WURZEL / "README.md").read_text(encoding="utf-8")
        self.assertIn("MIT-Lizenz", readme, "README nennt die Lizenz des Codes nicht")

    def test_openstreetmap_wird_in_der_form_genannt_die_die_odbl_verlangt(self):
        """Rechteinhaber sind die Mitwirkenden, nicht OpenStreetMap und dazu noch
        weitere. "OpenStreetMap und Mitwirkende" stand in beispiel.html und im
        README, während LICENSE und beide englischen Fassungen die richtige Form
        trugen — dieselbe Angabe, vier Schreibweisen.
        """
        for pfad in eigene_dateien(".md") + eigene_dateien(".html") + [WURZEL / "LICENSE"]:
            roh = pfad.read_text(encoding="utf-8")
            if "OpenStreetMap" not in roh:
                continue
            text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", roh))
            name = pfad.relative_to(WURZEL)
            self.assertNotIn(
                "OpenStreetMap und Mitwirkende",
                text,
                f"{name} nennt OpenStreetMap und die Mitwirkenden als zwei Parteien",
            )
            self.assertTrue(
                "OpenStreetMap-Mitwirkende" in text or "OpenStreetMap contributors" in text,
                f"{name} nennt OpenStreetMap, aber nicht die Mitwirkenden als Rechteinhaber",
            )

    def test_jede_seite_verlinkt_die_konfigurationsseite(self):
        """Sie ist der einzige Weg, einen eingeschränkten Einbettungscode zu
        bekommen, ohne die Adresse von Hand zu bauen. Unverlinkt findet sie
        niemand."""
        for name in SEITEN:
            if name == "konfigurieren.html":
                continue
            self.assertIn(
                'href="konfigurieren.html"',
                lade(name),
                f"{name} verlinkt die Konfigurationsseite nicht",
            )

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

    # Seiten, die die Zahl der Brände im Text nennen. Die Konfigurationsseite
    # steht bewusst nicht dabei: sie erzeugt ihre Angaben durchgängig aus den
    # Daten und hat keinen Satz, in dem eine Zahl stehen könnte.
    SEITEN_MIT_ZAHL = ["index-de.html", "index-en.html", "beispiel.html", "beispiel-en.html"]

    def test_anzahl_der_braende_kommt_aus_den_daten(self):
        for name in self.SEITEN_MIT_ZAHL:
            markup = lade(name)
            self.assertRegex(
                markup,
                r'id="(info-count|count-words|count-fires)"',
                f"{name} nennt die Zahl der Brände nicht über ein füllbares Element",
            )

    def test_keine_ausgeschriebene_anzahl_im_text(self):
        """Der eigentliche Fehler war nicht ein fehlendes Element, sondern eine
        Zahl im Satz. Diese Prüfung greift auf jeder Seite, auch auf einer neu
        angelegten, und braucht keine Pflegeliste."""
        zahlwoerter = "zwei|drei|vier|fünf|sechs|sieben|acht|neun|zehn|two|three|four|five|six|seven|eight|nine|ten"
        muster = re.compile(rf"\b({zahlwoerter})\s+(Brände|Bränden|fires)\b")
        # Nur ausgelieferte Seiten. Die Testseiten unter tests/ beschreiben in
        # ihren Kommentaren vergangene Messungen und sind ohnehin nie öffentlich.
        for pfad in [d for d in eigene_dateien(".html") if d.is_relative_to(APP)]:
            # Kommentare bleiben außen vor: dort steht mitunter eine historische
            # Messung ("gemessen war einer von fünf Bränden sichtbar"), die sich
            # auf einen vergangenen Zustand bezieht und deshalb nicht veraltet.
            # Skripte bleiben drin — eine feste Zahl in einer Zeichenkette wäre
            # genau der Fehler, um den es hier geht.
            ohne_kommentare = re.sub(r"<!--.*?-->", "", pfad.read_text(encoding="utf-8"), flags=re.S)
            for treffer in muster.finditer(ohne_kommentare):
                self.fail(
                    f"{pfad.relative_to(WURZEL)} schreibt die Zahl aus: "
                    f"{treffer.group(0)!r} — sie veraltet mit den Daten"
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


class TestStaedteauswahl(unittest.TestCase):
    """Die Städteliste ist kuratiert, nicht gewachsen.

    Sie war einmal neun Einträge lang, und in einem eingebetteten Rahmen war der
    letzte nur nach unentdecktem Scrollen erreichbar. Eine Obergrenze im Test
    hält die Entscheidung fest: eine sechste Stadt macht diese Prüfung rot und
    verlangt damit, dass jemand die Wahl trifft, statt sie anzuhängen.
    """

    OBERGRENZE = 5

    # Städte außerhalb Europas, die einmal in der Liste standen. Titel,
    # Beschreibung und Info-Kasten aller Fassungen sprechen von einem Vergleich
    # mit europäischen Städten — ein Eintrag hier widerlegt sie.
    AUSSEREUROPAEISCH = ["manhattan", "sacramento", "new-york", "yosemite"]

    def test_liste_bleibt_bei_fuenf_eintraegen(self):
        slugs = [c["slug"] for c in cities_daten()]
        self.assertEqual(
            len(slugs),
            self.OBERGRENZE,
            f"cities.js führt {len(slugs)} Städte ({', '.join(slugs)}) — kuratiert sind {self.OBERGRENZE}",
        )
        self.assertEqual(len(slugs), len(set(slugs)), "doppelte Städte")

    def test_keine_aussereuropaeische_stadt(self):
        slugs = [c["slug"] for c in cities_daten()]
        for verboten in self.AUSSEREUROPAEISCH:
            self.assertNotIn(
                verboten,
                slugs,
                f"{verboten} liegt nicht in Europa, die Seitenbeschreibung behauptet es aber",
            )

    def test_daten_und_bauskript_nennen_dieselben_staedte(self):
        """Die ausgelieferte Datei und die Liste, aus der sie entsteht, dürfen
        nicht auseinanderlaufen. Genau das passiert sonst beim Kürzen von Hand:
        cities.js wird kleiner, der nächste Lauf von bin/build_cities.py macht
        alles rückgängig."""
        self.assertEqual(
            [c["slug"] for c in cities_daten()],
            gebaute_staedte(),
            "cities.js und CITIES in bin/build_cities.py stimmen nicht überein",
        )

    def test_jede_stadt_hat_umriss_und_mittelpunkt(self):
        for city in cities_daten():
            self.assertTrue(city["rings"], f"{city['slug']} hat keinen Umriss")
            self.assertEqual(len(city["center"]), 2, f"{city['slug']} hat keinen Mittelpunkt")
            for sprache in ("de", "en"):
                self.assertTrue(
                    city["label"].get(sprache),
                    f"{city['slug']} hat keinen Namen für {sprache}",
                )

    def test_zu_jedem_brand_liegt_eine_stadt_in_der_naehe(self):
        """markNearestCity schlägt je Brand die nächstgelegene Stadt vor. Fällt
        beim Kürzen die einzige Stadt in der Nähe eines Brandes heraus, ist der
        Vorschlag formal noch da, zeigt aber auf die andere Seite Europas.
        Gemessen wird in Grad, nicht in Kilometern — für eine Obergrenze genügt
        das."""
        staedte = cities_daten()
        for fire in fires_daten():
            abstaende = [
                max(
                    abs(city["center"][0] - fire["center"][0]),
                    abs(city["center"][1] - fire["center"][1]),
                )
                for city in staedte
            ]
            self.assertLess(
                min(abstaende),
                6.0,
                f"zu {fire['slug']} liegt keine der Städte näher als 6 Grad — "
                f"der Vorschlag der nächstgelegenen Stadt wird unbrauchbar",
            )


class TestUeberDenGanzenBaum(unittest.TestCase):
    """Prüfungen, die nicht an einer Liste von Dateien hängen.

    Der Lizenzwiderspruch hielt sich monatelang, weil README.md in keiner
    Prüfliste stand. Eine Prüfung, die man beim Anlegen einer Datei erweitern
    muss, greift genau dann nicht, wenn es darauf ankommt.
    """

    def test_keine_cc_lizenz_in_eigenen_dateien(self):
        """Gesucht wird die Adresse, nicht die Zeichenfolge "CC BY": README.md
        erwähnt sie bewusst, um den früheren Fehler zu dokumentieren."""
        for endung in (".html", ".md"):
            for pfad in eigene_dateien(endung):
                self.assertNotIn(
                    "creativecommons.org/licenses",
                    pfad.read_text(encoding="utf-8"),
                    f"{pfad.relative_to(WURZEL)} verweist auf eine CC-Lizenz — der Code steht unter MIT",
                )

    def test_konsolenmeldungen_tragen_umlaute(self):
        """Meldungen der Pipeline liest jemand, der die Daten nachzieht.
        Deutscher Text bleibt deutscher Text — auch auf der Konsole.

        Geprüft wird über den Syntaxbaum, damit Kommentare außen vor bleiben:
        deren Schreibweise ist eine andere Frage als die einer Meldung, und die
        Slugs (koeln, muenchen, waldbraende) dürfen sich ohnehin nicht ändern.
        """
        for pfad in eigene_dateien(".py"):
            for zeile, text in konsolentexte(pfad):
                for wort in ASCII_ERSATZ_KONSOLE:
                    self.assertNotIn(
                        wort,
                        text,
                        f"{pfad.relative_to(WURZEL)}:{zeile} meldet {wort!r} statt der Umlautschreibweise: {text!r}",
                    )


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

    def test_keine_ascii_ersetzungen_in_den_meldungen_der_pipeline(self):
        """Die Vorlage für neue Brände wird aus discover herauskopiert, samt
        Regionstext. Stand dort eine Ersatzschreibung, wanderte sie in die Daten
        und von dort unter die Karte.
        """
        pfade = sorted((WURZEL / "bin").glob("*.py"))
        self.assertTrue(pfade, "keine Pipeline-Skripte gefunden — Prüfung wäre leer")
        for pfad in pfade:
            for zeile, text in konsolentexte(pfad):
                for wort in ASCII_ERSATZ_KONSOLE:
                    self.assertNotIn(
                        wort,
                        text,
                        f"{pfad.name}:{zeile} gibt {wort!r} aus",
                    )

    def test_keine_escapten_anfuehrungszeichen_im_markup(self):
        r"""Ein \" im HTML kommt aus einem Skript, das die Seite bearbeitet hat —
        das Attribut ist dann kaputt, ohne dass der Browser meckert."""
        for name in SEITEN:
            self.assertNotIn('\\"', lade(name), f"{name} enthält escapte Anführungszeichen")


class TestVerweiseZeigenAufVorhandenes(unittest.TestCase):
    def test_lokale_verweise_existieren(self):
        # Nur Angaben, die tatsächlich wie ein Dateiname aussehen. Ohne diese
        # Einschränkung greift das Muster auch in Skripten, wo src aus Teilen
        # zusammengesetzt wird (src="' + url + '").
        muster = re.compile(
            r'(?:href|src)="(?!https?:|javascript:|#|mailto:|data:)'
            r'([A-Za-z0-9._/-]+\.[A-Za-z0-9]{2,5})(?=["#?])'
        )
        for name in SEITEN:
            for ziel in set(muster.findall(lade(name))):
                self.assertTrue(
                    (APP / ziel).exists(),
                    f"{name} verweist auf {ziel}, das es nicht gibt",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
