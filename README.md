# Waldbrand-Visualisierung

Interaktive Karte, die kartierte Brandflächen im zeitlichen Verlauf zeigt und ihre
Fläche mit dem Umriss einer europäischen Stadt vergleicht.

Gezeigt wird eine **Auswahl**: jene Brände, für die Copernicus eine Kartierung mit
mindestens zwei Zeitschnitten veröffentlicht hat. Es brennt an mehr Orten, als hier
zu sehen sind. Welche Brände es sind, steht in der Liste `FIRES` in
`bin/fetch_ems.py`; die Anwendung liest die Zahl zur Laufzeit aus den Daten und
schreibt sie nirgends als Text fest.

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
  beispiel.html          Einbettungsbeispiele, deutsch
  beispiel-en.html       Einbettungsbeispiele, englisch
  konfigurieren.html     erzeugt Einbettungscode mit festgelegter Auswahl
  index.html             Weiterleitung nach Browsersprache, gibt Anker und Query weiter
  assets/data/fires.js   erzeugt von bin/fetch_ems.py
  assets/data/cities.js  erzeugt von bin/build_cities.py
  assets/data/config.js  Voreinstellung der Auswahl, von Hand pflegbar
  assets/js/polymorph.js Überblend-Algorithmus, aus der Fassung 2013
  assets/js/fire.js      Anwendungslogik
bin/fetch_ems.py         holt die Brandperimeter
bin/build_cities.py      baut die Stadtumrisse
data/*.geojson           Stadtgrenzen in echten Koordinaten (Quelldaten)
```

Unter `data/` liegen mehr Stadtgrenzen als die Anwendung zeigt: `hamburg`, `koeln`,
`muenchen` und `manhattan` sind aus der Vergleichsliste genommen worden, `sacramento`
stammt aus der Yosemite-Fassung von 2013. Die Dateien bleiben liegen, damit eine
Stadt ohne neuen Abruf bei OpenStreetMap zurückkommen kann — welche Städte
erscheinen, entscheidet allein die Liste in `bin/build_cities.py`.

`polymorph.js` ist absichtlich unangetastet, damit ein Vergleich mit der Fassung von
2013 möglich bleibt — die LICENSE-Datei sagt das auch so. Darin steckt eine Funktion
`linterpol`, die dort schon niemand aufrief; sie bleibt aus demselben Grund stehen.
Wer im Code danach sucht, findet also nichts, und das ist kein Versehen.

## Daten aktualisieren

```bash
python3 -m venv .venv
.venv/bin/pip install -r bin/requirements.txt

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
# http://localhost:8000/index-de.html      die Anwendung
# http://localhost:8000/beispiel.html      Einbettungsbeispiele
# http://localhost:8000/beispiel-en.html   dieselben, englisch
```

## Tests

```bash
python3 tests/test_geometry.py        # Rechenlogik der Pipeline
python3 tests/run_layout_tests.py     # Layout in echten Rahmen, braucht Chrome
```

Beide laufen auch in der CI (`.github/workflows/tests.yml`), bei jedem Push und bei jedem
automatischen Datenabgleich.

**`test_geometry.py`** prüft, was still falsch werden kann: Flächenberechnung auf der Kugel,
Neuabtastung der Umrisse, Wahl des Darstellungsmodus, Filtern der Produkte, Zusammenführen
von Teil-Läufen und die Wohlgeformtheit der Liste `FIRES`. Standardbibliothek, kein pytest
nötig.

**`run_layout_tests.py`** bindet die Anwendung in `iframe`s von fünf Größen ein und prüft in
beiden Sprachfassungen: keine Überlagerung sichtbarer Kästen, nichts außerhalb des
Sichtbereichs, kein waagerechtes Überlaufen, Herkunftsangabe sichtbar und einzeilig, Quellen
und Lizenz auch im eingebetteten Zustand erreichbar, kein Text auf gleichfarbigem Grund.

Diese Tests entstanden aus vier tatsächlich aufgetretenen Fehlern und fanden beim ersten Lauf
sofort sechzehn weitere. Beim Erweitern gilt: jede neue Prüfung einmal gegen eine eingebaute
Mutation laufen lassen — ein Test, der nicht rot werden kann, ist wertlos.

```bash
python3 tests/mutate_layout.py        # beißen die Layout-Prüfungen?
python3 tests/mutate_routing.py       # beißen die Routing-Prüfungen?
```

Beide bauen jeden Fehler, den die zugehörige Testseite fangen soll, einmal absichtlich in eine
Kopie des Baums ein und verlangen, dass genau die zugehörige Prüfung rot wird. Eine Mutation,
die niemand fängt, ist eine Prüfung, die nichts prüft; eine Mutation, deren Textstelle im Code
nicht mehr zu finden ist, gilt ebenfalls als Fehlschlag — sonst würde der Lauf nach jeder
Umbenennung still grün. Der Harnisch steckt in `mutate_routing.py`, `mutate_layout.py` setzt
nur Testseite und Zeitbudget um.

Dieser Lauf ist keine Formsache. Von zehn Layout-Mutationen blieben beim ersten Durchgang drei
ungefangen: zwei davon waren wirkungslos formuliert (ein Rasterelement landet auch ohne Regel
in der zweiten Reihe; `pointer-events: none` hält keinen Klick über die Ereignisschnittstelle
auf), die dritte deckte eine Prüfung auf, die nicht rot werden konnte.

**Warum im `iframe` und nicht im Fenster:** Headless Chrome erzwingt eine Mindestfensterbreite
von 500 Pixel. Ein Lauf mit `--window-size=400` rendert bei 500 und beschneidet nur das Bild —
schmale Layouts lassen sich so nicht prüfen, und der Beschnitt sieht wie ein Layout-Fehler aus.

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

## Veröffentlichung

Live unter **https://apps.datenfreunde.com** (Vercel, mit dem Repository verbunden — ein Push
veröffentlicht neu). Zusätzlich erreichbar über `waldbraende.vercel.app` und
`waldbraende-datenfreunde.vercel.app`.

`vercel.json` liefert `app/` als Wurzel aus, damit die relativen Pfade in den HTML-Dateien
unverändert bleiben. Die Wurzel `/` zeigt dabei **unmittelbar** auf `app/index-de.html` und
nicht auf eine Weiterleitungsseite: Vorschau-Crawler von LinkedIn, Bluesky oder Mastodon
führen kein JavaScript aus und sahen auf der Weiterleitungsseite nur einen Titel — die
Vorschaukarte blieb leer.

**Wichtig dabei:** Im Wurzelverzeichnis darf keine `index.html` liegen. Vercel prüft zuerst
das Dateisystem und erst danach die Umschreibungen — eine Datei dort gewinnt gegen die Regel
für `/` und macht sie wirkungslos. Genau daran hing der Fehler. `app/index.html` bleibt
erhalten, es greift nur bei direkten Verzeichnisaufrufen, etwa bei einem lokalen Server.

`fires.js` bekommt `must-revalidate`, sonst verschwindet der zweimal täglich aktualisierte
Datenstand hinter dem Cache.

**Zu Einbettungen bei LinkedIn:** LinkedIn nimmt keinen `iframe`-Code an und bettet nur von
einer eigenen Anbieterliste ein. Dort gehört die reine Adresse ins Feld — der Beitrag zeigt
dann eine Vorschaukarte, die auf die interaktive Seite führt. Deshalb müssen `og:title`,
`og:description`, `og:image` und `og:url` auf **jeder** einzeln teilbaren Seite stehen.

## Verlinkbare Zustände

Der Anker hält Brand und Vergleichsstadt fest:

```
#gironde              Brand mit seiner voreingestellten Vergleichsstadt
#gironde/madrid       Brand mit einer bestimmten Stadt
#gironde/none         Brand ohne Größenvergleich
```

Die Voreinstellung steht je Brand im Feld `compare` in `fires.js` und ist die
nächstgelegene der fünf Städte; `bin/fetch_ems.py` setzt sie beim Bauen der Daten,
`--compare` holt sie ohne Netzzugriff nach. Ohne Voreinstellung wäre der
Größenvergleich — der Grund für diese Anwendung — in jeder Einbettung unsichtbar, die
keinen Anker mit Stadt trägt. Genau deshalb braucht der abgeschaltete Vergleich ein
eigenes Kürzel: ohne `none` hieße `#gironde` sowohl „keine Angabe" als auch „keine
Stadt".

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
Veröffentlichung. Sie kommen laut Schema in UTC und werden in die Ortszeit des Brandes
gerechnet — je Aufnahme, aus der IANA-Zone im Feld `timezone` (`offsetHours` in
`app/assets/js/fire.js`). Der feste Versatz von zwei Stunden, den diese Stelle bis
Commit `c843547` beschrieb, wäre für eine Aufnahme aus dem Winterhalbjahr eine Stunde
falsch gewesen.

Der Städtevergleich verschiebt den Umriss an den Brandort und behält dabei die
tatsächliche Fläche — nicht die Form. Weil ein Längengrad in höheren Breiten kürzer
ist, wird die Ost-West-Ausdehnung mit dem Verhältnis der Breitenkosinus korrigiert
(`shiftRings` in `app/assets/js/fire.js`). Über weite Strecken ist diese Korrektur
deutlich sichtbar: Berlin (52,50° N) auf Artana (39,87° N) wird um 20,7 Prozent
gestaucht — das ist der größte Wert, den die fünf angebotenen Städte über die fünf
Brände erreichen. Der Umriss taugt als Flächenmaßstab, nicht als Stadtgrundriss.

Welche Stadt zu einem Brand voreingestellt ist, entscheidet die Pipeline: die
nächstgelegene, solange ihre Fläche in derselben Größenordnung liegt, sonst die
flächennächste. Die Grenze (`MAX_COMPARE_RATIO`) gibt es, weil Nähe allein zu
Unsinn führen kann — Fontainebleau (9,24 km²) war mit Paris voreingestellt, und
der Paris-Umriss stammte aus der Fassung von 2013 und war die **Agglomeration**
mit 3.112 km². Der Brand war damit ein Punkt in einer Fläche. Paris kommt jetzt
wie Bordeaux und Madrid aus OpenStreetMap und ist das Stadtgebiet (105 km²);
Berlin und London bleiben Dateien und waren immer Stadt- bzw. Verwaltungsgebiet.

Die kartierte Fläche kann von einem Stand zum nächsten **sinken**. Verbrannte Fläche
verschwindet nicht wieder, die kartierte aber schon: Ein späterer Stand grenzt genauer
ab und nimmt vorher mitgezählte unverbrannte Inseln heraus. Die Zahl fällt dann,
während das rote Gebiet im Bild unverändert bleibt. Die Animation ist deshalb keine
Zusage, dass die Fläche nur wächst.

## Lizenz

Der Programmcode steht unter der [MIT-Lizenz](LICENSE) — Copyright 2013 OpenDataCity
für die ursprüngliche Fassung, 2026 Datenfreunde GmbH für diese. `LICENSE` ist die
maßgebliche Angabe; nutzersichtbare Stellen nannten bis Juli 2026 fälschlich CC BY 3.0
und widersprachen damit genau der Datei, auf die sie verwiesen.

Die **Daten** folgen nicht der Lizenz des Codes:

Brandperimeter: Copernicus EMS Rapid Mapping, © Europäische Union.
Stadtgrenzen: OpenStreetMap-Mitwirkende, ODbL.
Reliefkarte: Esri.
