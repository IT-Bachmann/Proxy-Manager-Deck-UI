# Proxy Manager Deck · Demo 2

Diese getrennte HTML-Demo zeigt die überarbeitete Oberfläche. Sie verändert
weder die bestehende Demo noch die Docker-Anwendung. Zum Testen `index.html`
direkt im Browser öffnen. Die Daten bleiben als Beispieldaten im Browser.

## Proxy Hosts

Ein Proxy Host kann beliebig viele Upstream-Ziele enthalten. Über
`+ Ziel hinzufügen` wird eine neue, separat bearbeitbare Zeile ergänzt.

Felder je Proxy Host:

- Domainname, Schema und Weiterleitungs-Port
- Load Balancing: Round Robin, wenigste Verbindungen, IP-Hash,
  gewichtete oder zufällige Verteilung
- auswählbares SSL-Zertifikat
- Aktiv, WebSocket und automatische HTTPS-Weiterleitung

Felder je Ziel:

- Zieladresse
- Typ: IPv4, IPv6 oder Hostname
- Gewicht
- Modus: Aktiv, Backup oder Deaktiviert
- eigener Healthcheck-Pfad

Die Demo prüft Domain und Zieladresse passend zum gewählten Adresstyp.

Über die Größenwahl oben rechts lässt sich die komplette Oberfläche dauerhaft
auf `0,5×`, `1,0×` oder `1,5×` skalieren. Die Einstellung gilt auch für
Navigation, Tabellen, Dialoge und die mobile Ansicht.

## Start

Es ist kein Build-Schritt notwendig. `index.html` direkt öffnen oder den
Ordner mit einem beliebigen statischen Webserver bereitstellen.

## English

ProxyManagerDeck2 is a standalone responsive interface prototype for
Proxy Manager Deck. A proxy host can contain any number of IPv4, IPv6, or
hostname upstream targets. Each target has its own weight, operating mode,
and health-check path. The editor supports Round Robin, Least Connections,
IP Hash, weighted distribution, and random distribution.

No build step is required. Open `index.html` directly or serve the directory
with any static web server.

## License

MIT
