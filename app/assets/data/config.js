/*
 * Voreinstellung der Anwendung. Von Hand pflegbar — im Unterschied zu fires.js
 * und cities.js, die aus der Pipeline kommen und nicht bearbeitet werden dürfen.
 *
 * `nur` schränkt ein, welche Brände gezeigt werden. Leer heißt: alle. Die Angabe
 * in der Adresse (?nur=gironde,artana) hat Vorrang — so kann eine Redaktion je
 * Einbettung eine andere Auswahl festlegen, ohne dass hier etwas geändert wird.
 * Diese Datei setzt nur, was gilt, wenn in der Adresse nichts steht.
 *
 * Unbekannte Kürzel werden übergangen, nicht als Fehler behandelt: eine
 * Einbettung, die auf einen später entfernten Brand zeigt, soll weiter
 * funktionieren und nicht leer bleiben.
 *
 * Kürzel: die Werte des Feldes `slug` in assets/data/fires.js.
 */
var _config = {
  nur: [],
};
