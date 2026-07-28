/*
 * polymorph - weiches Ueberblenden zweier Polygonumrisse.
 *
 * Unveraendert uebernommen aus der Fassung von 2013 (vormals in fire.js),
 * lediglich in eine eigene Datei ausgelagert und die Hilfsfunktion distance
 * nach innen gezogen, damit sie nicht mehr im globalen Namensraum liegt.
 *
 * Arbeitsweise: Beide Ringe werden zunaechst auf ein Gitter reduziert und so
 * rotiert, dass die beiden aehnlichsten Punkte am Anfang stehen. Danach paart
 * ein Dynamic-Programming-Lauf die Punkte beider Ringe so, dass die Summe der
 * Abstaende minimal wird. Zwischen den gepaarten Punkten wird linear
 * interpoliert. Der Aufwand waechst mit dem Produkt beider Punktzahlen -
 * deshalb deckelt die Datenpipeline die Stuetzpunkte je Umriss.
 */

var polymorph = (function () {
  function distance(point1, point2) {
    var dx = point1[0] - point2[0];
    var dy = point1[1] - point2[1];
    return dx * dx + dy * dy;
  }

  return {
    /* linear interpolation */
    betterInterpol: function (p1, p2, a) {
      return a * p2 + (1 - a) * p1;
    },
    /* linear interpolation */
    linterpol: function (ak, av, bk, bv, xk) {
      var xr = (bk - xk) / (bk - ak);
      return xr * av + (1 - xr) * bv;
    },
    cleanUp: function (p) {
      for (var i = 0; i < p.length; i++) {
        p[i][0] = parseFloat(p[i][0]);
        p[i][1] = parseFloat(p[i][1]);
      }
    },
    rotate: function (p1, p2) {
      var best1,
        best2,
        error = 1e10;
      for (var i1 = 0; i1 < p1.length; i1++) {
        for (var i2 = 0; i2 < p2.length; i2++) {
          var d = distance(p1[i1], p2[i2]);
          if (d < error) {
            error = d;
            best1 = i1;
            best2 = i2;
          }
        }
        if (error == 0) break;
      }

      return {
        p1: p1.slice(best1).concat(p1.slice(0, best1)),
        p2: p2.slice(best2).concat(p2.slice(0, best2)),
      };
    },

    reduce: function (p) {
      var cy = 0.01;
      var cx = cy * Math.cos((p[0][1] * 3.14156) / 180);

      var indexes = [];
      for (var i = 0; i < p.length; i++) {
        var xi = Math.round(p[i][0] / cx);
        var yi = Math.round(p[i][1] / cy);
        indexes[i] = xi + "_" + yi;
      }

      var sx = 0;
      var sy = 0;
      var n = 0;
      var lastIndex = "_";
      var np = [];
      for (var i = 0; i < p.length; i++) {
        if (indexes[i] != lastIndex) {
          if (n > 0) {
            np.push([sx / n, sy / n]);
            sx = 0;
            sy = 0;
            n = 0;
          }
          lastIndex = indexes[i];
        }
        sx += p[i][0];
        sy += p[i][1];
        n++;
      }

      np.push([sx / n, sy / n]);

      return np;
    },

    /* double up array elements to average out array lengths */
    resample: function (p1, p2) {
      p1 = polymorph.reduce(p1);
      p2 = polymorph.reduce(p2);

      var temp = polymorph.rotate(p1, p2);

      p1 = temp.p1;
      p2 = temp.p2;

      var max1 = p1.length - 1;
      var max2 = p2.length - 1;

      var a = [];
      for (var i1 = 0; i1 <= max1; i1++) a[i1] = new Array(p2.length);

      for (var i1 = 0; i1 <= max1; i1++) {
        for (var i2 = 0; i2 <= max2; i2++) {
          var minSum;
          if (i1 == 0) {
            if (i2 == 0) {
              minSum = 0;
            } else {
              minSum = a[i1][i2 - 1];
            }
          } else {
            if (i2 == 0) {
              minSum = a[i1 - 1][i2];
            } else {
              minSum = Math.min(
                a[i1 - 1][i2],
                a[i1 - 1][i2 - 1],
                a[i1][i2 - 1],
              );
            }
          }

          var d = Math.pow(distance(p1[i1], p2[i2]), 0.3) + 1e-6;

          a[i1][i2] = minSum + d;
        }
      }

      var newp1 = [],
        newp2 = [];
      var i1 = max1,
        i2 = max2;
      var minSum;
      while (i1 > 0 || i2 > 0) {
        newp1.push(p1[i1]);
        newp2.push(p2[i2]);

        if (i1 == 0) {
          if (i2 == 0) {
            minSum = 0; // shouldn't happend
          } else {
            i2--;
          }
        } else {
          if (i2 == 0) {
            i1--;
          } else {
            var new1 = i1,
              new2 = i2;
            minSum = a[i1][i2];
            if (minSum > a[i1 - 1][i2 - 1]) {
              minSum = a[i1 - 1][i2 - 1];
              new1 = i1 - 1;
              new2 = i2 - 1;
            }
            if (minSum > a[i1 - 1][i2]) {
              minSum = a[i1 - 1][i2];
              new1 = i1 - 1;
              new2 = i2;
            }
            if (minSum > a[i1][i2 - 1]) {
              minSum = a[i1][i2 - 1];
              new1 = i1;
              new2 = i2 - 1;
            }
            i1 = new1;
            i2 = new2;
          }
        }
      }
      newp1.push(p1[0]);
      newp2.push(p2[0]);

      return { p1: newp1, p2: newp2 };
    },
    /* calculate morphing steps */
    steps: function (p1, p2, steps) {
      var animation = [];

      polymorph.cleanUp(p1);
      polymorph.cleanUp(p2);

      /* check for polygon sizes and resample if nessecary */
      var temp = polymorph.resample(p1, p2);
      p1 = temp.p1;
      p2 = temp.p2;

      /* return first polygon */
      animation.push(p1);

      /* calculate interpolated polygons */
      var pi = [];
      for (var i = 1; i < steps; i++) {
        var a = i / steps;
        pi = [];
        for (var j = 0; j < p1.length; j++) {
          pi.push([
            polymorph.betterInterpol(p1[j][0], p2[j][0], a),
            polymorph.betterInterpol(p1[j][1], p2[j][1], a),
          ]);
        }
        animation.push(pi);
      }

      /* return final polygon */
      animation.push(p2);

      return animation;
    },

    /* execute polymorphing animation */
    run: function (p1, p2, steps, duration, callback) {
      var interval = Math.round(duration / steps);
      var animation = polymorph.steps(p1, p2, steps);
      var timer = setInterval(function () {
        callback(animation.length === 1, animation.shift());
        if (animation.length === 0) clearInterval(timer);
      }, interval);
      return timer;
    },
  };
})();
