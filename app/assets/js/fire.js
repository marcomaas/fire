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

  /* Die Aufnahmezeitpunkte kommen laut API-Schema in UTC. Mitteleuropaeische
   * Sommerzeit liegt zwei Stunden davor. Bewusst fest verdrahtet, weil moment
   * hier ohne Zeitzonendatenbank eingebunden ist und alle dargestellten
   * Braende in derselben Zone liegen. */
  var TZ_OFFSET_HOURS = 2;

  /* Impressum der Datenfreunde. Steht in der Herkunftszeile der Karte, weil eine
   * randlose Kartenanwendung keine eigene Fußzeile hat — und weil das die
   * einzige Stelle ist, die auch im eingebetteten Zustand sichtbar bleibt. */
  var IMPRINT_URL = "https://www.datenfreunde.com/impressum";

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
      dateFormat: "DD.MM.YYYY HH:mm",
      tzLabel: "MESZ",
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
      outbreak: "Brandausbruch",
      acquisition: "Satellitenaufnahme",
      dayShort: "DD.MM.",
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
      nearest: "am nächsten zum Brandort",
    },
    en: {
      dateFormat: "YYYY-MM-DD HH:mm",
      tzLabel: "CEST",
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
      outbreak: "Fire outbreak",
      acquisition: "Satellite acquisition",
      dayShort: "MMM D",
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
      nearest: "closest to the fire",
    },
  }[lang];

  function formatTime(millis) {
    return (
      moment.utc(millis).add(TZ_OFFSET_HOURS, "hours").format(text.dateFormat) +
      " " +
      text.tzLabel
    );
  }

  function at(iso) {
    return moment.utc(iso).valueOf();
  }

  function formatDay(millis) {
    return moment
      .utc(millis)
      .add(TZ_OFFSET_HOURS, "hours")
      .format(text.dayShort);
  }

  /* Zeitspanne in Worten. Unter zwei Tagen in Stunden, weil "1 Tag" bei 39
   * Stunden mehr verschweigt als sagt. */
  function describeSpan(millis) {
    var hours = Math.round(millis / 3600000);
    if (hours < 48) return text.hours(hours);
    return text.days(Math.round(hours / 24));
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
  var historyPolyStyle = {
    stroke: false,
    fill: true,
    fillColor: "#221100",
    fillOpacity: 0.12,
  };
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
   * zusaetzliches Zoomen dazwischen waere ein sichtbares Zucken. */
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
    $("#map-compare a").removeClass("highlight");
    $('#map-compare a[data-city=""]').addClass("highlight");
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
     * des Umrisses und traegt denselben Namen wie der Listeneintrag. */
    var nord = cityLayer.getBounds().getNorth();
    var mitte = cityLayer.getBounds().getCenter().lng;
    cityLabel = L.marker([nord, mitte], {
      interactive: false,
      keyboard: false,
      icon: L.divIcon({
        className: "city-label",
        html: '<span></span>',
        iconSize: null,
      }),
    }).addTo(map);
    cityLabel.getElement().querySelector("span").textContent =
      city.label[lang] || city.label.de;
    activeCity = slug;
    syncPickers();
    $("#map-compare a").removeClass("highlight");
    $('#map-compare a[data-city="' + slug + '"]').addClass("highlight");

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
      clearCity(true);
      return;
    }
    showCity(slug);
  });

  /* ---------- Animation ---------- */

  /* Der Anker haelt Brand und optional die Vergleichsstadt fest, damit ein
   * bestimmter Vergleich verlinkbar ist: #gironde/bordeaux */
  function syncHash() {
    if (!fire) return;
    var target = "#" + fire.slug + (activeCity ? "/" + activeCity : "");
    if (window.location.hash !== target) {
      window.history.replaceState(null, "", target);
    }
  }

  function setButtonState(state) {
    $("#map-startstop-label").text(text[state] || text.play);
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

      /* Der erreichte Stand bleibt als blasser Schatten liegen, damit das
       * Wachstum auch am Ende noch nachvollziehbar ist. */
      historyLayer.addLayer(new L.Polygon(from.polygon, historyPolyStyle));

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

  /* Setzt den Ausschnitt auf die letzte, größte Ausdehnung — einschließlich der
   * Nebenflächen, die bei zerstreuten Bränden weit über die Hauptfläche
   * hinausreichen.
   *
   * Der Umweg über invalidateSize und den Wiederholversuch ist nötig, weil
   * fitBounds die Zoomstufe aus der Containergröße berechnet. Steht die noch
   * nicht fest — in einem gerade eingefügten iframe der Regelfall — ergibt die
   * Rechnung eine Stufe unterhalb von minZoom, und Leaflet zeigt statt des
   * Brandes halb Europa. Trat bei 470 Pixel breiten Rahmen zuverlässig auf,
   * während die Vollbildansicht unauffällig blieb. */
  /* Setzt einen Ausschnitt und wartet, bis der Container eine brauchbare Größe
   * hat. Der Wiederholversuch ist zwingend: fitBounds berechnet die Zoomstufe
   * aus der Containergröße, und in einem gerade eingefügten iframe steht die
   * noch nicht fest. Die Rechnung ergibt dann eine Stufe unterhalb von minZoom,
   * und statt des Motivs ist halb Europa zu sehen. */
  function fitSafely(getBounds, padding, attempt) {
    map.invalidateSize(false);

    var size = map.getSize();
    if ((size.x < 60 || size.y < 60) && (attempt || 0) < 12) {
      setTimeout(function () {
        fitSafely(getBounds, padding, (attempt || 0) + 1);
      }, 60);
      return;
    }

    var b = getBounds();
    if (b && b.isValid()) map.fitBounds(b.pad(padding));
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
    var next = null;
    for (var i = 0; i < _fires.length; i++) {
      if (_fires[i].slug === slug) next = _fires[i];
    }
    if (!next) next = _fires[0];

    stop();
    fire = next;

    historyLayer.clearLayers();
    otherLayer.clearLayers();
    clearCity();
    $("#map-container").removeClass("played");

    $("#fire-name").text(fire.name[lang] || fire.name.de);
    $("#fire-region").text(fire.region[lang] || fire.region.de);
    $("#fire-source").attr("href", fire.source_url).text(fire.activation);
    $("#fire-status").text(fire.closed ? text.contained : text.ongoing);
    $("#fire-steps").text(text.steps(fire.steps.length));
    $("#fire-note").text(fire.steps.length < 2 ? text.single : "");

    $("#map-fires a").removeClass("highlight");
    $('#map-fires a[data-fire="' + fire.slug + '"]').addClass("highlight");
    markNearestCity();
    syncPickers();
    updateScrollHints();

    /* Ausschnitt auf die letzte, groesste Ausdehnung setzen — einschliesslich
     * der Nebenflaechen, die bei zerstreuten Braenden weit ueber die
     * Hauptflaeche hinausreichen. */
    fitToFire(fire);
    buildTimeline(fire);
    showStep(fire.steps[0]);
    setButtonState(fire.steps.length < 2 ? "again" : "play");

    if (citySlug) showCity(citySlug);
    syncHash();

    play();
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
    var n = _fires.length;
    $("#info-count").text(n < zahlwort.length ? zahlwort[n] : String(n));

    /* Verzug zwischen gemeldetem Ausbruch und erster Aufnahme, über alle Brände. */
    var verzuege = _fires
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
   * beim Groessenwechsel neu bestimmt. */
  function updateScrollHints() {
    ["#map-fires", "#map-compare"].forEach(function (sel) {
      var box = $(sel);
      var ul = box.find("ul")[0];
      if (!ul) return;
      var rest = ul.scrollHeight - ul.clientHeight - ul.scrollTop;
      box.toggleClass("has-more", rest > 2);
      box.toggleClass("has-before", ul.scrollTop > 2);
    });
  }

  $(document).on("scroll", "#map-fires ul, #map-compare ul", updateScrollHints);
  $(window).on("resize", updateScrollHints);

  function buildPickers() {
    $("#map-picker [data-label=fires]").text(text.fires);
    $("#map-picker [data-label=compare]").text(text.compare);

    var fires = $("#pick-fire").empty();
    _fires.forEach(function (item) {
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
      clearCity(true);
      return;
    }
    showCity(slug);
  });

  /* Naechstgelegene Stadt zum Brandort. Kein automatisches Einblenden: der
   * Ausschnitt muesste dafuer beide Formen fassen und zoomte beim Laden heraus,
   * bevor jemand den Brand gesehen hat. Stattdessen ein Vorschlag in der Liste —
   * fuer einen Brand in der Gironde ist Bordeaux die naheliegende Bezugsgroesse,
   * nicht der erste Eintrag der Liste.
   *
   * Entfernung naeherungsweise in der Ebene, mit Breitenkorrektur auf die
   * Laengengrade. Fuer eine Reihenfolge genuegt das; eine Grosskreisrechnung
   * wuerde an keiner Stelle zu einer anderen Wahl fuehren. */
  function markNearestCity() {
    if (typeof _cities === "undefined" || !fire) return;
    var naechste = null;
    var kuerzeste = Infinity;
    var kos = Math.cos((fire.center[0] * Math.PI) / 180);
    _cities.forEach(function (city) {
      var dLat = city.center[0] - fire.center[0];
      var dLng = (city.center[1] - fire.center[1]) * kos;
      var d = dLat * dLat + dLng * dLng;
      if (d < kuerzeste) {
        kuerzeste = d;
        naechste = city.slug;
      }
    });
    $("#map-compare a").removeClass("nearest").removeAttr("title");
    if (naechste) {
      $('#map-compare a[data-city="' + naechste + '"]')
        .addClass("nearest")
        .attr("title", text.nearest);
    }
  }

  function buildFireButtons() {
    var list = $("#map-fires ul").empty();
    _fires.forEach(function (item) {
      $("<li>")
        .append(
          $("<a>")
            .attr({ href: "javascript:;", "data-fire": item.slug })
            .text(item.name[lang] || item.name.de),
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

  buildFireButtons();
  buildCityButtons();
  buildPickers();
  fillInfoFigures();
  updateScrollHints();

  if (window.top !== window) $("html").addClass("in-frame");

  /* Anker der Form #brand oder #brand/stadt */
  function parseHash() {
    var parts = window.location.hash.replace("#", "").split("/");
    return { fire: parts[0] || _fires[0].slug, city: parts[1] || null };
  }

  var start = parseHash();
  selectFire(start.fire, start.city);

  $(window).on("hashchange", function () {
    var target = parseHash();
    if (!fire) return;
    if (target.fire !== fire.slug) {
      selectFire(target.fire, target.city);
    } else if (target.city !== activeCity) {
      if (target.city) {
        showCity(target.city);
      } else {
        clearCity(true);
      }
    }
  });
});
