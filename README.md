# Waldbrand-Visualisierung

Interaktive Karte, die kartierte Brandflächen im zeitlichen Verlauf zeigt und sie
flächentreu mit dem Umriss europäischer Städte vergleicht.

Diese Fassung ist eine Wiederbelebung von
[opendatacity/fire](https://github.com/opendatacity/fire) (2013, *Yosemite Rim Fire*).
Die Überblend-Animation ist unverändert übernommen. Datenquelle, Kartengrundlage und
Gestaltung wurden 2026 erneuert, weil die ursprünglichen Dienste nicht mehr existieren.

## Was ersetzt wurde und warum

| Bestandteil 2013 | Zustand | Ersatz 2026 |
|---|---|---|
| Kachelserver `tilt.odcdn.de` | DNS gelöscht | Esri World Shaded Relief über HTTPS |
| GeoMAC-KML der USGS (`bin/rimfire.js`) | Dienst 2020 abgeschaltet | Copernicus EMS Rapid Mapping (`bin/fetch_ems.py`) |
| InciWeb-Scraping (`bin/incidents.js`) | HTTP 403, Seitenstruktur hinfällig | entfällt |
| Vorverschobene Stadtumrisse (`bin/move.js`) | an einen fest verdrahteten Zielpunkt gerechnet | Verschiebung zur Laufzeit im Browser, dadurch für jeden Brand nutzbar |
| Leaflet 0.6.4, Bootstrap 3, Font Awesome 3 | veraltet | Leaflet 1.9.4, eigenes Stylesheet |
| Google Analytics, Google+, App.net | eingestellt bzw. unerwünscht | entfernt |

## Aufbau

```
app/                     die eigentliche Anwendung, statisch ausliefern
  index-de.html          deutsche Fassung
  index-en.html          englische Fassung
  assets/data/fires.js   erzeugt von bin/fetch_ems.py
  assets/data/cities.js  erzeugt von bin/build_cities.py
  assets/js/polymorph.js Überblend-Algorithmus, aus der Fassung 2013
  assets/js/fire.js      Anwendungslogik
bin/fetch_ems.py         holt die Brandperimeter
bin/build_cities.py      baut die Stadtumrisse
data/*.geojson           Stadtgrenzen in echten Koordinaten (Quelldaten)
```

## Daten aktualisieren

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

.venv/bin/python bin/fetch_ems.py            # alle konfigurierten Brände
.venv/bin/python bin/fetch_ems.py gironde    # nur einen
.venv/bin/python bin/build_cities.py         # nur bei Änderungen an der Städteliste
```

Welche Brände dargestellt werden, steht in der Liste `FIRES` in `bin/fetch_ems.py`.
Ein Eintrag verweist auf eine EMS-Aktivierung und eine Area of Interest darin, weil
eine Aktivierung mehrere räumlich getrennte Brände umfassen kann.

Solange eine Aktivierung nicht abgeschlossen ist, liefert Copernicus weitere
Monitoring-Stände nach. Ein erneuter Lauf verlängert die Animation dann automatisch.

## Lokal ansehen

```bash
python3 -m http.server 8000 --directory app
# http://localhost:8000/index-de.html
```

## Woher die Daten kommen

Grundlage ist die Activations-API des
[Copernicus EMS Rapid Mapping Service](https://mapping.emergency.copernicus.eu/).
Ihr Schema liegt offen unter
`/static/cems_rapidmapping_openapi_specs.yaml`.

Pro Area of Interest gibt es eine erste Delineation und danach durchnummerierte
Monitoring-Stände. Jeder Stand nennt den Aufnahmezeitpunkt der zugrunde liegenden
Satellitenszene, und genau diese Serie ist es, welche die Animation trägt. Verwendet
wird jeweils die Ebene `observedEventA`, also die beobachtete Brandfläche.

Nur ausgelieferte Produkte werden übernommen. Angekündigte Stände tragen im Feld
`version.statusCode` ein `W` oder `I` und haben noch keine Geometrie.

Berücksichtigt werden die Produkttypen `FEP` (erste Einschätzung), `DEL` (Delineation)
und `GRA` (Schadensklassifizierung). Alle drei enthalten die beobachtete Brandfläche;
sortiert wird nach Aufnahmezeit, sodass ein späterer Stand die Reihe unabhängig von
seinem Typ verlängert.

## Verlinkbare Zustände

Der Anker hält Brand und Vergleichsstadt fest:

```
#gironde              nur der Brand
#gironde/bordeaux     Brand mit eingeblendetem Stadtumriss
```

Die Einstiegsseite im Wurzelverzeichnis leitet je nach Browsersprache auf die deutsche
oder englische Fassung und nimmt den Anker mit.

## Zwei Darstellungsmodi

Die Delineation-Produkte sind sehr feingliedrig, bis über 25.000 Teilflächen je Stand.
Die Pipeline verschmilzt sie und entscheidet dann anhand des Flächenanteils der
größten zusammenhängenden Fläche, wie animiert wird:

- **`morph`** — ab 70 Prozent Anteil. Der Umriss der Hauptfläche wird von Stand zu
  Stand übergeblendet, so wie in der Fassung von 2013.
- **`crossfade`** — darunter. Jeder Stand wird vollständig eingeblendet und bleibt
  liegen. Nötig, weil sich manche Brände in viele getrennte Flecken auflösen: Dort
  wächst die Hauptfläche kaum, während die Gesamtfläche sich vervielfacht — ein
  Überblenden nur der Hauptfläche würde Stillstand suggerieren.

## Grenzen der Darstellung

Die Bewegung zwischen zwei Aufnahmen ist linear interpoliert und damit eine
Darstellungshilfe, keine Messung. Was zwischen zwei Satellitenüberflügen geschah,
ist aus diesen Daten nicht bekannt.

Zeitangaben sind Aufnahmezeitpunkte der Satellitenszene, nicht Zeitpunkte der
Veröffentlichung. Sie kommen laut Schema in UTC und werden für die Anzeige um zwei
Stunden auf mitteleuropäische Sommerzeit verschoben — fest verdrahtet, weil hier
keine Zeitzonendatenbank eingebunden ist und alle dargestellten Brände in derselben
Zone liegen.

Der Städtevergleich verschiebt den Umriss an den Brandort und behält dabei die
tatsächliche Fläche. Weil ein Längengrad in höheren Breiten kürzer ist, wird die
Ost-West-Ausdehnung mit dem Verhältnis der Breitenkosinus korrigiert.

## Lizenz

Anwendung unter [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/), siehe `LICENSE`.

Brandperimeter: Copernicus EMS Rapid Mapping, © Europäische Union.
Stadtgrenzen: OpenStreetMap und Mitwirkende, ODbL.
Reliefkarte: Esri.
