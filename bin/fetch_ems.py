#!/usr/bin/env python3
"""Holt datierte Brandperimeter aus dem Copernicus EMS Rapid Mapping Service.

Ersetzt die 2013er Node-Kette (bin/rimfire.js), die auf dem 2020 abgeschalteten
GeoMAC-KML-Dienst der USGS aufsetzte.

Quelle ist die Rapid-Mapping-Activations-API. Pro Aktivierung und Area of Interest
liefert sie eine Serie von Produkten: eine erste Delineation und danach
durchnummerierte Monitoring-Stände. Jeder Stand traegt den Aufnahmezeitpunkt der
zugrunde liegenden Satellitenszene, und genau diese Serie ist es, welche die
Morphing-Animation im Frontend braucht.

Schema der API: /static/cems_rapidmapping_openapi_specs.yaml auf dem Portal.

Ausgabe: app/assets/data/fires.js
"""

import json
import math
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/public-activations/"

ROOT = Path(__file__).resolve().parent.parent
OUT_FILE = ROOT / "app" / "assets" / "data" / "fires.js"

# Welche Braende dargestellt werden. Ein Eintrag entspricht einer Area of
# Interest innerhalb einer EMS-Aktivierung, denn eine Aktivierung kann mehrere
# raeumlich getrennte Braende umfassen.
FIRES = [
    {
        "slug": "gironde",
        "activation": "EMSR899",
        "aoi": 1,
        "name_de": "Gironde, Frankreich",
        "name_en": "Gironde, France",
        "region_de": "Saumos und Le Porge, westlich von Bordeaux",
        "region_en": "Saumos and Le Porge, west of Bordeaux",
        "timezone_label": "CEST",
    },
    {
        "slug": "central-spain",
        "activation": "EMSR900",
        "aoi": 3,
        "name_de": "La Atalaya, Spanien",
        "name_en": "La Atalaya, Spain",
        "region_de": "Zentralspanien, westlich von Madrid",
        "region_en": "Central Spain, west of Madrid",
        "timezone_label": "CEST",
    },
    {
        "slug": "biscarrosse",
        "activation": "EMSR902",
        "aoi": 1,
        "name_de": "Biscarrosse, Frankreich",
        "name_en": "Biscarrosse, France",
        "region_de": "Landes, südwestliche Atlantikküste",
        "region_en": "Landes, south-western Atlantic coast",
        "timezone_label": "CEST",
    },
    {
        "slug": "artana",
        "activation": "EMSR905",
        "aoi": 1,
        "name_de": "Artana, Spanien",
        "name_en": "Artana, Spain",
        "region_de": "Plana Baixa, Provinz Castellón, nördlich von Valencia",
        "region_en": "Plana Baixa, Castellón province, north of Valencia",
        "timezone_label": "CEST",
    },
    {
        # Aelter als die uebrigen: Ereignis am 12.07.2026, Kartierung
        # abgeschlossen. Damit der erste Brand im Bestand, bei dem die Anwendung
        # den Zustand "abgeschlossen" anzeigt statt "laeuft weiter".
        "slug": "fontainebleau",
        "activation": "EMSR894",
        "aoi": 1,
        "name_de": "Fontainebleau, Frankreich",
        "name_en": "Fontainebleau, France",
        "region_de": "Seine-et-Marne, südöstlich von Paris",
        "region_en": "Seine-et-Marne, south-east of Paris",
        "timezone_label": "CEST",
    },
]

# Beobachtet, aber noch nicht aufgenommen: EMSR906 "Wildfires in Province of
# Leon, Spain". Dort lag am 28.07.2026 nur ein einziges ausgeliefertes
# Flaechenprodukt vor - fuer eine Animation braucht es mindestens zwei
# Zeitschnitte. Sobald Copernicus nachliefert, genuegt hier ein weiterer
# Eintrag mit activation EMSR906 und der passenden AOI-Nummer.

# Die Delineation-Produkte sind sehr feingliedrig (bis ueber 25.000 Teilflaechen
# pro Stand). Der Morphing-Algorithmus im Frontend vergleicht jeden Punkt eines
# Umrisses mit jedem Punkt des naechsten und laeuft damit quadratisch. Ohne
# Obergrenze blockiert er den Browser, deshalb wird die Stuetzpunktzahl gedeckelt.
MAX_VERTICES = 320
SIMPLIFY_TOLERANCE = 0.0003  # Grad, entspricht grob 30 m
MIN_FRAGMENT_HA = 5.0  # Streufeuer unterhalb dieser Groesse verrauschen den Umriss
MAX_OTHER_PARTS = 250  # weitere gezeichnete Teilflaechen neben der groessten
OTHER_VERTICES = 48

# Ab diesem Anteil der groessten Teilflaeche an der Gesamtflaeche traegt eine
# Morphing-Animation die Aussage. Darunter verteilt sich das Feuer auf viele
# getrennte Flecken - dann waere ein Ueberblenden des groessten Umrisses
# irrefuehrend, weil er kaum waechst, waehrend die Gesamtflaeche steigt.
MORPH_SHARE_THRESHOLD = 0.7

# Rasterfang beim Verschmelzen, in Grad. Etwa ein Meter.
UNION_GRID_SIZE = 0.00001

TIMEOUT = 120
RETRIES = 4


class Blocked(Exception):
    """Der Dienst weist uns ab — Ratenbegrenzung oder Sperre.

    Bewusst von einem normalen Netzfehler unterschieden: ein Fehlschlag, der
    "existiert nicht" bedeutet, und einer, der "wir duerfen gerade nicht"
    bedeutet, verlangen unterschiedliche Reaktionen. Wer beides gleich behandelt,
    baut sich eine Suche, die bei Abweisung stillschweigend zu frueh aufhoert
    und "nichts Neues gefunden" meldet.
    """


def fetch_json(url):
    """Holt eine JSON-Antwort und wiederholt bei Netzfehlern mit Wartezeit.

    Die groessten Delineation-Produkte sind mehrere Megabyte gross; unter der
    Last einer laufenden Grosslage bricht der Server Verbindungen ab.

    Abweisungen mit 403 oder 429 werden NICHT wiederholt - ein wiederholter
    Versuch verschaerft die Ratenbegrenzung nur - und als Blocked gemeldet.
    """
    last = None
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "fire-viz/2.0 (+github.com/marcomaas/fire)"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as err:
            if err.code in (403, 429):
                raise Blocked(f"HTTP {err.code} — Ratenbegrenzung oder Sperre") from err
            # 404 und andere Statusfehler sind Aussagen ueber die Ressource,
            # kein Netzproblem. Einmal genuegt.
            if 400 <= err.code < 500:
                raise
            last = err
        except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError) as err:
            last = err
            if attempt < RETRIES - 1:
                wait = 4 * (attempt + 1)
                print(f"      Versuch {attempt + 1} fehlgeschlagen ({err}), warte {wait}s", flush=True)
                time.sleep(wait)
    raise last


def ring_area_m2(coords):
    """Flaeche eines geschlossenen Rings auf der Kugel, nach Chamberlain/Duquette."""
    radius = 6371008.8
    total = 0.0
    for i in range(len(coords) - 1):
        lon1, lat1 = math.radians(coords[i][0]), math.radians(coords[i][1])
        lon2, lat2 = math.radians(coords[i + 1][0]), math.radians(coords[i + 1][1])
        total += (lon2 - lon1) * (2 + math.sin(lat1) + math.sin(lat2))
    return abs(total * radius * radius / 2.0)


def polygon_area_ha(geom):
    """Flaeche eines (Multi)Polygons in Hektar, Loecher abgezogen."""
    polys = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
    total = 0.0
    for poly in polys:
        total += ring_area_m2(list(poly.exterior.coords))
        for hole in poly.interiors:
            total -= ring_area_m2(list(hole.coords))
    return total / 10000.0


def resample_ring(coords, count):
    """Legt count Stuetzpunkte in gleichen Abstaenden auf einen geschlossenen Ring.

    Der Morphing-Algorithmus im Frontend paart die Punkte zweier Umrisse
    miteinander. Gleichmaessig verteilte Punkte sind dafuer deutlich guenstiger
    als die Originalstuetzpunkte, die sich an detailreichen Stellen haeufen und
    auf langen Geraden ausduennen. Kurze Ringe bleiben unveraendert.
    """
    if len(coords) <= 3:
        return list(coords)

    ring = list(coords)
    if ring[0] != ring[-1]:
        ring.append(ring[0])

    # Laengenkorrektur, damit Ost-West-Abstaende nicht ueberbewertet werden.
    scale = math.cos(math.radians(ring[0][1])) or 1.0

    def dist(a, b):
        dx = (b[0] - a[0]) * scale
        dy = b[1] - a[1]
        return math.hypot(dx, dy)

    cumulative = [0.0]
    for i in range(len(ring) - 1):
        cumulative.append(cumulative[-1] + dist(ring[i], ring[i + 1]))
    length = cumulative[-1]
    if length <= 0:
        return ring[: count + 1]
    if len(ring) - 1 <= count:
        return ring

    out = []
    step = length / count
    index = 0
    for k in range(count):
        target = k * step
        while index < len(cumulative) - 2 and cumulative[index + 1] < target:
            index += 1
        span = cumulative[index + 1] - cumulative[index]
        ratio = 0.0 if span <= 0 else (target - cumulative[index]) / span
        lon = ring[index][0] + (ring[index + 1][0] - ring[index][0]) * ratio
        lat = ring[index][1] + (ring[index + 1][1] - ring[index][1]) * ratio
        out.append((lon, lat))
    out.append(out[0])
    return out


def delivered_products(aoi):
    """Nur ausgelieferte Flaechenprodukte, chronologisch nach Aufnahmezeit.

    Angekuendigte Produkte tragen statusCode W oder I und haben noch keine
    Layer. Sie zu uebernehmen wuerde Luecken in die Animation reissen.
    """
    out = []
    for product in aoi.get("products", []):
        if not product.get("feasible"):
            continue
        if (product.get("version") or {}).get("statusCode") != "F":
            continue
        if product.get("type") not in ("DEL", "FEP", "GRA"):
            continue
        urls = [
            layer["json"]
            for layer in (product.get("layers") or [])
            if layer.get("json") and "observedEventA" in layer["json"]
        ]
        if not urls:
            continue
        images = product.get("images") or [{}]
        acquired = images[0].get("acquisitionTime")
        if not acquired:
            continue
        out.append({"acquired": acquired, "url": urls[0], "product": product})
    out.sort(key=lambda item: item["acquired"])
    return out


def outline(geojson):
    """Verschmilzt alle Teilflaechen zu einem Umriss und vereinfacht ihn.

    Zurueck kommt der aeussere Ring der groessten zusammenhaengenden Flaeche
    sowie die Gesamtflaeche aller Teilflaechen. Das entspricht dem Verhalten der
    Originalanwendung, die ebenfalls die groesste Teilflaeche animierte, waehrend
    die Flaechenangabe das gesamte Brandgebiet auswies.
    """
    from shapely import union_all
    from shapely.geometry import shape
    from shapely.ops import unary_union

    geoms = []
    for feature in geojson.get("features", []):
        if not feature.get("geometry"):
            continue
        geom = shape(feature["geometry"])
        if geom.is_empty:
            continue
        if not geom.is_valid:
            geom = geom.buffer(0)
        if geom.geom_type not in ("Polygon", "MultiPolygon") or geom.is_empty:
            continue
        geoms.append(geom)

    if not geoms:
        return None

    # Das Verschmelzen tausender Kleinstflaechen ist der teuerste Schritt des
    # ganzen Laufs. Ein Rasterfang von etwa einem Meter beschleunigt ihn
    # erheblich und liegt weit unter der Vereinfachungstoleranz von rund 30 m,
    # die ohnehin darauf folgt - das Ergebnis aendert sich dadurch nicht
    # sichtbar. Faellt der Rasterfang aus, wird ohne ihn verschmolzen.
    try:
        merged = union_all(geoms, grid_size=UNION_GRID_SIZE)
        if merged.is_empty:
            merged = unary_union(geoms)
    except Exception:  # noqa: BLE001 - Rasterfang ist eine Optimierung, kein Muss
        merged = unary_union(geoms)

    total_ha = polygon_area_ha(merged)

    parts = list(merged.geoms) if merged.geom_type == "MultiPolygon" else [merged]
    parts = [p for p in parts if polygon_area_ha(p) >= MIN_FRAGMENT_HA] or parts
    parts.sort(key=polygon_area_ha, reverse=True)
    largest = parts[0]

    # Erst leichtes Gläten gegen das Pixelrauschen der Kartierung, dann die
    # Stuetzpunktzahl durch gleichmaessige Neuabtastung entlang des Umrisses
    # setzen. Die Toleranz weiter hochzudrehen, bis die Punktzahl passt, waere
    # der falsche Hebel: Bei diesen zerlappten Brandflaechen bleibt die
    # Punktzahl lange hoch, waehrend die Form bereits zerstoert ist.
    smoothed = largest.simplify(SIMPLIFY_TOLERANCE, preserve_topology=True)
    if smoothed.is_empty:
        smoothed = largest
    if smoothed.geom_type == "MultiPolygon":
        smoothed = max(smoothed.geoms, key=polygon_area_ha)

    exterior = list(smoothed.exterior.coords)
    ring_lonlat = resample_ring(exterior, MAX_VERTICES)

    # Leaflet erwartet die Reihenfolge Breite, Laenge - GeoJSON liefert sie umgekehrt.
    ring = [[round(lat, 5), round(lon, 5)] for lon, lat in ring_lonlat]

    # Die uebrigen Teilflaechen werden nicht ueberblendet, aber mitgezeichnet,
    # damit Flaechenangabe und Bild zusammenpassen. Bei stark zerstreuten
    # Braenden tragen gerade sie den Zuwachs.
    others = []
    dropped_ha = 0.0
    dropped_count = 0
    for index, part in enumerate(parts[1:]):
        if index >= MAX_OTHER_PARTS:
            dropped_ha += polygon_area_ha(part)
            dropped_count += 1
            continue
        simple = part.simplify(SIMPLIFY_TOLERANCE, preserve_topology=True)
        if simple.is_empty:
            simple = part
        if simple.geom_type == "MultiPolygon":
            simple = max(simple.geoms, key=polygon_area_ha)
        coords = resample_ring(list(simple.exterior.coords), OTHER_VERTICES)
        others.append([[round(lat, 5), round(lon, 5)] for lon, lat in coords])

    largest_ha = polygon_area_ha(largest)
    centroid = largest.centroid
    return {
        "ring": ring,
        "others": others,
        "total_ha": total_ha,
        "largest_ha": largest_ha,
        "largest_share": (largest_ha / total_ha) if total_ha else 1.0,
        "parts": len(parts),
        "fragments": len(geoms),
        "dropped_parts": dropped_count,
        "dropped_ha": dropped_ha,
        "center": [round(centroid.y, 5), round(centroid.x, 5)],
        "raw_vertices": len(exterior),
    }


def build_fire(config):
    code = config["activation"]
    print(f"[{code}/AOI{config['aoi']:02d}] {config['name_de']}", flush=True)

    payload = fetch_json(f"{API}?code={code}")
    results = payload.get("results") or []
    if not results:
        print("   keine Aktivierung gefunden", file=sys.stderr)
        return None
    activation = results[0]

    aois = [a for a in activation.get("aois", []) if a.get("number") == config["aoi"]]
    if not aois:
        print(f"   AOI {config['aoi']} nicht vorhanden", file=sys.stderr)
        return None
    aoi = aois[0]

    products = delivered_products(aoi)
    if not products:
        print("   keine ausgelieferten Flaechenprodukte", file=sys.stderr)
        return None

    steps = []
    for item in products:
        try:
            geojson = fetch_json(item["url"])
        except Exception as err:  # noqa: BLE001 - ein Ausfall darf die Serie nicht abbrechen
            print(f"   {item['acquired']}: Download endgueltig fehlgeschlagen ({err})", file=sys.stderr)
            continue

        result = outline(geojson)
        if not result:
            print(f"   {item['acquired']}: keine verwertbare Geometrie", file=sys.stderr)
            continue

        product = item["product"]
        # Der Produkttyp gehoert in die Beschriftung: die Monitoring-Nummern
        # werden je Typ gezaehlt, nicht fortlaufend. Bei Fontainebleau tragen
        # deshalb zwei verschiedene Staende beide die Nummer 1 — ohne den Typ
        # waeren sie in der Anzeige nicht unterscheidbar.
        typ = product.get("type", "DEL")
        label = f"{typ} MONIT{product['monitoringNumber']}" if product.get("monitoring") else typ
        steps.append(
            {
                "acquired": item["acquired"],
                "label": label,
                "size_km2": round(result["total_ha"] / 100.0, 2),
                "size_ha": round(result["total_ha"], 1),
                "largest_ha": round(result["largest_ha"], 1),
                "largest_share": round(result["largest_share"], 3),
                "polygon": result["ring"],
                "others": result["others"],
                "center": result["center"],
            }
        )
        print(
            f"   {item['acquired'][:16]}  {label:8s} "
            f"{result['total_ha']:>9,.0f} ha  "
            f"groesste={result['largest_ha']:>9,.0f} ha ({result['largest_share'] * 100:>4.0f}%)  "
            f"Teile={result['parts']:>5d}  "
            f"Stützpunkte={len(result['ring']):>4d} (roh {result['raw_vertices']})",
            flush=True,
        )
        if result["dropped_parts"]:
            print(
                f"      nicht gezeichnet: {result['dropped_parts']} Kleinstflaechen "
                f"mit zusammen {result['dropped_ha']:,.0f} ha "
                f"({result['dropped_ha'] / result['total_ha'] * 100:.1f}% der Gesamtflaeche)",
                file=sys.stderr,
            )

    if len(steps) < 2:
        print(f"   nur {len(steps)} Zeitschnitt(e) - reicht nicht fuer eine Animation", file=sys.stderr)

    if not steps:
        return None

    # Kartenmittelpunkt aus dem letzten, groessten Stand.
    center = steps[-1]["center"]

    # Darstellungsmodus aus der Datenlage ableiten, nicht vorgeben. Dominiert
    # eine zusammenhaengende Flaeche, traegt das Ueberblenden der Umrisse die
    # Aussage. Zerfaellt der Brand in viele Flecken, wird stattdessen zwischen
    # den vollstaendigen Zustaenden gewechselt - sonst stuende der ueberblendete
    # Umriss fast still, waehrend die Flaechenangabe sich vervielfacht.
    shares = [step["largest_share"] for step in steps]
    min_share = min(shares)
    mode = pick_mode(shares)
    print(
        f"   Modus: {mode} (kleinster Anteil der groessten Teilflaeche: {min_share * 100:.0f}%)",
        flush=True,
    )

    return {
        "slug": config["slug"],
        "activation": code,
        "aoi": config["aoi"],
        "mode": mode,
        "name": {"de": config["name_de"], "en": config["name_en"]},
        "region": {"de": config["region_de"], "en": config["region_en"]},
        "timezone_label": config["timezone_label"],
        "event_time": activation.get("eventTime"),
        "closed": activation.get("closed"),
        "source_url": f"https://mapping.emergency.copernicus.eu/activations/{code}/",
        "center": center,
        "steps": steps,
    }


def discover(look_back=14, miss_limit=8):
    """Sucht neue Waldbrand-Aktivierungen, die noch nicht konfiguriert sind.

    Die API hat keine Listen-Schnittstelle: der Parameter code ist Pflicht, ein
    Aufruf ohne ihn liefert nur ein Fehlerobjekt. Deshalb wird der Nummernraum
    abgetastet - ab look_back Nummern unterhalb der hoechsten bereits
    konfigurierten Aktivierung aufwaerts, bis miss_limit Nummern in Folge
    nichts liefern.

    Gemeldet wird nur, was auch darstellbar ist: Kategorie Wildfire und
    mindestens zwei ausgelieferte Flaechenprodukte in derselben Area of
    Interest. Mit nur einem Zeitschnitt gibt es keine Entwicklung zu zeigen.
    """
    known_codes = {c["activation"] for c in FIRES}
    known_pairs = {(c["activation"], c["aoi"]) for c in FIRES}
    highest = max(int(c["activation"].removeprefix("EMSR")) for c in FIRES)

    start = highest - look_back
    print(f"Suche ab EMSR{start}, Abbruch nach {miss_limit} Fehlschlägen in Folge.\n")

    candidates = []
    number = start
    misses = 0
    blocked_at = None

    while misses < miss_limit:
        code = f"EMSR{number}"
        number += 1
        try:
            payload = fetch_json(f"{API}?code={code}")
        except Blocked as err:
            # Abweisung ist keine Aussage darueber, ob es die Aktivierung gibt.
            # Als Fehlschlag gezaehlt wuerde sie die Suche zu frueh beenden und
            # das Ergebnis als "nichts Neues" ausgeben. Deshalb: abbrechen und
            # sagen, wie weit gekommen wurde.
            print(
                f"\nSuche bei {code} abgebrochen: {err}\n"
                f"Bis {code} geprueft, darueber liegende Aktivierungen sind UNGEPRUEFT.\n"
                "Spaeter erneut laufen lassen — der Dienst begrenzt die Abfragerate.",
                file=sys.stderr,
            )
            blocked_at = code
            break
        except Exception as err:  # noqa: BLE001 - eine Luecke darf die Suche nicht beenden
            print(f"{code}: nicht abrufbar ({err})", file=sys.stderr)
            misses += 1
            continue

        results = payload.get("results") or []
        if not results:
            misses += 1
            continue

        misses = 0
        activation = results[0]
        if activation.get("category") != "Wildfire":
            continue

        countries = ", ".join(c.get("name", "?") for c in activation.get("countries", []))
        marker = " [konfiguriert]" if code in known_codes else ""
        print(f"{code} {activation.get('name')} ({countries}){marker}")

        for aoi in activation.get("aois", []):
            ready = delivered_products(aoi)
            flag = ""
            if len(ready) >= 2 and (code, aoi.get("number")) not in known_pairs:
                flag = "  <-- darstellbar, noch nicht aufgenommen"
                candidates.append(
                    {
                        "code": code,
                        "aoi": aoi.get("number"),
                        "aoi_name": aoi.get("name"),
                        "name": activation.get("name"),
                        "countries": countries,
                        "steps": len(ready),
                        "closed": bool(activation.get("closed")),
                    }
                )
            print(f"    AOI{aoi.get('number'):02d} {str(aoi.get('name'))[:26]:28s} Zeitschnitte={len(ready)}{flag}")

    print()
    if blocked_at:
        print(
            f"ACHTUNG: Suche wurde bei {blocked_at} abgewiesen — das Ergebnis ist "
            "unvollstaendig. Was oberhalb liegt, wurde nicht geprueft."
        )
    if not candidates:
        if blocked_at:
            # Kein grünes Signal ohne sichtbaren Geltungsbereich: eine abgewiesene
            # Suche darf nicht wie eine erfolglose aussehen.
            print("Bis zum Abbruch keine neuen darstellbaren Waldbrände gefunden.")
            return 2
        print("Keine neuen darstellbaren Waldbrände gefunden.")
        return 1

    print(f"{len(candidates)} Kandidat(en) für die Liste FIRES in bin/fetch_ems.py:\n")
    for c in candidates:
        slug = str(c["aoi_name"] or c["code"]).lower().replace(" ", "-")
        print(
            "    {\n"
            f'        "slug": "{slug}",\n'
            f'        "activation": "{c["code"]}",\n'
            f'        "aoi": {c["aoi"]},\n'
            f'        "name_de": "{c["aoi_name"]}, LAND",\n'
            f'        "name_en": "{c["aoi_name"]}, COUNTRY",\n'
            f'        "region_de": "{c["name"]} — Region ergänzen",\n'
            f'        "region_en": "{c["name"]} — add region",\n'
            '        "timezone_label": "CEST",\n'
            "    },"
        )
        print(
            f"    # {c['countries']}, {c['steps']} Zeitschnitte, {'abgeschlossen' if c['closed'] else 'noch offen'}\n"
        )
    return 0


def pick_mode(shares):
    """Waehlt den Darstellungsmodus aus den Flaechenanteilen aller Zeitschnitte.

    Dominiert in jedem Stand eine zusammenhaengende Flaeche, traegt das
    Ueberblenden der Umrisse die Aussage. Faellt der Anteil in einem Stand
    darunter, verteilt sich der Brand auf viele getrennte Flecken - dann wuerde
    ein Ueberblenden nur der Hauptflaeche Stillstand suggerieren, waehrend die
    Gesamtflaeche steigt.

    Ausschlaggebend ist der kleinste Anteil der Reihe, nicht der Durchschnitt:
    ein einziger zerstreuter Stand macht die Morphing-Darstellung irrefuehrend.
    """
    if not shares:
        return "crossfade"
    return "morph" if min(shares) >= MORPH_SHARE_THRESHOLD else "crossfade"


def load_existing():
    """Liest die letzte Ausgabe als dict slug -> Brand.

    Dient zwei Zwecken: dem Erkennen neuer Aufnahmen ohne Download von
    Geometrien, und dem Erhalten der uebrigen Braende, wenn nur eine Auswahl
    neu geholt wird. Ist die Datei nicht vorhanden oder unlesbar, gilt der
    Bestand als leer - ein voller Lauf stellt ihn dann wieder her.
    """
    if not OUT_FILE.exists():
        return {}
    text = OUT_FILE.read_text(encoding="utf-8")
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end <= start:
        return {}
    try:
        return {fire["slug"]: fire for fire in json.loads(text[start : end + 1])}
    except (json.JSONDecodeError, KeyError, TypeError):
        print(f"{OUT_FILE.name} nicht lesbar - Bestand gilt als leer.", file=sys.stderr)
        return {}


def report_status(configs):
    """Prueft je Aktivierung, ob sie noch offen ist und ob neue Staende vorliegen.

    Gedacht fuer den taeglichen automatischen Lauf: die eigentlichen Geometrien
    wiegen bis zu 59 MB je Produkt, ein voller Lauf dauert Minuten. Diese
    Abfrage kostet nur wenige Sekunden und beantwortet die Frage, ob sich ein
    voller Lauf ueberhaupt lohnt.

    Rueckgabe 0, wenn ein voller Lauf sinnvoll ist, sonst 1.
    """
    # Bereits verarbeitete Aufnahmezeitpunkte aus der letzten Ausgabe lesen, um
    # neue Staende zu erkennen, ohne Geometrien zu laden.
    known = {(slug, step["acquired"]) for slug, fire in load_existing().items() for step in fire.get("steps", [])}

    any_open = False
    fresh_total = 0

    for config in configs:
        code = config["activation"]
        try:
            payload = fetch_json(f"{API}?code={code}")
        except Exception as err:  # noqa: BLE001
            print(f"{code}: API nicht erreichbar ({err})", file=sys.stderr)
            # Unbekannter Zustand gilt als Grund, den vollen Lauf zu versuchen.
            fresh_total += 1
            any_open = True
            continue

        results = payload.get("results") or []
        if not results:
            print(f"{code}: keine Aktivierung gefunden", file=sys.stderr)
            continue
        activation = results[0]
        closed = bool(activation.get("closed"))
        any_open = any_open or not closed

        aois = [a for a in activation.get("aois", []) if a.get("number") == config["aoi"]]
        products = delivered_products(aois[0]) if aois else []
        fresh = [p for p in products if (config["slug"], p["acquired"]) not in known]
        fresh_total += len(fresh)

        print(
            f"{code}/AOI{config['aoi']:02d} {config['slug']:15s} "
            f"{'abgeschlossen' if closed else 'offen        '} "
            f"ausgeliefert={len(products):2d} neu={len(fresh):2d}"
            + (f"  -> {', '.join(p['acquired'][:16] for p in fresh)}" if fresh else "")
        )

    print()
    if fresh_total:
        print(f"{fresh_total} neue Aufnahme(n) - voller Lauf sinnvoll.")
        return 0
    if any_open:
        print("Keine neuen Aufnahmen, Kartierung läuft aber weiter - morgen erneut prüfen.")
        return 1
    print("Alle Aktivierungen abgeschlossen und nichts Neues - die Automatik kann ruhen.")
    return 1


def main():
    args = sys.argv[1:]
    status_only = "--status" in args
    discover_only = "--discover" in args
    wanted = [a for a in args if not a.startswith("--")]

    if discover_only:
        return discover()

    configs = [c for c in FIRES if not wanted or c["slug"] in wanted]
    if not configs:
        print(f"Unbekannter Brand. Verfuegbar: {', '.join(c['slug'] for c in FIRES)}", file=sys.stderr)
        return 1

    if status_only:
        return report_status(configs)

    fires = []
    for config in configs:
        try:
            fire = build_fire(config)
        except (urllib.error.URLError, TimeoutError) as err:
            print(f"   API nicht erreichbar: {err}", file=sys.stderr)
            continue
        if fire:
            fires.append(fire)

    if not fires:
        print("Keine Daten geholt - Ausgabe unverändert gelassen.", file=sys.stderr)
        return 1

    # Wurde nur eine Auswahl geholt, bleiben die uebrigen Braende aus der letzten
    # Ausgabe erhalten. Ohne diesen Schritt wuerde ein Lauf fuer einen einzelnen
    # Brand alle anderen aus der Datei loeschen - und ein voller Lauf laedt
    # Produkte von bis zu 59 MB erneut herunter, nur um sie unveraendert zu
    # schreiben.
    if wanted:
        fresh = {f["slug"]: f for f in fires}
        merged = load_existing()
        merged.update(fresh)
        # Reihenfolge aus FIRES uebernehmen, damit die Auswahlknoepfe stabil bleiben.
        order = [c["slug"] for c in FIRES]
        fires = [merged[s] for s in order if s in merged]
        kept = [s for s in merged if s not in fresh]
        if kept:
            print(f"\nUnverändert übernommen: {', '.join(kept)}")

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(
        "/* Erzeugt von bin/fetch_ems.py - nicht von Hand bearbeiten. */\n"
        "var _fires = " + json.dumps(fires, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )

    total_steps = sum(len(f["steps"]) for f in fires)
    size_kb = OUT_FILE.stat().st_size / 1024
    print(f"\n{OUT_FILE.relative_to(ROOT)}: {len(fires)} Brände, {total_steps} Zeitschnitte, {size_kb:.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
