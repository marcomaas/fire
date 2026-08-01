/*
 * Waldbrand-Visualisierung.
 *
 * Fassung 2026: Datenquelle ist der Copernicus Emergency Management Service.
 * Die Originalfassung von 2013 zeigte das Rim Fire im Yosemite-Nationalpark und
 * bezog seine Umrisse vom GeoMAC-Dienst der USGS, der 2020 abgeschaltet wurde.
 *
 * Erwartete Daten:
 *   _fires   aus assets/data/fires.js   (bin/fetch_ems.py)
 *   _cities  aus assets/data/cities.js  (bin/build_cities.py)
 */

$(document).ready(function () {
  var lang = $("html").hasClass("site-de") ? "de" : "en";

  /* Die Aufnahmezeitpunkte kommen laut API-Schema in UTC und werden in der
   * Ortszeit des Brandes gezeigt. Die Zone steht je Brand in den Daten (Feld
   * `timezone`, eine IANA-Angabe wie Europe/Madrid).
   *
   * Gerechnet und formatiert wird durchgaengig mit Intl. Vorher lief die
   * Formatierung ueber moment und der Zeitversatz ueber einen Umweg: dasselbe
   * Datum zweimal als en-US-Text erzeugen, zurueckparsen und die Differenz
   * bilden. Das funktionierte, war aber eine Rueckparse-Kruecke neben einer
   * Schnittstelle, die es direkt kann — und moment lag nur noch fuer die
   * Formatierung im Baum.
   *
   * Zwei Dinge, die frueher still falsch waren und jetzt nicht mehr:
   *   - Bei unbekannter Zone stand ein fester Versatz von zwei Stunden. Jetzt
   *     wird UTC angezeigt UND als UTC beschriftet — falsch beschriftet ist
   *     schlimmer als sichtbar unbekannt.
   *   - Das Kuerzel kannte nur MEZ/MESZ. Jetzt kommt es aus Intl und stimmt
   *     auch fuer den ersten Brand ausserhalb Mitteleuropas. */
  var FALLBACK_TZ = "UTC";

  function zoneOf(f) {
    return (f && f.timezone) || FALLBACK_TZ;
  }

  /* Ein Formatierer je (Zone, Art). Intl.DateTimeFormat ist teuer im Aufbau und
   * wird hier pro Bild der Animation aufgerufen. */
  var _formatCache = {};

  function formatter(zone, options) {
    var key = zone + "|" + JSON.stringify(options);
    if (!_formatCache[key]) {
      var locale = lang === "de" ? "de-DE" : "en-GB";
      try {
        _formatCache[key] = new Intl.DateTimeFormat(
          locale,
          $.extend({ timeZone: zone }, options),
        );
      } catch (e) {
        /* Unbekannte Zone: Intl wirft. Auf UTC zurueckfallen — und der Aufrufer
         * beschriftet es auch so, siehe zoneLabel(). */
        _formatCache[key] = new Intl.DateTimeFormat(
          locale,
          $.extend({ timeZone: "UTC" }, options),
        );
      }
    }
    return _formatCache[key];
  }

  function zoneKnown(zone) {
    try {
      new Intl.DateTimeFormat("en-GB", { timeZone: zone });
      return true;
    } catch (e) {
      return false;
    }
  }

  /* Das Kuerzel der Zone zum jeweiligen Zeitpunkt — im Sommer ein anderes als im
   * Winter. Intl liefert es je nach Sprache als "MESZ" oder "CEST"; wo es nur
   * einen Versatz kennt ("GMT+2"), bleibt dieser stehen. Beides ist richtig,
   * beides ist nachpruefbar — anders als eine fest eingetragene Abkuerzung. */
  function zoneLabel(millis, zone) {
    if (!zoneKnown(zone)) return "UTC";
    var teile = formatter(zone, { timeZoneName: "short" }).formatToParts(
      new Date(millis),
    );
    for (var i = 0; i < teile.length; i++) {
      if (teile[i].type === "timeZoneName") return teile[i].value;
    }
    return "";
  }

  /* ---------- Auswahl der gezeigten Braende ---------- */

  /* Eine Redaktion soll je Einbettung festlegen koennen, welche Braende zu sehen
   * sind — ohne eine eigene Fassung der Anwendung zu brauchen. Die Auswahl steht
   * deshalb in der Adresse (?nur=gironde,artana) und ist damit Teil des
   * iframe-Codes, den die Konfigurationsseite ausgibt.
   *
   * Rangfolge: Adresse vor assets/data/config.js vor "alle". Unbekannte Kuerzel
   * werden uebergangen statt als Fehler behandelt, und eine Auswahl, von der
   * nichts uebrig bleibt, faellt auf alle zurueck. Eine Einbettung, die auf einen
   * spaeter entfernten Brand zeigt, zeigt dann wieder alles — das ist besser als
   * eine leere Karte in einem fremden Artikel. */
  function readSelection() {
    var roh = null;

    var m = /[?&]nur=([^&]*)/.exec(window.location.search);
    if (m) roh = decodeURIComponent(m[1].replace(/\+/g, " "));
    else if (
      typeof _config !== "undefined" &&
      _config &&
      _config.nur &&
      _config.nur.length
    )
      roh = _config.nur.join(",");

    if (!roh) return null;

    var gewuenscht = roh
      .split(",")
      .map(function (t) {
        return t.trim().toLowerCase();
      })
      .filter(Boolean);
    if (!gewuenscht.length) return null;

    /* Reihenfolge aus den Daten, nicht aus der Adresse: die Daten sind nach
     * Aktivierung sortiert, und eine vertippte Reihenfolge soll die Anwendung
     * nicht umsortieren. */
    var gefiltert = _fires.filter(function (f) {
      return gewuenscht.indexOf(f.slug) !== -1;
    });
    return gefiltert.length ? gefiltert : null;
  }

  var selection = null;

  /* Die eine Stelle, die beantwortet, welche Braende gezeigt werden. Alles
   * andere — Liste, Auswahlfeld, Zahl im Info-Kasten, Rueckfall bei unbekanntem
   * Anker — fragt hier und nirgends sonst. */
  function visibleFires() {
    return selection || _fires;
  }

  /* Impressum der Datenfreunde. Steht in der Herkunftszeile der Karte, weil eine
   * randlose Kartenanwendung keine eigene Fußzeile hat — und weil das die
   * einzige Stelle ist, die auch im eingebetteten Zustand sichtbar bleibt. */
  var IMPRINT_URL = "https://www.datenfreunde.com/impressum";

  /* Die vollstaendige Anwendung. Im Rahmen zeigt ein Verweis dorthin, damit ein
   * Leser die Auswahl selbst steuern kann. */
  var FULL_APP_URL = "https://apps.datenfreunde.com/";

  /* Abspieldauer je Abschnitt richtet sich nach dem tatsächlichen Zeitabstand
   * zweier Aufnahmen — vorher war jeder Abschnitt gleich lang, ob 22 oder 49
   * Stunden dazwischen lagen. Gedeckelt nach oben und unten, damit ein sehr
   * kurzer Abstand nicht übersprungen wird und ein sehr langer nicht ermüdet. */
  var MS_PER_HOUR = 58;
  var STEP_MIN_MS = 900;
  var STEP_MAX_MS = 3800;
  var MS_PER_FRAME = 55;

  /* Zahlformatierung: im Deutschen Komma als Dezimaltrennzeichen und Punkt
   * als Tausendertrennzeichen, im Englischen umgekehrt. */
  function num(value, decimals) {
    var parts = value.toFixed(decimals).split(".");
    var thousands = lang === "de" ? "." : ",";
    var decimal = lang === "de" ? "," : ".";
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, thousands);
    return parts.length > 1 ? parts[0] + decimal + parts[1] : parts[0];
  }

  var text = {
    de: {
      /* Intl-Angaben statt moment-Muster: dieselbe Ausgabe (01.08.2026 14:05),
       * nur ohne die Bibliothek. */
      dateParts: {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      },
      size: function (ha) {
        return num(ha / 100, 2) + " km² (" + num(ha, 0) + " ha)";
      },
      compare: "Größenvergleich",
      fires: "Brand wählen",
      ongoing:
        "Kartierung läuft weiter — der Brand ist noch nicht abgeschlossen.",
      contained: "Die Kartierung dieses Brandes ist abgeschlossen.",
      steps: function (n) {
        return n === 1 ? "1 Satellitenaufnahme" : n + " Satellitenaufnahmen";
      },
      single:
        "Für diesen Brand liegt bislang nur eine Aufnahme vor, die Entwicklung lässt sich noch nicht zeigen.",
      play: "Verlauf",
      pause: "Pause",
      again: "Nochmal",
      sources: "Quellen",
      imprint: "Impressum",
      fullApp: "alle Brände",
      outbreak: "Brandausbruch",
      acquisition: "Satellitenaufnahme",
      dayParts: { day: "2-digit", month: "2-digit" },
      /* Nennt zuerst das Ausbruchsdatum, dann den Verzug bis zur ersten
       * Aufnahme, dann den kartierten Zeitraum — "wann war der Brand" ist die
       * erste Frage, die der Zeitstrahl beantworten soll. */
      summary: function (outbreakText, delayText, mappedText) {
        return (
          "Ausbruch " +
          outbreakText +
          " · erste Aufnahme " +
          delayText +
          " später · " +
          mappedText +
          " kartiert"
        );
      },
      summaryNoDelay: function (outbreakText, mappedText) {
        return "Ausbruch " + outbreakText + " · " + mappedText + " kartiert";
      },
      days: function (n) {
        return n === 1 ? "1 Tag" : n + " Tage";
      },
      hours: function (n) {
        return n === 1 ? "1 Stunde" : n + " Stunden";
      },
      stillOpen: "Kartierung läuft weiter",
      rangeJoin: " bis ",
      noCompare: "ohne Vergleich",
      nearest: "am nächsten zum Brandort — beim Öffnen eingeblendet",
      /* Dieselbe Aussage kurz, für die Legende unter der Liste. Die lange Fassung
       * bleibt im title-Attribut; sichtbar sein muss sie trotzdem, weil ein
       * Touchscreen keinen Hover kennt. */
      nearestLegend: "zu diesem Brand vorausgewählt",
      buttonTitle: {
        play: "Verlauf abspielen",
        pause: "Abspielen anhalten",
        again: "Verlauf erneut abspielen",
      },
      details: "Angaben zum Brand",
      /* Nennt die Eintraege ausserhalb des Fensters mit ihrer Richtung. Nur eine
       * Zahl ohne Richtung liesse offen, wohin gescrollt werden muss — und in
       * einer Liste, die schon in der Mitte steht, geht es in beide. */
      hiddenBelow: function (n) {
        return n + " weitere ↓";
      },
      hiddenAbove: function (n) {
        return "↑ " + n + " weitere";
      },
      hiddenBoth: function (oben, unten) {
        return "↑ " + oben + " · " + unten + " ↓";
      },
    },
    en: {
      dateParts: {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      },
      size: function (ha) {
        return num(ha * 0.00386102, 2) + " sq mi (" + num(ha, 0) + " ha)";
      },
      compare: "Size comparison",
      fires: "Select fire",
      ongoing: "Mapping is ongoing — this fire is not yet closed.",
      contained: "Mapping for this fire is complete.",
      steps: function (n) {
        return n === 1
          ? "1 satellite acquisition"
          : n + " satellite acquisitions";
      },
      single:
        "Only one acquisition is available for this fire so far, so its growth cannot be shown yet.",
      play: "Play",
      pause: "Pause",
      again: "Replay",
      sources: "Sources",
      imprint: "Impressum",
      fullApp: "all fires",
      outbreak: "Fire outbreak",
      acquisition: "Satellite acquisition",
      dayParts: { day: "2-digit", month: "short" },
      summary: function (outbreakText, delayText, mappedText) {
        return (
          "Outbreak " +
          outbreakText +
          " · first acquisition " +
          delayText +
          " later" +
          " · " +
          mappedText +
          " mapped"
        );
      },
      summaryNoDelay: function (outbreakText, mappedText) {
        return "Outbreak " + outbreakText + " · " + mappedText + " mapped";
      },
      days: function (n) {
        return n === 1 ? "1 day" : n + " days";
      },
      hours: function (n) {
        return n === 1 ? "1 hour" : n + " hours";
      },
      stillOpen: "Mapping ongoing",
      rangeJoin: " to ",
      noCompare: "no comparison",
      nearest: "closest to the fire — shown on opening",
      nearestLegend: "preselected for this fire",
      buttonTitle: {
        play: "Play the sequence",
        pause: "Pause playback",
        again: "Play the sequence again",
      },
      details: "Fire details",
      hiddenBelow: function (n) {
        return n + " more ↓";
      },
      hiddenAbove: function (n) {
        return "↑ " + n + " more";
      },
      hiddenBoth: function (oben, unten) {
        return "↑ " + oben + " · " + unten + " ↓";
      },
    },
  }[lang];

  /* Zone als Parameter, nicht aus der globalen Variablen `fire`. Vorher las
   * formatTime sie dort — wer einen Zeitstempel von Brand A formatierte, nachdem
   * auf B umgeschaltet war, bekam still die Zone von B. Geschuetzt hat allein die
   * Aufrufreihenfolge. */
  function formatTime(millis, zone) {
    zone = zone || zoneOf(fire);
    var datum = formatter(zone, text.dateParts).format(new Date(millis));
    var kuerzel = zoneLabel(millis, zone);
    return kuerzel ? datum + " " + kuerzel : datum;
  }

  /* Die Aufnahmezeitpunkte stehen ohne Zonenangabe in den Daten und sind laut
   * API-Schema UTC. Date.parse verlangt dafuer das Z. */
  function at(iso) {
    return Date.parse(/[Zz]|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : iso + "Z");
  }

  function formatDay(millis, zone) {
    return formatter(zone || zoneOf(fire), text.dayParts).format(new Date(millis));
  }

  /* Zeitspanne in Worten. Unter zwei Tagen in Stunden, weil "1 Tag" bei 39
   * Stunden mehr verschweigt als sagt. */
  function describeSpan(millis) {
    var hours = Math.round(millis / 3600000);
    if (hours < 48) return text.hours(hours);
    return text.days(Math.round(hours / 24));
  }

  /* Systemeinstellung "reduzierte Bewegung". Wird bei jedem Aufruf gelesen und
   * nicht einmal gespeichert: die Einstellung laesst sich im Betriebssystem
   * umstellen, waehrend die Seite offen ist. */
  function reducedMotion() {
    return (
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    );
  }

  /* ---------- Zeitstrahl ---------- */

  /* Die Achse beginnt beim Brandausbruch, nicht bei der ersten Aufnahme. Der
   * Abstand dazwischen lag je Brand zwischen 20 und 106 Stunden — er gehört ins
   * Bild, sonst suggeriert die Darstellung, das Feuer habe mit der ersten
   * Satellitenaufnahme begonnen. */
  function timelineBounds(f) {
    var first = at(f.steps[0].acquired);
    var last = at(f.steps[f.steps.length - 1].acquired);
    var outbreak = f.event_time ? at(f.event_time) : first;
    var start = Math.min(outbreak, first);
    /* Fällt alles auf einen Zeitpunkt, würde gleich durch Null geteilt. */
    var span = Math.max(last - start, 3600000);
    return {
      start: start,
      end: start + span,
      span: span,
      outbreak: outbreak,
      first: first,
    };
  }

  var bounds = null;

  function ratioOf(millis) {
    if (!bounds) return 0;
    return Math.max(0, Math.min(1, (millis - bounds.start) / bounds.span));
  }

  function buildTimeline(f) {
    bounds = timelineBounds(f);

    var ticks = $("#timeline-ticks").empty();

    /* Brandausbruch als Dreieck, wenn er vor der ersten Aufnahme liegt. */
    if (bounds.outbreak < bounds.first) {
      $("<div>")
        .addClass("timeline-tick outbreak")
        .css("left", (ratioOf(bounds.outbreak) * 100).toFixed(3) + "%")
        .attr("title", text.outbreak + ": " + formatTime(bounds.outbreak))
        .appendTo(ticks);
    }

    f.steps.forEach(function (step) {
      var t = at(step.acquired);
      $("<div>")
        .addClass("timeline-tick")
        .css("left", (ratioOf(t) * 100).toFixed(3) + "%")
        .attr(
          "title",
          text.acquisition +
            ": " +
            formatTime(t) +
            " — " +
            text.size(step.size_ha),
        )
        .appendTo(ticks);
    });

    /* Schraffierter Bereich bis zur ersten Aufnahme. */
    $("#timeline-unmapped").css(
      "width",
      (ratioOf(bounds.first) * 100).toFixed(3) + "%",
    );

    $("#timeline-from").text(formatDay(bounds.start));
    $("#timeline-to").text(formatDay(bounds.end));

    var mapped = describeSpan(
      at(f.steps[f.steps.length - 1].acquired) - bounds.first,
    );
    var delay = bounds.first - bounds.outbreak;
    var outbreakLabel = formatDay(bounds.outbreak);
    var summary =
      delay >= 3600000
        ? text.summary(outbreakLabel, describeSpan(delay), mapped)
        : text.summaryNoDelay(outbreakLabel, mapped);
    if (!f.closed) summary += " · " + text.stillOpen;
    $("#timeline-summary").text(summary);

    setPlayhead(bounds.first);
  }

  /* Der Schreibkopf sitzt auf der Zeitachse, der rote Balken reicht von der
   * ersten Aufnahme bis dorthin — der schraffierte Teil davor bleibt frei. */
  function setPlayhead(millis) {
    var from = ratioOf(bounds ? bounds.first : millis) * 100;
    var to = ratioOf(millis) * 100;
    $("#timeline-head").css("left", to.toFixed(3) + "%");
    $("#timeline-elapsed").css({
      left: from.toFixed(3) + "%",
      width: Math.max(0, to - from).toFixed(3) + "%",
    });
  }

  /* Dauer und Bildzahl eines Abschnitts aus dem echten Zeitabstand. */
  function stepTiming(from, to) {
    var hours = (at(to.acquired) - at(from.acquired)) / 3600000;
    var duration = Math.max(
      STEP_MIN_MS,
      Math.min(STEP_MAX_MS, Math.round(hours * MS_PER_HOUR)),
    );
    return {
      duration: duration,
      frames: Math.max(12, Math.min(70, Math.round(duration / MS_PER_FRAME))),
    };
  }

  if (typeof _fires === "undefined" || !_fires.length) {
    $("#map")
      .addClass("map-error")
      .text("Keine Branddaten vorhanden — bin/fetch_ems.py ausführen.");
    return;
  }

  /* ---------- Karte ---------- */

  var map = new L.Map("map", {
    minZoom: 4,
    maxZoom: 14,
  });

  /* Der frueher genutzte Kachelserver tilt.odcdn.de existiert nicht mehr.
   * Der Reliefhintergrund von Esri kommt dem damaligen Stamen-Terrain am
   * naechsten und braucht keinen Zugangsschluessel. */
  new L.TileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Shaded_Relief/MapServer/tile/{z}/{y}/{x}",
    {
      maxZoom: 14,
      /* Bewusst kurz gehalten. Die lange Fassung umbrach bei schmaler Breite auf
       * zwei Zeilen und legte sich über Zustandsanzeige und Abspielknopf. Die
       * vollständigen Quellen- und Lizenzangaben stehen im Info-Kasten, der
       * jetzt auch im eingebetteten Zustand erreichbar ist — vorher war er es
       * nicht, weil die Kopfzeile im Rahmen ausgeblendet wird. */
      attribution:
        '<a href="https://mapping.emergency.copernicus.eu/" target="_blank" rel="noopener">Copernicus EMS</a> · ' +
        '<a href="https://openstreetmap.org" target="_blank" rel="noopener">OSM</a> · ' +
        '<a href="https://www.esri.com/" target="_blank" rel="noopener">Esri</a> · ' +
        '<a href="javascript:;" class="attr-info">' +
        text.sources +
        "</a> · " +
        '<a href="' +
        IMPRINT_URL +
        '" target="_blank" rel="noopener">' +
        text.imprint +
        "</a>",
    },
  ).addTo(map);

  /* Ortsnamen als halbtransparente Ebene darueber, damit die Karte lesbar
   * bleibt, ohne den Brandumriss zu verdecken. */
  new L.TileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
    { maxZoom: 14, opacity: 0.55 },
  ).addTo(map);

  var firePolyStyle = {
    stroke: true,
    color: "#8A0B0B",
    opacity: 0.9,
    weight: 1,
    fill: true,
    fillColor: "#BE1313",
    fillOpacity: 0.75,
  };
  var otherPolyStyle = {
    stroke: false,
    fill: true,
    fillColor: "#BE1313",
    fillOpacity: 0.45,
  };
  /* Erreichte Fläche — in Brandrot, nicht als blasser Schatten.
   *
   * Vorher stand hier ein dunkelbraunes Feld mit 12 Prozent Deckkraft. Im
   * Morph-Modus führte das zu einer falschen Aussage: der Überblend-Algorithmus
   * verschiebt jeden Stützpunkt geradlinig auf seinen Nachfolger, und bei einem
   * Flächensprung wie in der Gironde (5.763 auf 26.008 ha) liegt die Zwischenform
   * nicht zwischen beiden Umrissen, sondern daneben. Gemessen: bei 118 von 132
   * Bildern lag schon verbrannte Fläche außerhalb des roten Umrisses, an einer
   * Stelle alle 231 Prüfpunkte — die Grafik zeigte, wie das Feuer von der Fläche
   * wegwandert, die es verbrannt hatte.
   *
   * Verbrannte Fläche verschwindet nicht wieder. Sie bleibt deshalb rot, und der
   * Morph kann nur hinzufügen. Die aktuelle Front ist an ihrer Randlinie
   * erkennbar, nicht mehr daran, dass alles davor verblasst.
   *
   * Nur die Deckkraft, keine eigene Farbangabe: gezeichnet wird über
   * footprintLayer(), das die Farbe aus otherPolyStyle nimmt. Ein zweites
   * fillColor daneben wäre wirkungslos — beim Mutationstest hat genau das eine
   * Ruecknahme vorgetaeuscht, die nichts veraendert hat. */
  var REACHED_FILL_OPACITY = 0.55;

  /* Der Stadtumriss liegt ueber der Brandflaeche. Bei 0,35 Deckkraft zog das
   * weisse Fuellen der roten Flaeche die Farbe, gerade in der Schnittmenge - und
   * damit an der Stelle, um die es beim Vergleich geht. Die Fuellung soll den
   * Umriss als Flaeche lesbar machen, nicht das Darunterliegende ueberdecken;
   * dafuer traegt jetzt die Linie. */
  var cityStyle = {
    stroke: true,
    color: "#1B3A6B",
    opacity: 1,
    weight: 3,
    fill: true,
    fillColor: "#FFFFFF",
    fillOpacity: 0.1,
  };

  var firePoly = new L.Polygon([], firePolyStyle).addTo(map);
  var otherLayer = new L.LayerGroup().addTo(map);
  var historyLayer = new L.LayerGroup().addTo(map);
  var cityLayer = null;
  var cityLabel = null;

  var fire = null;
  var timer = null;
  var playing = false;
  var activeCity = null;

  /* Hat der Leser den Vergleich ausdruecklich abgeschaltet? Dann bleibt er auch
   * beim naechsten Brand aus. Ohne dieses Merkmal kaeme die Voreinstellung bei
   * jedem Brandwechsel zurueck und ueberginge damit eine Entscheidung, die der
   * Leser gerade getroffen hat. */
  var compareOff = false;

  /* Kuerzel im Anker fuer "ausdruecklich ohne Vergleich". Noetig, seit eine
   * Voreinstellung existiert: ohne dieses Kuerzel bedeutet #gironde sowohl
   * "keine Angabe" (dann gilt die Voreinstellung) als auch "kein Vergleich"
   * (dann gilt sie nicht) — und eine Redaktion, die im Konfigurator "ohne
   * Vergleich" waehlt, bekaeme eine Einbettung mit Vergleich. */
  var NO_COMPARE = "none";

  /* ---------- Groessenvergleich ---------- */

  /* Verschiebt einen Stadtumriss an den Brandort und behaelt dabei die
   * tatsaechliche Flaeche. Ein Laengengrad ist in hoeheren Breiten kuerzer,
   * deshalb wird die Ost-West-Ausdehnung mit dem Verhaeltnis der
   * Breitenkosinus korrigiert. Portiert aus bin/move.js der Fassung von 2013,
   * wo die Verschiebung noch einmalig beim Erzeugen der Daten geschah und der
   * Zielort fest im Code stand — bei mehreren umschaltbaren Braenden waere das
   * je Stadt und Brand ein eigener Datensatz. */
  function shiftRings(rings, from, to) {
    var xScale =
      Math.cos((from[0] * Math.PI) / 180) / Math.cos((to[0] * Math.PI) / 180);
    var dLat = from[0] - to[0];
    return rings.map(function (ring) {
      return ring.map(function (point) {
        return [point[0] - dLat, (point[1] - from[1]) * xScale + to[1]];
      });
    });
  }

  /* refit nur bei einer Handlung des Nutzers. Beim Brandwechsel raeumt
   * selectFire ohnehin auf und setzt den Ausschnitt danach selbst — ein
   * zusaetzliches Zoomen dazwischen waere ein sichtbares Zucken.
   *
   * Das Merkmal compareOff setzt diese Funktion bewusst nicht: sie raeumt auch
   * beim Brandwechsel auf, und dort darf die Voreinstellung des naechsten
   * Brandes nicht mitgeloescht werden. Wer den Vergleich abwaehlt, setzt es an
   * der Stelle, an der die Entscheidung faellt. */
  function clearCity(refit) {
    if (cityLayer) {
      map.removeLayer(cityLayer);
      cityLayer = null;
    }
    if (cityLabel) {
      map.removeLayer(cityLabel);
      cityLabel = null;
    }
    activeCity = null;
    $("#map-compare a").removeClass("highlight").removeAttr("aria-current");
    $('#map-compare a[data-city=""]')
      .addClass("highlight")
      .attr("aria-current", "true");
    syncPickers();
    if (refit === true && fire) fitToFire(fire);
    syncHash();
  }

  function showCity(slug) {
    var city = null;
    for (var i = 0; i < _cities.length; i++) {
      if (_cities[i].slug === slug) city = _cities[i];
    }
    if (!city) return;
    compareOff = false;
    if (cityLayer) map.removeLayer(cityLayer);
    if (cityLabel) map.removeLayer(cityLabel);
    cityLayer = new L.Polygon(
      shiftRings(city.rings, city.center, fire.center),
      cityStyle,
    ).addTo(map);
    cityLayer.on("click", function () {
      clearCity(true);
    });

    /* Der Umriss allein sagt nicht, welche Stadt er zeigt. In der Liste ist der
     * Eintrag hervorgehoben, im eingebetteten Zustand mit Auswahlfeldern steht
     * die Antwort nur im zugeklappten Feld — und wer die Grafik als Bild
     * weitergibt, hat gar keine Beschriftung. Die Marke sitzt an der Nordkante
     * des Umrisses und traegt denselben Namen wie der Listeneintrag.
     *
     * Der Name steht im Icon selbst und wird nicht nachtraeglich in das erzeugte
     * Element geschrieben: getElement() liefert null, solange die Karte keine
     * Groesse hat — in einem Rahmen, der erst nach dem Laden bemasst wird, brach
     * showCity an dieser Zeile ab und der Vergleich blieb ganz aus. */
    var nord = cityLayer.getBounds().getNorth();
    var mitte = cityLayer.getBounds().getCenter().lng;
    var beschriftung = document.createElement("span");
    beschriftung.textContent = city.label[lang] || city.label.de;
    cityLabel = L.marker([nord, mitte], {
      interactive: false,
      keyboard: false,
      icon: L.divIcon({
        className: "city-label",
        html: beschriftung.outerHTML,
        iconSize: null,
      }),
    }).addTo(map);
    activeCity = slug;
    syncPickers();
    $("#map-compare a").removeClass("highlight").removeAttr("aria-current");
    $('#map-compare a[data-city="' + slug + '"]')
      .addClass("highlight")
      .attr("aria-current", "true");

    /* Ausschnitt so setzen, dass Brand UND Stadtumriss hineinpassen. Ohne das
     * ist der Vergleich bei kleinen Bränden unsichtbar: die Karte steht auf der
     * Brandfläche, und ein größerer Stadtumriss liegt komplett außerhalb.
     * Aufgefallen bei Fontainebleau — 9,24 km² Brand gegen 105 km² Paris, der
     * Umriss war da, aber nirgends zu sehen.
     *
     * Das Nachziehen des Ausschnitts ist hier erwünscht: einen Vergleich
     * auszuwählen ist eine ausdrückliche Handlung, und die Antwort darauf ist,
     * ihn zu zeigen. */
    fitToComparison();
    syncHash();
  }

  /* Ausschnitt über Brand und aktiven Stadtumriss. Ohne aktiven Vergleich fällt
   * es auf den Brand allein zurück. Weniger Rand als bei der Brandansicht, weil
   * hier zwei Formen hineinmüssen. */
  function fitToComparison() {
    if (!fire) return;
    fitSafely(function () {
      var b = fireBounds(fire);
      if (cityLayer) b.extend(cityLayer.getBounds());
      return b;
    }, 0.12);
  }

  function buildCityButtons() {
    if (typeof _cities === "undefined") return;
    var list = $("#map-compare ul").empty();

    /* Ein zweites Anklicken des aktiven Eintrags hebt den Vergleich auf — das
     * war der einzige Weg zurueck und niemand konnte es wissen. Der Eintrag
     * macht ihn sichtbar und deckt sich mit dem leeren Wert im Auswahlfeld. */
    $("<li>")
      .addClass("no-compare")
      .append(
        $("<a>")
          .attr({ href: "javascript:;", "data-city": "" })
          .text(text.noCompare),
      )
      .appendTo(list);

    _cities.forEach(function (city) {
      $("<li>")
        .append(
          $("<a>")
            .attr({ href: "javascript:;", "data-city": city.slug })
            .text(city.label[lang] || city.label.de),
        )
        .appendTo(list);
    });
    $("#map-compare h2").text(text.compare);
  }

  $(document).on("click", "#map-compare a", function (evt) {
    evt.preventDefault();
    var slug = $(this).attr("data-city");
    if (!slug || slug === activeCity) {
      compareOff = true;
      clearCity(true);
      return;
    }
    showCity(slug);
  });

  /* ---------- Animation ---------- */

  /* Der Anker haelt Brand und Vergleichsstadt fest, damit ein bestimmter
   * Vergleich verlinkbar ist: #gironde/bordeaux. Der abgeschaltete Vergleich
   * braucht dabei ein eigenes Kuerzel — siehe NO_COMPARE. */
  function syncHash() {
    if (!fire) return;
    var teil = activeCity
      ? "/" + activeCity
      : compareOff
        ? "/" + NO_COMPARE
        : "";
    var target = "#" + fire.slug + teil;
    if (window.location.hash !== target) {
      window.history.replaceState(null, "", target);
    }
  }

  function setButtonState(state) {
    $("#map-startstop-label").text(text[state] || text.play);
    /* Auch das title-Attribut, nicht nur die Beschriftung: es stand fest auf
     * "Verlauf abspielen", auch wenn der Knopf gerade "Pause" hiess. */
    $("#map-startstop").attr("title", text.buttonTitle[state] || text.buttonTitle.play);
  }

  function stop() {
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
    playing = false;
    $("#map-container").removeClass("playing");
    setButtonState("again");
  }

  function drawOthers(step) {
    otherLayer.clearLayers();
    (step.others || []).forEach(function (ring) {
      otherLayer.addLayer(new L.Polygon(ring, otherPolyStyle));
    });
  }

  function showStep(step) {
    firePoly.setLatLngs(step.polygon);
    drawOthers(step);
    $("#map-date").text(formatTime(at(step.acquired)));
    $("#map-size").text(text.size(step.size_ha));
    setPlayhead(at(step.acquired));
  }

  /* Zeit und Flaeche zwischen zwei Aufnahmen fortschreiben. Linear
   * interpoliert und damit eine Darstellungshilfe, keine Messung — was
   * zwischen zwei Satellitenueberfluegen genau geschah, ist nicht bekannt. */
  function updateReadout(from, to, ratio) {
    var t0 = at(from.acquired);
    var t1 = at(to.acquired);
    var now = t0 + (t1 - t0) * ratio;
    $("#map-date").text(formatTime(now));
    $("#map-size").text(
      text.size(from.size_ha + (to.size_ha - from.size_ha) * ratio),
    );
    setPlayhead(now);
  }

  function finish(redrawLast) {
    if (redrawLast) showStep(fire.steps[fire.steps.length - 1]);
    setPlayhead(at(fire.steps[fire.steps.length - 1].acquired));
    playing = false;
    timer = null;
    $("#map-container").removeClass("playing").addClass("played");
    setButtonState("again");
  }

  /* Bei stark zerstreuten Braenden waechst die groesste zusammenhaengende
   * Flaeche kaum, waehrend die Gesamtflaeche stark zunimmt — ein Ueberblenden
   * des groessten Umrisses wuerde dort Stillstand suggerieren. Stattdessen wird
   * jeder neue Stand vollstaendig eingeblendet und bleibt liegen; verbrannte
   * Flaeche verschwindet ohnehin nicht wieder. Welcher Modus greift, entscheidet
   * die Datenpipeline anhand des Flaechenanteils (Feld mode). */
  function footprintLayer(step, fillOpacity) {
    var group = new L.LayerGroup();
    var style = $.extend({}, otherPolyStyle, { fillOpacity: fillOpacity });
    group.addLayer(new L.Polygon(step.polygon, style));
    (step.others || []).forEach(function (ring) {
      group.addLayer(new L.Polygon(ring, style));
    });
    return group;
  }

  /* Der erreichte Stand samt seiner Nebenflächen. Vorher blieb im Morph-Modus nur
   * die Hauptfläche als Schatten liegen; die Streufeuer daneben — bei zerstreuten
   * Bränden ein erheblicher Teil der Fläche — verschwanden beim Übergang ganz. */
  function reachedFootprint(step) {
    return footprintLayer(step, REACHED_FILL_OPACITY);
  }

  function playCrossfade() {
    var index = 0;
    var target = firePolyStyle.fillOpacity;

    firePoly.setLatLngs([]);
    otherLayer.clearLayers();
    historyLayer.addLayer(footprintLayer(fire.steps[0], target));

    function fadeStep() {
      var from = fire.steps[index];
      var to = fire.steps[index + 1];
      var timing = stepTiming(from, to);
      var incoming = footprintLayer(to, 0);
      historyLayer.addLayer(incoming);

      var frameInStep = 0;
      timer = setInterval(
        function () {
          frameInStep++;

          var ratio = Math.min(1, frameInStep / timing.frames);
          incoming.eachLayer(function (layer) {
            layer.setStyle({ fillOpacity: target * ratio });
          });

          updateReadout(from, to, ratio);

          if (ratio < 1) return;

          clearInterval(timer);
          timer = null;
          index++;
          if (index + 1 < fire.steps.length) {
            fadeStep();
          } else {
            finish(false);
          }
        },
        Math.round(timing.duration / timing.frames),
      );
    }

    fadeStep();
  }

  function play() {
    if (playing || !fire || fire.steps.length < 2) return;

    playing = true;
    $("#map-container").addClass("playing").removeClass("played");
    setButtonState("pause");
    historyLayer.clearLayers();

    if (fire.mode === "crossfade") {
      playCrossfade();
      return;
    }

    var index = 0;

    showStep(fire.steps[0]);

    function morphStep() {
      var from = fire.steps[index];
      var to = fire.steps[index + 1];
      var timing = stepTiming(from, to);

      /* Der erreichte Stand bleibt als Brandfläche liegen — samt Nebenflächen.
       * Der Überblend-Umriss darf sich darüber bewegen, wie er will; verbrannte
       * Fläche bleibt dann verbrannt, und die Bewegung fügt nur hinzu. */
      historyLayer.addLayer(reachedFootprint(from));

      var frameInStep = 0;

      timer = polymorph.run(
        from.polygon.map(function (p) {
          return [p[0], p[1]];
        }),
        to.polygon.map(function (p) {
          return [p[0], p[1]];
        }),
        timing.frames,
        timing.duration,
        function (end, ring) {
          if (!ring || !ring.length) return;

          frameInStep++;
          firePoly.setLatLngs(ring);
          updateReadout(from, to, Math.min(1, frameInStep / timing.frames));

          if (!end) return;

          drawOthers(to);
          index++;
          if (index + 1 < fire.steps.length) {
            morphStep();
          } else {
            finish(true);
          }
        },
      );
    }

    morphStep();
  }

  /* ---------- Kartenausschnitt ---------- */

  /* Setzt einen Ausschnitt und wartet, bis der Container eine brauchbare Größe
   * hat. Der Wiederholversuch ist zwingend: fitBounds berechnet die Zoomstufe aus
   * der Containergröße. Steht die noch nicht fest — in einem gerade eingefügten
   * iframe der Regelfall — ergibt die Rechnung eine Stufe unterhalb von minZoom,
   * und statt des Motivs ist halb Europa zu sehen. Trat bei 470 Pixel breiten
   * Rahmen zuverlässig auf, während die Vollbildansicht unauffällig blieb. */
  function fitSafely(getBounds, padding, attempt) {
    map.invalidateSize(false);

    var size = map.getSize();
    if ((size.x < 60 || size.y < 60) && (attempt || 0) < 12) {
      setTimeout(function () {
        fitSafely(getBounds, padding, (attempt || 0) + 1);
      }, 60);
      return;
    }

    /* Ohne Zoom-Animation. Nicht aus Geschmack: waehrend der Animation steht die
     * Marke des Stadtumrisses noch an ihrem alten Platz, waehrend die Karte
     * schon woanders ist — platziereMarke() maesse dann einen Zwischenstand und
     * klappte die Marke falsch oder gar nicht um. Der Sprung ist ausserdem
     * derselbe, den der Brandwechsel ohnehin macht. */
    var b = getBounds();
    if (b && b.isValid()) map.fitBounds(b.pad(padding), { animate: false });
  }

  function fireBounds(f) {
    var last = f.steps[f.steps.length - 1];
    var b = new L.LatLngBounds(last.polygon);
    (last.others || []).forEach(function (ring) {
      b.extend(new L.LatLngBounds(ring));
    });
    return b;
  }

  function fitToFire(f) {
    fitSafely(function () {
      return fireBounds(f);
    }, 0.35);
  }

  /* Ändert sich die Rahmengröße nachträglich — Drehen eines Telefons, ein
   * aufklappendes Layout —, passt der Ausschnitt sonst nicht mehr. Ist ein
   * Vergleich eingeblendet, bleibt er im Bild. */
  var resizeTimer = null;
  $(window).on("resize", function () {
    if (resizeTimer) clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      resizeTimer = null;
      if (!fire) return;
      if (cityLayer) fitToComparison();
      else fitToFire(fire);
    }, 250);
  });

  /* ---------- Brand wechseln ---------- */

  function selectFire(slug, citySlug) {
    /* Nur innerhalb der Auswahl suchen. Sonst oeffnete ein Anker auf einen
     * ausgefilterten Brand ihn trotzdem — die Einbettung haette gezeigt, was sie
     * gerade nicht zeigen soll. */
    var sichtbar = visibleFires();
    var next = null;
    for (var i = 0; i < sichtbar.length; i++) {
      if (sichtbar[i].slug === slug) next = sichtbar[i];
    }
    if (!next) next = sichtbar[0];

    stop();
    fire = next;

    historyLayer.clearLayers();
    otherLayer.clearLayers();
    clearCity();
    $("#map-container").removeClass("played");

    $("#fire-region").text(fire.region[lang] || fire.region.de);
    $("#fire-source").attr("href", fire.source_url).text(fire.activation);
    $("#fire-status").text(fire.closed ? text.contained : text.ongoing);
    $("#fire-steps").text(text.steps(fire.steps.length));
    $("#fire-note").text(fire.steps.length < 2 ? text.single : "");

    /* aria-current zusaetzlich zur Klasse: die Hervorhebung war allein farbig,
     * ein Screenreader nannte fuenf gleichwertige Verweise. */
    $("#map-fires a").removeClass("highlight").removeAttr("aria-current");
    $('#map-fires a[data-fire="' + fire.slug + '"]')
      .addClass("highlight")
      .attr("aria-current", "true");
    markDefaultCity();
    syncPickers();
    updateScrollHints();

    /* Ausschnitt auf die letzte, groesste Ausdehnung setzen — einschliesslich
     * der Nebenflaechen, die bei zerstreuten Braenden weit ueber die
     * Hauptflaeche hinausreichen. */
    fitToFire(fire);
    buildTimeline(fire);
    showStep(fire.steps[0]);
    setButtonState(fire.steps.length < 2 ? "again" : "play");

    /* Ohne Angabe in der Adresse gilt die Voreinstellung aus den Daten. Der
     * Groessenvergleich ist die Aussage dieser Anwendung — stand er im Standard
     * aus, war sie in jeder Einbettung unsichtbar, die keinen Anker mit Stadt
     * trug, und das ist der Code, den der Konfigurator ausgibt.
     *
     * Der Ausschnitt zoomt dafuer beim Laden weiter heraus als die Brandflaeche
     * allein braucht. Das ist der Preis und er ist gewollt: die Flaeche ohne
     * Bezugsgroesse ist eine rote Form ohne Groessenordnung. */
    if (citySlug === NO_COMPARE) {
      compareOff = true;
    } else {
      var ziel = citySlug || defaultCity();
      if (ziel) showCity(ziel);
    }
    syncHash();

    /* Kein Autostart, wenn das System reduzierte Bewegung verlangt. Der letzte
     * Stand steht dann sofort da — die Aussage der Grafik ist die Fläche, nicht
     * die Bewegung — und wer den Verlauf sehen will, drückt den Knopf. Eine
     * Animation, die von selbst losläuft und länger als fünf Sekunden dauert,
     * braucht nach WCAG 2.2.2 ohnehin einen Weg, sie anzuhalten; hier ist der
     * bessere Weg, sie gar nicht zu erzwingen. */
    if (reducedMotion()) {
      finish(true);
      setButtonState("play");
    } else {
      play();
    }
  }

  /* Die Voreinstellung steht je Brand in den Daten (Feld compare, gesetzt von
   * bin/fetch_ems.py). Abgeschaltet, wenn der Leser den Vergleich ausdruecklich
   * weggeklickt hat, und uebergangen, wenn die genannte Stadt nicht mehr in der
   * Liste steht — eine geaenderte Staedteliste soll keine leere Auswahl
   * hinterlassen. */
  function defaultCity() {
    if (compareOff || !fire || !fire.compare) return null;
    if (typeof _cities === "undefined") return null;
    for (var i = 0; i < _cities.length; i++) {
      if (_cities[i].slug === fire.compare) return fire.compare;
    }
    return null;
  }

  /* Füllt die Zahlen im Info-Kasten aus den Daten. Vorher standen dort feste
   * Werte — die Spanne "21 bis 106 Stunden" stammte aus der Zeit mit vier
   * Bränden und war mit dem fünften falsch, ohne dass es auffiel. Was sich mit
   * den Daten ändert, darf nicht im Text festgeschrieben stehen. */
  function fillInfoFigures() {
    var zahlwort = {
      de: [
        "kein",
        "ein",
        "zwei",
        "drei",
        "vier",
        "fünf",
        "sechs",
        "sieben",
        "acht",
        "neun",
      ],
      en: [
        "no",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
      ],
    }[lang];
    var n = visibleFires().length;
    $("#info-count").text(n < zahlwort.length ? zahlwort[n] : String(n));

    /* Verzug zwischen gemeldetem Ausbruch und erster Aufnahme, über alle Brände. */
    var verzuege = visibleFires()
      .filter(function (f) {
        return f.event_time;
      })
      .map(function (f) {
        return at(f.steps[0].acquired) - at(f.event_time);
      })
      .filter(function (ms) {
        return ms > 0;
      });

    if (!verzuege.length) return;
    var min = Math.min.apply(null, verzuege);
    var max = Math.max.apply(null, verzuege);
    $("#info-delay-span").text(
      min === max
        ? describeSpan(min)
        : describeSpan(min) + text.rangeJoin + describeSpan(max),
    );
  }

  /* Kompakte Auswahl fuer flache Rahmen. Traegt dieselben Eintraege wie die
   * beiden Listen und wird von denselben Funktionen mitgefuehrt — es gibt keinen
   * zweiten Zustand, nur eine zweite Darstellung. Welche der beiden sichtbar
   * ist, entscheidet allein das Stylesheet ueber die Rahmenhoehe. */
  /* Zeigt an, dass eine Liste weitergeht. Gelesen wird der tatsaechliche
   * Scrollzustand, nicht die Anzahl der Eintraege — eine Liste kann bei einer
   * Rahmenhoehe vollstaendig passen und bei der naechsten nicht. Deshalb auch
   * beim Groessenwechsel neu bestimmt.
   *
   * Gezaehlt wird ueber die Eintraege selbst, nicht ueber die Restpixel des
   * Scrollbereichs: nur so laesst sich die Zahl nennen, und nur so deckt sich die
   * Anzeige mit dem, was ein Leser sieht. Die Pixelrechnung schwieg bei einem um
   * einen Pixel angeschnittenen Eintrag — sichtbar unvollstaendig, laut Anzeige
   * vollstaendig. */
  function hiddenEntries(ul) {
    var fenster = ul.getBoundingClientRect();
    var oben = 0;
    var unten = 0;
    Array.prototype.forEach.call(ul.children, function (li) {
      var r = li.getBoundingClientRect();
      if (r.top < fenster.top - 1) oben++;
      else if (r.bottom > fenster.bottom + 1) unten++;
    });
    return { oben: oben, unten: unten };
  }

  function updateScrollHints() {
    ["#map-fires", "#map-compare"].forEach(function (sel) {
      var box = $(sel);
      var ul = box.find("ul")[0];
      if (!ul) return;
      var verdeckt = hiddenEntries(ul);
      box.toggleClass("has-more", verdeckt.unten > 0);
      box.toggleClass("has-before", verdeckt.oben > 0);

      var hinweis = "";
      if (verdeckt.oben && verdeckt.unten) {
        hinweis = text.hiddenBoth(verdeckt.oben, verdeckt.unten);
      } else if (verdeckt.unten) {
        hinweis = text.hiddenBelow(verdeckt.unten);
      } else if (verdeckt.oben) {
        hinweis = text.hiddenAbove(verdeckt.oben);
      }
      box.find(".list-hint").text(hinweis);
    });
  }

  /* ---------- Kompakte Zustandsanzeige ---------- */

  /* Die Schwelle steht im Stylesheet, nicht hier: dort liegt schon die Regel, die
   * das Umschalten der Auswahl entscheidet, und zwei Zahlen an zwei Stellen waeren
   * beim naechsten Verschieben still auseinandergelaufen. Gelesen wird die Wirkung
   * (--compact), nicht die Bedingung. */
  function cardIsCompact() {
    var el = document.getElementById("map-controls");
    if (!el) return false;
    return getComputedStyle(el).getPropertyValue("--compact").trim() === "1";
  }

  /* Nur beim Wechsel gesetzt, nicht bei jedem Ereignis: hat jemand die Angaben in
   * der kompakten Fassung von Hand aufgeklappt, soll ein Groessenwechsel innerhalb
   * derselben Fassung sie nicht wieder zuklappen. */
  var lastCardMode = null;

  function applyCardMode() {
    var compact = cardIsCompact();
    if (compact === lastCardMode) return;
    lastCardMode = compact;
    $("#fire-details").prop("open", !compact);
  }

  /* Direkt an den Listen, nicht delegiert über das Dokument: scroll-Ereignisse
   * steigen nicht auf, ein delegierter Zuhörer wird für ein scrollendes Element
   * darum nie ausgelöst. Die Hinweiszeile blieb dadurch auf dem Stand des
   * letzten Neuaufbaus stehen — nach jedem Scrollen nannte sie eine Zahl, die
   * nicht mehr stimmte. Die Listen selbst werden nie ersetzt, nur ihr Inhalt;
   * einmal binden genügt. */
  $("#map-fires ul, #map-compare ul").on("scroll", updateScrollHints);
  $(window).on("resize", updateScrollHints);

  /* Und noch einmal, wenn das Layout wirklich steht. Die Zeile nennt eine Zahl
   * verdeckter Einträge, und die hängt an gerenderter Geometrie: solange die
   * Schriften nachladen, sind die Zeilenhöhen andere. Beim Umstellen auf
   * defer-geladene Skripte fiel das auf — die Zeile sagte „2 weitere", außerhalb
   * lag einer. Eine Zahl, die im Moment ihres Erscheinens falsch ist, ist
   * schlimmer als keine. */
  $(window).on("load", updateScrollHints);
  if (document.fonts && document.fonts.ready && document.fonts.ready.then) {
    document.fonts.ready.then(updateScrollHints);
  }
  $(window).on("resize", applyCardMode);

  function buildPickers() {
    $("#map-picker [data-label=fires]").text(text.fires);
    $("#map-picker [data-label=compare]").text(text.compare);

    var fires = $("#pick-fire").empty();
    visibleFires().forEach(function (item) {
      $("<option>")
        .attr("value", item.slug)
        .text(item.name[lang] || item.name.de)
        .appendTo(fires);
    });

    /* Der erste Eintrag hebt den Vergleich auf. Ein Auswahlfeld hat immer einen
     * Wert — ohne diesen Eintrag gaebe es keinen Weg zurueck zur reinen
     * Brandfläche, den die Liste ueber ein zweites Anklicken bietet. */
    var cities = $("#pick-city").empty();
    $("<option>").attr("value", "").text(text.noCompare).appendTo(cities);
    if (typeof _cities !== "undefined") {
      _cities.forEach(function (city) {
        $("<option>")
          .attr("value", city.slug)
          .text(city.label[lang] || city.label.de)
          .appendTo(cities);
      });
    }

    syncPickers();
  }

  function syncPickers() {
    if (fire) $("#pick-fire").val(fire.slug);
    $("#pick-city").val(activeCity || "");
  }

  $(document).on("change", "#pick-fire", function () {
    selectFire($(this).val());
  });

  $(document).on("change", "#pick-city", function () {
    var slug = $(this).val();
    if (!slug) {
      compareOff = true;
      clearCity(true);
      return;
    }
    showCity(slug);
  });

  /* Markiert die voreingestellte Stadt in der Liste. Die Wahl selbst wird hier
   * nicht mehr gerechnet: sie steht je Brand in den Daten, gesetzt von
   * bin/fetch_ems.py als die naechstgelegene der fuenf Staedte. Vorher rechnete
   * das Frontend dieselbe Entfernung bei jedem Brandwechsel neu — zwei Orte
   * derselben Aussage, und nur einer davon in einer Datei, die man ansehen kann.
   *
   * Die Markierung bleibt sichtbar, auch wenn der Vergleich gerade
   * abgeschaltet oder eine andere Stadt gewaehlt ist: sie sagt, welcher Eintrag
   * zu diesem Brand gehoert, nicht welcher gerade aktiv ist. */
  function markDefaultCity() {
    $("#map-compare a").removeClass("nearest").removeAttr("title");
    var legende = $("#map-compare .compare-legend");

    if (!fire || !fire.compare) {
      legende.prop("hidden", true).text("");
      return;
    }

    var eintrag = $('#map-compare a[data-city="' + fire.compare + '"]');
    eintrag.addClass("nearest").attr("title", text.nearest);

    /* Die Legende erscheint nur, wenn es auch eine Markierung gibt — und nur,
     * wenn die Liste sichtbar ist. In der kompakten Darstellung tritt ein
     * Auswahlfeld an ihre Stelle, dort ist der Eintrag schon vorgewählt und eine
     * Legende erklärte etwas, das man nicht sieht.
     *
     * Ohne diese Zeile stand vor dem Eintrag ein Viereck ohne Bedeutung. Die
     * Erklärung steckte allein im title-Attribut, also im Hover — auf einem
     * Touchscreen nirgends. Aufgefallen am 31.07.2026 beim Ansehen der Anwendung. */
    var sichtbar =
      eintrag.length > 0 && legende.closest("#map-compare").is(":visible");
    legende.prop("hidden", !sichtbar).text(sichtbar ? text.nearestLegend : "");
  }

  function buildFireButtons() {
    var list = $("#map-fires ul").empty();
    visibleFires().forEach(function (item) {
      /* Kurzname in der Liste, voller Name überall sonst. Bei 132 Pixel
       * Listenbreite brechen die vollen Namen auf zwei Zeilen, und die Liste
       * passt dann je nach Schriftmetrik nicht mehr in ihren Kasten — auf dem
       * CI-Läufer fiel dadurch ein Brand heraus, lokal nicht. Das title-Attribut
       * trägt den vollen Namen weiter, und unter der Karte steht ohnehin die
       * Region. */
      var kurz = (item.name_short && item.name_short[lang]) || item.name[lang] || item.name.de;
      var voll = item.name[lang] || item.name.de;
      $("<li>")
        .append(
          $("<a>")
            .attr({ href: "javascript:;", "data-fire": item.slug, title: voll })
            .text(kurz),
        )
        .appendTo(list);
    });
    $("#map-fires h2").text(text.fires);
  }

  $(document).on("click", "#map-fires a", function (evt) {
    evt.preventDefault();
    selectFire($(this).attr("data-fire"));
  });

  /* ---------- Bedienelemente ---------- */

  $("#map-startstop").click(function (evt) {
    evt.preventDefault();
    if (playing) {
      stop();
    } else {
      play();
    }
  });

  /* Der Verweis in der Herkunftsangabe öffnet denselben Kasten. Er ist die
   * einzige Route dorthin, wenn die Anwendung eingebettet läuft und die
   * Kopfzeile ausgeblendet ist — und damit der Weg, auf dem die Lizenz- und
   * Quellenangaben auch beim Einbetten erreichbar bleiben. Delegiert
   * gebunden, weil Leaflet die Herkunftsangabe selbst erzeugt. */
  /* Escape schliesst, was offen ist. Vorher fuehrte nur der Schliessen-Link
   * heraus — bei einem Kasten, der die halbe Karte bedeckt, ist das die
   * Bedienung, die jeder zuerst versucht. */
  $(document).on("keydown", function (evt) {
    if (evt.key !== "Escape" && evt.keyCode !== 27) return;
    var main = $("#main");
    if (main.hasClass("show-info") || main.hasClass("show-share")) {
      main.removeClass("show-info show-share");
    }
  });

  $(document).on("click", "#button-info, .attr-info", function (evt) {
    evt.preventDefault();
    $("#main").removeClass("show-share").toggleClass("show-info");
  });

  $("#button-share").click(function (evt) {
    evt.preventDefault();
    $("#main").removeClass("show-info").toggleClass("show-share");
  });

  $(document).on("click", ".overlay-close", function (evt) {
    evt.preventDefault();
    $("#main").removeClass("show-info show-share");
  });

  $(".share-pop").click(function (evt) {
    evt.preventDefault();
    window.open(
      $(this).attr("href"),
      "share",
      "width=560,height=340,status=no,scrollbars=no,resizable=no,menubar=no,toolbar=no",
    );
  });

  /* ---------- Start ---------- */

  selection = readSelection();

  buildFireButtons();
  buildCityButtons();
  buildPickers();
  fillInfoFigures();
  updateScrollHints();

  $("#fire-details-label").text(text.details);
  applyCardMode();

  /* Der Sprachwechsel nimmt Auswahl und Anker mit. Vorher trug der Verweis nur
   * den Dateinamen: wer bei #artana/madrid auf EN klickte, landete beim ersten
   * Brand mit Voreinstellung und musste sich neu zurechtfinden.
   *
   * Beim Klick gesetzt, nicht einmal beim Laden: der Anker aendert sich mit jeder
   * Auswahl (syncHash schreibt ihn per replaceState), ein einmal gesetzter Verweis
   * traegt danach den Stand von vorhin. */
  $(document).on("click", "#nav a[href*='index-']", function () {
    var a = $(this);
    var basis = a.attr("href").split("?")[0].split("#")[0];
    a.attr("href", basis + window.location.search + window.location.hash);
  });

  if (window.top !== window) {
    $("html").addClass("in-frame");

    /* Verweis auf die vollstaendige Anwendung. Er gehoert in die Herkunftszeile,
     * weil das die einzige Stelle ist, die im Rahmen sichtbar bleibt — die
     * Kopfzeile wird dort ausgeblendet.
     *
     * Der Anker wird mitgenommen, die Auswahl bewusst nicht: in der eingebetteten
     * Fassung ist sie von der Redaktion festgelegt, in der vollen Anwendung soll
     * sie der Leser selbst bestimmen koennen. Mit ?nur= im Verweis waere sie dort
     * genauso eingeschraenkt. */
    var ziel =
      FULL_APP_URL +
      (lang === "de" ? "" : "index-en.html") +
      window.location.hash;

    /* Ueber addAttribution, nicht per append in das Element: Leaflet baut die
     * Herkunftszeile bei jeder hinzugefuegten Ebene neu auf. Ein angehaengter
     * Verweis verschwand dadurch wieder, sobald der erste Brand gezeichnet wurde
     * — sichtbar war er nur in dem Augenblick zwischen Aufbau und erster
     * Auswahl, also nie. */
    map.attributionControl.addAttribution(
      '<a href="' +
        ziel +
        '" target="_blank" rel="noopener">' +
        text.fullApp +
        "</a>",
    );
  }

  /* Anker der Form #brand oder #brand/stadt */
  function parseHash() {
    var parts = window.location.hash.replace("#", "").split("/");
    return { fire: parts[0] || visibleFires()[0].slug, city: parts[1] || null };
  }

  var start = parseHash();
  selectFire(start.fire, start.city);

  $(window).on("hashchange", function () {
    var target = parseHash();
    if (!fire) return;
    if (target.fire !== fire.slug) {
      selectFire(target.fire, target.city);
      return;
    }

    /* Gleicher Brand, andere Angabe zur Stadt. Drei Faelle: eine Stadt, das
     * Kuerzel fuer "ohne Vergleich", oder gar nichts — und gar nichts heisst
     * wie beim Laden: es gilt die Voreinstellung. */
    var wunsch;
    if (target.city === NO_COMPARE) {
      wunsch = null;
      compareOff = true;
    } else if (target.city) {
      wunsch = target.city;
    } else {
      compareOff = false;
      wunsch = defaultCity();
    }
    if (wunsch === activeCity) return;
    if (wunsch) {
      showCity(wunsch);
    } else {
      clearCity(true);
    }
  });
});
