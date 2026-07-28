#!/usr/bin/env python3
"""Tests fuer die Rechenlogik der Datenpipeline.

Geprueft wird das, was still falsch werden kann, ohne dass es auffaellt: die
Flaechenberechnung, die Neuabtastung der Umrisse, die Wahl des
Darstellungsmodus, das Filtern der Produkte und das Zusammenfuehren von
Teil-Laeufen.

    python3 tests/test_geometry.py

Laeuft mit der Standardbibliothek. shapely ist nur fuer die Tests noetig, die
Geometrien verschmelzen - fehlt es, werden diese uebersprungen statt zu scheitern.
"""

import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bin"))

import fetch_ems  # noqa: E402


def square(lon, lat, side_deg):
    """Geschlossener Ring eines achsenparallelen Quadrats in Grad."""
    return [
        (lon, lat),
        (lon + side_deg, lat),
        (lon + side_deg, lat + side_deg),
        (lon, lat + side_deg),
        (lon, lat),
    ]


class TestFlaechenberechnung(unittest.TestCase):
    """ring_area_m2 rechnet auf der Kugel. Gegengeprueft wird mit der ebenen
    Naeherung, die bei kleinen Flaechen sehr genau ist."""

    def test_kleines_quadrat_am_aequator(self):
        side = 0.01
        got = fetch_ems.ring_area_m2(square(0.0, 0.0, side))
        # Am Aequator sind ein Laengen- und ein Breitengrad naeherungsweise
        # gleich lang.
        meter_pro_grad = 6371008.8 * math.pi / 180
        erwartet = (side * meter_pro_grad) ** 2
        self.assertAlmostEqual(got / erwartet, 1.0, delta=0.01)

    def test_quadrat_in_mittleren_breiten_ist_kleiner(self):
        """Bei 60 Grad Nord ist ein Laengengrad halb so lang wie am Aequator."""
        side = 0.01
        aequator = fetch_ems.ring_area_m2(square(0.0, 0.0, side))
        norden = fetch_ems.ring_area_m2(square(0.0, 60.0, side))
        self.assertAlmostEqual(norden / aequator, 0.5, delta=0.02)

    def test_umlaufrichtung_egal(self):
        ring = square(10.0, 45.0, 0.02)
        self.assertAlmostEqual(
            fetch_ems.ring_area_m2(ring),
            fetch_ems.ring_area_m2(list(reversed(ring))),
            delta=1.0,
        )

    def test_hektar_umrechnung(self):
        """Ein Quadrat von 1000 m Seite ist genau 100 ha."""
        try:
            from shapely.geometry import Polygon
        except ImportError:
            self.skipTest("shapely nicht vorhanden")
        # 1000 m entsprechen bei 0 Grad etwa 0.008983 Grad.
        side = 1000.0 / (6371008.8 * math.pi / 180)
        poly = Polygon(square(0.0, 0.0, side))
        self.assertAlmostEqual(fetch_ems.polygon_area_ha(poly) / 100.0, 1.0, delta=0.01)

    def test_loecher_werden_abgezogen(self):
        try:
            from shapely.geometry import Polygon
        except ImportError:
            self.skipTest("shapely nicht vorhanden")
        aussen = square(0.0, 45.0, 0.10)
        innen = square(0.03, 45.03, 0.04)
        mit_loch = Polygon(aussen, [innen])
        ohne_loch = Polygon(aussen)
        nur_loch = Polygon(innen)
        self.assertAlmostEqual(
            fetch_ems.polygon_area_ha(mit_loch),
            fetch_ems.polygon_area_ha(ohne_loch) - fetch_ems.polygon_area_ha(nur_loch),
            delta=0.5,
        )


class TestNeuabtastung(unittest.TestCase):
    """resample_ring ersetzte eine fehlerhafte Toleranz-Eskalation, die den Umriss
    bei sieben Kilometern Toleranz zerstoerte und trotzdem 612 Stuetzpunkte
    behielt. Die Punktzahl muss deshalb verlaesslich gedeckelt sein."""

    def test_punktzahl_wird_getroffen(self):
        # Ein feiner Kreis mit 500 Punkten.
        ring = [(math.cos(i / 500 * 2 * math.pi), 45 + math.sin(i / 500 * 2 * math.pi)) for i in range(500)]
        ring.append(ring[0])
        out = fetch_ems.resample_ring(ring, 100)
        self.assertEqual(len(out), 101, "count Punkte plus Schlusspunkt")

    def test_ring_bleibt_geschlossen(self):
        ring = square(0.0, 45.0, 1.0)
        out = fetch_ems.resample_ring(ring, 40)
        self.assertEqual(out[0], out[-1], "erster und letzter Punkt muessen gleich sein")

    def test_kurze_ringe_bleiben_unveraendert(self):
        """Weniger Punkte als gefordert: nichts erfinden."""
        ring = square(0.0, 45.0, 1.0)  # 5 Punkte
        out = fetch_ems.resample_ring(ring, 100)
        self.assertEqual(len(out), len(ring))

    def test_form_bleibt_erhalten(self):
        """Die Neuabtastung darf die Flaeche nicht merklich veraendern - genau das
        war der Fehler der alten Toleranz-Eskalation."""
        ring = square(0.0, 45.0, 0.5)
        # Ring kuenstlich verfeinern, damit es etwas abzutasten gibt.
        fein = []
        for i in range(len(ring) - 1):
            a, b = ring[i], ring[i + 1]
            for k in range(50):
                t = k / 50
                fein.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
        fein.append(ring[0])

        vorher = fetch_ems.ring_area_m2(fein)
        nachher = fetch_ems.ring_area_m2(fetch_ems.resample_ring(fein, 64))
        self.assertAlmostEqual(nachher / vorher, 1.0, delta=0.02)

    def test_entartete_eingaben(self):
        einzelpunkt = [(1.0, 1.0), (1.0, 1.0), (1.0, 1.0)]
        out = fetch_ems.resample_ring(einzelpunkt, 10)
        self.assertTrue(len(out) >= 3, "darf nicht leer zurueckkommen")


class TestModuswahl(unittest.TestCase):
    """Die Modus-Entscheidung ist der inhaltlich wichtigste Schalter: bei La
    Atalaya stagnierte die Hauptflaeche bei 33 Prozent Anteil, waehrend die
    Gesamtflaeche stieg. Ein Ueberblenden haette dort Stillstand gezeigt."""

    def test_dominante_hauptflaeche_wird_ueberblendet(self):
        self.assertEqual(fetch_ems.pick_mode([0.92, 0.90]), "morph")

    def test_zerstreuter_brand_wird_eingeblendet(self):
        self.assertEqual(fetch_ems.pick_mode([0.81, 0.47, 0.33, 0.52]), "crossfade")

    def test_ein_einziger_zerstreuter_stand_entscheidet(self):
        """Der Durchschnitt laege hier ueber der Schwelle, der kleinste Wert nicht."""
        self.assertEqual(fetch_ems.pick_mode([0.99, 0.99, 0.40]), "crossfade")

    def test_schwelle_ist_inklusiv(self):
        self.assertEqual(fetch_ems.pick_mode([fetch_ems.MORPH_SHARE_THRESHOLD]), "morph")

    def test_leere_reihe_faellt_auf_die_sichere_seite(self):
        self.assertEqual(fetch_ems.pick_mode([]), "crossfade")


class TestProduktfilter(unittest.TestCase):
    """delivered_products entscheidet, welche Staende in die Animation kommen.
    Ein Fehler hier laesst Zeitschnitte still verschwinden."""

    @staticmethod
    def produkt(status, acq, typ="DEL", layer="observedEventA", feasible=True):
        layers = []
        if layer:
            layers = [{"json": f"https://example.invalid/x_{layer}_v1.json"}]
        return {
            "type": typ,
            "feasible": feasible,
            "version": {"statusCode": status},
            "layers": layers,
            "images": [{"acquisitionTime": acq}] if acq else [],
        }

    def test_nur_ausgelieferte_produkte(self):
        aoi = {
            "products": [
                self.produkt("F", "2026-07-25T10:00:00"),
                self.produkt("W", "2026-07-26T10:00:00"),  # angekuendigt
                self.produkt("I", "2026-07-27T10:00:00"),  # in Produktion
            ]
        }
        got = fetch_ems.delivered_products(aoi)
        self.assertEqual([p["acquired"] for p in got], ["2026-07-25T10:00:00"])

    def test_chronologisch_sortiert(self):
        aoi = {
            "products": [
                self.produkt("F", "2026-07-27T10:00:00"),
                self.produkt("F", "2026-07-25T10:00:00"),
                self.produkt("F", "2026-07-26T10:00:00"),
            ]
        }
        got = [p["acquired"] for p in fetch_ems.delivered_products(aoi)]
        self.assertEqual(got, sorted(got))

    def test_ohne_flaechenebene_wird_verworfen(self):
        aoi = {"products": [self.produkt("F", "2026-07-25T10:00:00", layer=None)]}
        self.assertEqual(fetch_ems.delivered_products(aoi), [])

    def test_ohne_aufnahmezeit_wird_verworfen(self):
        """Ohne Zeitstempel liesse sich der Stand nicht einordnen."""
        aoi = {"products": [self.produkt("F", None)]}
        self.assertEqual(fetch_ems.delivered_products(aoi), [])

    def test_nicht_beauftragte_produkte_werden_verworfen(self):
        aoi = {"products": [self.produkt("F", "2026-07-25T10:00:00", feasible=False)]}
        self.assertEqual(fetch_ems.delivered_products(aoi), [])

    def test_grading_zaehlt_mit(self):
        """GRA verlaengert die Reihe, wenn es spaeter aufgenommen wurde."""
        aoi = {
            "products": [
                self.produkt("F", "2026-07-24T10:00:00", typ="DEL"),
                self.produkt("F", "2026-07-27T14:00:00", typ="GRA"),
            ]
        }
        self.assertEqual(len(fetch_ems.delivered_products(aoi)), 2)


class TestBestandLesen(unittest.TestCase):
    """load_existing haelt bei einem Teil-Lauf die uebrigen Braende. Ohne das
    loeschte ein Lauf fuer einen einzelnen Brand alle anderen aus der Ausgabe."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original = fetch_ems.OUT_FILE
        fetch_ems.OUT_FILE = Path(self.tmp.name) / "fires.js"

    def tearDown(self):
        fetch_ems.OUT_FILE = self.original
        self.tmp.cleanup()

    def schreibe(self, fires):
        fetch_ems.OUT_FILE.write_text("/* erzeugt */\nvar _fires = " + json.dumps(fires) + ";\n", encoding="utf-8")

    def test_fehlende_datei_gilt_als_leer(self):
        self.assertEqual(fetch_ems.load_existing(), {})

    def test_liest_slugs(self):
        self.schreibe(
            [
                {"slug": "a", "steps": [{"acquired": "2026-07-25T10:00:00"}]},
                {"slug": "b", "steps": []},
            ]
        )
        got = fetch_ems.load_existing()
        self.assertEqual(sorted(got), ["a", "b"])
        self.assertEqual(got["a"]["steps"][0]["acquired"], "2026-07-25T10:00:00")

    def test_beschaedigte_datei_gilt_als_leer(self):
        fetch_ems.OUT_FILE.write_text("var _fires = [ das ist kein JSON", encoding="utf-8")
        self.assertEqual(fetch_ems.load_existing(), {})

    def test_leere_datei_gilt_als_leer(self):
        fetch_ems.OUT_FILE.write_text("", encoding="utf-8")
        self.assertEqual(fetch_ems.load_existing(), {})


class TestKonfiguration(unittest.TestCase):
    """Die Liste FIRES wird von Hand gepflegt - Tippfehler darin faenden sonst
    erst beim naechsten Lauf auf."""

    def test_slugs_sind_eindeutig(self):
        slugs = [c["slug"] for c in fetch_ems.FIRES]
        self.assertEqual(len(slugs), len(set(slugs)))

    def test_aktivierung_und_aoi_sind_eindeutig(self):
        paare = [(c["activation"], c["aoi"]) for c in fetch_ems.FIRES]
        self.assertEqual(len(paare), len(set(paare)))

    def test_pflichtfelder_vorhanden(self):
        pflicht = {
            "slug",
            "activation",
            "aoi",
            "name_de",
            "name_en",
            "region_de",
            "region_en",
            "timezone_label",
        }
        for config in fetch_ems.FIRES:
            self.assertTrue(
                pflicht <= set(config),
                f"{config.get('slug')} fehlt: {pflicht - set(config)}",
            )

    def test_aktivierungscodes_wohlgeformt(self):
        for config in fetch_ems.FIRES:
            self.assertRegex(config["activation"], r"^EMSR\d{3,4}$")

    def test_slugs_sind_ankertauglich(self):
        """Die Slugs landen im Anker der Adresse."""
        for config in fetch_ems.FIRES:
            self.assertRegex(config["slug"], r"^[a-z0-9-]+$")


if __name__ == "__main__":
    unittest.main(verbosity=2)
