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

  var FRAMES_PER_STEP = 40;
  var STEP_DURATION = 2200;

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
    },
  }[lang];

  function formatTime(millis) {
    return (
      moment.utc(millis).add(TZ_OFFSET_HOURS, "hours").format(text.dateFormat) +
      " " +
      text.tzLabel
    );
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
      attribution:
        'Brandumrisse: <a href="https://mapping.emergency.copernicus.eu/" target="_blank" rel="noopener">Copernicus EMS</a> · ' +
        'Stadtgrenzen: <a href="https://openstreetmap.org" target="_blank" rel="noopener">OpenStreetMap</a> · ' +
        'Relief: <a href="https://www.esri.com/" target="_blank" rel="noopener">Esri</a> · ' +
        'Anwendung <a href="https://github.com/marcomaas/fire" target="_blank" rel="noopener">CC BY</a>, nach einer Arbeit von OpenDataCity (2013)',
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
  var cityStyle = {
    stroke: true,
    color: "#1B3A6B",
    opacity: 1,
    weight: 2,
    fill: true,
    fillColor: "#FFFFFF",
    fillOpacity: 0.35,
  };

  var firePoly = new L.Polygon([], firePolyStyle).addTo(map);
  var otherLayer = new L.LayerGroup().addTo(map);
  var historyLayer = new L.LayerGroup().addTo(map);
  var cityLayer = null;

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

  function clearCity() {
    if (cityLayer) {
      map.removeLayer(cityLayer);
      cityLayer = null;
    }
    activeCity = null;
    $("#map-compare a").removeClass("highlight");
    syncHash();
  }

  function showCity(slug) {
    var city = null;
    for (var i = 0; i < _cities.length; i++) {
      if (_cities[i].slug === slug) city = _cities[i];
    }
    if (!city) return;
    if (cityLayer) map.removeLayer(cityLayer);
    cityLayer = new L.Polygon(
      shiftRings(city.rings, city.center, fire.center),
      cityStyle,
    ).addTo(map);
    cityLayer.on("click", clearCity);
    activeCity = slug;
    $("#map-compare a").removeClass("highlight");
    $('#map-compare a[data-city="' + slug + '"]').addClass("highlight");
    syncHash();
  }

  function buildCityButtons() {
    if (typeof _cities === "undefined") return;
    var list = $("#map-compare ul").empty();
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
    if (slug === activeCity) {
      clearCity();
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
    $("#map-date").text(formatTime(moment.utc(step.acquired).valueOf()));
    $("#map-size").text(text.size(step.size_ha));
  }

  /* Zeit und Flaeche zwischen zwei Aufnahmen fortschreiben. Linear
   * interpoliert und damit eine Darstellungshilfe, keine Messung — was
   * zwischen zwei Satellitenueberfluegen genau geschah, ist nicht bekannt. */
  function updateReadout(from, to, ratio) {
    var t0 = moment.utc(from.acquired).valueOf();
    var t1 = moment.utc(to.acquired).valueOf();
    $("#map-date").text(formatTime(t0 + (t1 - t0) * ratio));
    $("#map-size").text(
      text.size(from.size_ha + (to.size_ha - from.size_ha) * ratio),
    );
  }

  function finish(redrawLast) {
    if (redrawLast) showStep(fire.steps[fire.steps.length - 1]);
    $("#map-throbber-bar").css("width", "100%");
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
    var frames = 0;
    var totalFrames = (fire.steps.length - 1) * FRAMES_PER_STEP;
    var target = firePolyStyle.fillOpacity;

    firePoly.setLatLngs([]);
    otherLayer.clearLayers();
    historyLayer.addLayer(footprintLayer(fire.steps[0], target));

    function fadeStep() {
      var from = fire.steps[index];
      var to = fire.steps[index + 1];
      var incoming = footprintLayer(to, 0);
      historyLayer.addLayer(incoming);

      var frameInStep = 0;
      timer = setInterval(
        function () {
          frameInStep++;
          frames++;

          var ratio = Math.min(1, frameInStep / FRAMES_PER_STEP);
          incoming.eachLayer(function (layer) {
            layer.setStyle({ fillOpacity: target * ratio });
          });

          $("#map-throbber-bar").css(
            "width",
            Math.min(100, (100 * frames) / totalFrames).toFixed(2) + "%",
          );
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
        Math.round(STEP_DURATION / FRAMES_PER_STEP),
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
    var frames = 0;
    var totalFrames = (fire.steps.length - 1) * FRAMES_PER_STEP;

    showStep(fire.steps[0]);

    function morphStep() {
      var from = fire.steps[index];
      var to = fire.steps[index + 1];

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
        FRAMES_PER_STEP,
        STEP_DURATION,
        function (end, ring) {
          if (!ring || !ring.length) return;

          frameInStep++;
          frames++;
          $("#map-throbber-bar").css(
            "width",
            Math.min(100, (100 * frames) / totalFrames).toFixed(2) + "%",
          );

          firePoly.setLatLngs(ring);
          updateReadout(from, to, Math.min(1, frameInStep / FRAMES_PER_STEP));

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
    $("#map-throbber-bar").css("width", "0");
    $("#map-container").removeClass("played");

    $("#fire-name").text(fire.name[lang] || fire.name.de);
    $("#fire-region").text(fire.region[lang] || fire.region.de);
    $("#fire-source").attr("href", fire.source_url).text(fire.activation);
    $("#fire-status").text(fire.closed ? text.contained : text.ongoing);
    $("#fire-steps").text(text.steps(fire.steps.length));
    $("#fire-note").text(fire.steps.length < 2 ? text.single : "");

    $("#map-fires a").removeClass("highlight");
    $('#map-fires a[data-fire="' + fire.slug + '"]').addClass("highlight");

    /* Ausschnitt auf die letzte, groesste Ausdehnung setzen — einschliesslich
     * der Nebenflaechen, die bei zerstreuten Braenden weit ueber die
     * Hauptflaeche hinausreichen. */
    var last = fire.steps[fire.steps.length - 1];
    var bounds = new L.LatLngBounds(last.polygon);
    (last.others || []).forEach(function (ring) {
      bounds.extend(new L.LatLngBounds(ring));
    });
    map.fitBounds(bounds.pad(0.35));

    showStep(fire.steps[0]);
    setButtonState(fire.steps.length < 2 ? "again" : "play");

    if (citySlug) showCity(citySlug);
    syncHash();

    play();
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

  $("#button-info").click(function (evt) {
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
        clearCity();
      }
    }
  });
});
