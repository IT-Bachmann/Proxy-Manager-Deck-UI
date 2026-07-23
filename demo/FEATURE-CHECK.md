# Funktionsprüfung Demo 2

## Proxy Hosts

| Funktion/Feld | Status |
|---|---|
| Übersicht aller Hosts | vorhanden |
| Host anlegen und bearbeiten | vorhanden |
| Mehrere Ziele pro Host | vorhanden |
| Ziele mit `+` ergänzen | vorhanden |
| Ziele einzeln entfernen | vorhanden |
| IPv4, IPv6 und Hostname wählbar | vorhanden |
| Gewicht pro Ziel | vorhanden |
| Aktiv-, Backup- und Aus-Modus | vorhanden |
| Healthcheck-Pfad pro Ziel | vorhanden |
| Round Robin | vorhanden |
| Least Connections | vorhanden |
| IP-Hash | vorhanden |
| Gewichtete Verteilung | vorhanden |
| Zufällige Verteilung | vorhanden |
| Schema und Port | vorhanden |
| WebSocket | vorhanden |
| Zertifikatsauswahl | vorhanden |
| HTTPS-Weiterleitung | vorhanden |
| Domain- und Adressvalidierung | vorhanden |

## Weitere Bereiche

Zertifikate und Benutzer besitzen eigene Übersichten und Aktionen.
Weiterleitungen, Streams, DNS-Anbieter, Healthchecks, Traffic,
Benachrichtigungen und Protokolle besitzen kontextspezifische Dialoge.
Die Demo speichert Änderungen nur im Arbeitsspeicher; echte Datenbank-,
Nginx- und ACME-Aktionen liegen im Docker-Hauptprojekt.
