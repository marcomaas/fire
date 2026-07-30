#!/usr/bin/env python3
"""Baut app/assets/data/cities.js fuer den Groessenvergleich.

Anders als in der Fassung von 2013 werden die Stadtumrisse hier in echten
Koordinaten abgelegt. Das Verschieben an den Brandort uebernimmt das Frontend zur
Laufzeit. Vorher wurde jede Stadt mit bin/move.js einmalig an einen fest im Code
stehenden Zielpunkt gerechnet - fuer eine Anwendung mit mehreren umschaltbaren
Braenden waere das je Stadt und Brand ein eigener Datensatz.

Bestehende Umrisse kommen aus data/*.geojson, fehlende werden bei OpenStreetMap
ueber Nominatim geholt.
"""

import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from shapely.geometry import shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT_FILE = ROOT / "app" / "assets" / "data" / "cities.js"

NOMINATIM = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "fire-viz/2.0 (+https://github.com/marcomaas/fire)"

SIMPLIFY_TOLERANCE = 0.0008
MAX_VERTICES_PER_RING = 400

# label: Anzeigename. query: Nominatim-Suche, falls keine lokale Datei existiert.
CITIES = [
    {"slug": "bordeaux", "label": {"de": "Bordeaux", "en": "Bordeaux"}, "query": "Bordeaux, France"},
    {"slug": "madrid", "label": {"de": "Madrid", "en": "Madrid"}, "query": "Madrid, Spain"},
    {"slug": "paris", "label": {"de": "Paris", "en": "Paris"}, "file": "paris.geojson"},
    {"slug": "berlin", "label": {"de": "Berlin", "en": "Berlin"}, "file": "berlin.geojson"},
    {"slug": "hamburg", "label": {"de": "Hamburg", "en": "Hamburg"}, "file": "hamburg.geojson"},
    {"slug": "muenchen", "label": {"de": "München", "en": "Munich"}, "file": "muenchen.geojson"},
    {"slug": "koeln", "label": {"de": "Köln", "en": "Cologne"}, "file": "koeln.geojson"},
    {"slug": "london", "label": {"de": "London", "en": "London"}, "file": "london.geojson"},
    {"slug": "manhattan", "label": {"de": "Manhattan", "en": "Manhattan"}, "file": "manhattan.geojson"},
]


def load_local(name):
    path = DATA / name
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    geoms = []
    for feature in payload.get("features", []):
        if feature.get("geometry"):
            geoms.append(shape(feature["geometry"]))
    return unary_union(geoms) if geoms else None


def load_nominatim(query):
    params = urllib.parse.urlencode({"q": query, "format": "json", "polygon_geojson": "1", "limit": "1"})
    req = urllib.request.Request(f"{NOMINATIM}?{params}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=45) as resp:
        payload = json.load(resp)
    if not payload:
        return None
    geom = payload[0].get("geojson")
    if not geom or geom.get("type") not in ("Polygon", "MultiPolygon"):
        return None
    return shape(geom)


def thin(ring):
    """Duennt einen Ring aus, falls er die Stuetzpunktgrenze reisst."""
    if len(ring) <= MAX_VERTICES_PER_RING:
        return ring
    stride = len(ring) // MAX_VERTICES_PER_RING + 1
    thinned = ring[::stride]
    if thinned[-1] != ring[-1]:
        thinned.append(ring[-1])
    return thinned


def to_rings(geom):
    """Wandelt eine Geometrie in Listen von [lat, lon]-Ringen fuer Leaflet."""
    simple = geom.simplify(SIMPLIFY_TOLERANCE, preserve_topology=True)
    if simple.is_empty:
        simple = geom
    polys = list(simple.geoms) if simple.geom_type == "MultiPolygon" else [simple]
    rings = []
    for poly in polys:
        coords = thin([[round(lat, 5), round(lon, 5)] for lon, lat in poly.exterior.coords])
        if len(coords) >= 4:
            rings.append(coords)
    return rings


def main():
    out = []
    for city in CITIES:
        geom = None
        if city.get("file"):
            geom = load_local(city["file"])
            source = f"data/{city['file']}"
        if geom is None and city.get("query"):
            print(f"  {city['slug']}: hole Umriss bei OpenStreetMap", flush=True)
            try:
                geom = load_nominatim(city["query"])
            except Exception as err:  # noqa: BLE001 - Netzfehler sollen den Lauf nicht abbrechen
                print(f"  {city['slug']}: Nominatim fehlgeschlagen ({err})", file=sys.stderr)
            source = "OpenStreetMap / Nominatim"
            time.sleep(1.2)  # Nutzungsregeln von Nominatim: maximal eine Anfrage pro Sekunde

        if geom is None or geom.is_empty:
            print(f"  {city['slug']}: kein Umriss gefunden - uebersprungen", file=sys.stderr)
            continue

        rings = to_rings(geom)
        if not rings:
            print(f"  {city['slug']}: Umriss leer nach Vereinfachung", file=sys.stderr)
            continue

        centroid = geom.centroid
        out.append(
            {
                "slug": city["slug"],
                "label": city["label"],
                "center": [round(centroid.y, 5), round(centroid.x, 5)],
                "rings": rings,
                "source": source,
            }
        )
        points = sum(len(r) for r in rings)
        print(f"  {city['slug']:11s} Ringe={len(rings):2d}  Stützpunkte={points:5d}  ({source})")

    if not out:
        print("Keine Stadt verarbeitet.", file=sys.stderr)
        return 1

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(
        "/* Erzeugt von bin/build_cities.py - nicht von Hand bearbeiten. */\n"
        "var _cities = " + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )
    print(f"\n{OUT_FILE.relative_to(ROOT)}: {len(out)} Städte, {OUT_FILE.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
