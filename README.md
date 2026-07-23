# ProxyManagerDeck2

ProxyManagerDeck2 enthält den vollständigen Docker-Stack des stabilen
ProxyManagerDeck und zusätzlich die neu entwickelte, responsive
Benutzeroberfläche als interaktive Demo unter `demo/`. Die Demo unterstützt
Mehrziel-Proxy-Hosts, anpassbare Farben, vollständige Farbtönung, Logo,
Favicon sowie getrennte Schriftgröße und Oberflächenskalierung.

Eine responsive, selbst gehostete Reverse-Proxy-Verwaltung für Nginx mit mehreren IPv4-, IPv6- und Hostname-Upstreams pro Domain.

A responsive, self-hosted Nginx reverse-proxy manager supporting multiple IPv4, IPv6, and hostname upstreams per domain.

[Deutsch](#deutsch) · [English](#english)

> ProxyManagerDeck2 befindet sich in aktiver Entwicklung. Vor einem öffentlichen Produktionseinsatz sind HTTPS für das Dashboard, Firewall-Regeln und regelmäßige Volume-Backups erforderlich.

---

## Deutsch

### Überblick

ProxyManagerDeck2 verwaltet Reverse Proxies, Weiterleitungen, TCP-/UDP-Streams, Zertifikate und Healthchecks über eine eigene Weboberfläche. Die Anwendung verwendet SQLite für persistente Daten und erzeugt reale Nginx-Konfigurationen. Änderungen werden atomar geschrieben, mit `nginx -t` geprüft und anschließend ohne vollständigen Gateway-Neustart geladen.

Ein Proxy Host kann mehrere gemischte Ziele besitzen, beispielsweise eine interne IPv4-Adresse und eine öffentliche IPv6-Adresse. Damit wird eine Domain nur einmal angelegt und trotzdem auf mehrere Ziele verteilt.

### Funktionen

- mehrere IPv4-, IPv6- und Hostname-Upstreams pro Domain
- Round Robin, Least Connections, IP Hash, Gewichtung und Backup-Ziele
- reale HTTP(S)-Healthchecks mit Latenz und Erreichbarkeitsstatus
- echte Nginx-Aktivierung mit validiertem Auto-Reload
- automatische HTTP-zu-HTTPS-Weiterleitung bei aktiviertem SSL
- Let's Encrypt über ACME HTTP-01 und DNS-01
- Multi-Domain-/SAN- und Wildcard-Zertifikate
- eigene Zertifikatsseite mit Einzelstatus, ZIP-Download und sicherem Löschen
- DNS-Anbieter: Cloudflare, DigitalOcean, AWS Route 53, IONOS, Hetzner DNS, IPv64.net, STRATO und PowerDNS
- HTTP-Weiterleitungen und TCP-/UDP-Streams
- Benutzerverwaltung mit Rollen `admin`, `operator` und `viewer`
- eigene Benutzerseite mit Bearbeiten, Aktivieren/Deaktivieren, Passwortwechsel und geschütztem Löschen
- PBKDF2-SHA256-Passwort-Hashes, HttpOnly-Sitzungen und CSRF-Schutz
- automatische Abmeldung nach zehn Minuten ohne Benutzeraktivität
- verschlüsselte API-Schlüssel in SQLite; Änderungen erst nach erneuter Passworteingabe
- Benachrichtigungen über SMTP/E-Mail, Telegram und WhatsApp Cloud API
- Traffic-, Treffer-, Latenz- und Fehlerauswertung aus echten Nginx-Logs
- Audit-Log und Systemprotokoll
- anpassbare Farben, Hintergrund, Logo und Favicon bis jeweils 2 MB
- Deutsch und Englisch sowie UI-Skalierung
- responsive Desktop-, Tablet- und Mobilansicht
- integrierte Updateprüfung mit Status, Timeout und Updater-Heartbeat
- separate interaktive Demo
- Docker-Unterstützung für AMD64, ARM64 und eingeschränkt ARMv7

### Schnellinstallation

```bash
git clone https://github.com/IT-Bachmann/ProxyManagerDeck2.git
cd ProxyManagerDeck2
chmod +x install.sh
sudo ./install.sh
```

Das Installationsskript erkennt Linux, Architektur, LXC, freien Speicher, Portkonflikte, Docker und Docker Compose. Fehlende Docker-Pakete werden auf unterstützten Distributionen installiert.

Alternativ:

```bash
cp .env.example .env
nano .env
docker compose up -d --build
```

In `.env` müssen mindestens gesetzt werden:

```env
PROXYDECK_ADMIN_USER=admin
PROXYDECK_ADMIN_PASSWORD=ein-zufälliges-passwort-mit-mindestens-16-zeichen
PROXYDECK_SECRET_KEY=ein-gültiger-fernet-schlüssel
```

Einen Fernet-Schlüssel erzeugen:

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Aufruf und Ports

| Dienst | Port | Beschreibung |
|---|---:|---|
| Dashboard | `8181` | Verwaltungsoberfläche, standardmäßig nur an `127.0.0.1` gebunden |
| Demo | `45130` | Öffentliche interaktive Demo |
| HTTP | `80` | Proxy und ACME HTTP-01 |
| HTTPS | `443` | TLS-Reverse-Proxy |
| Stream-Beispiel | `9000/tcp`, `9000/udp` | Beispiel; weitere Ports in `compose.yml` veröffentlichen |

Dashboard lokal:

```text
http://127.0.0.1:8181
```

Dashboard auf einem entfernten Server sicher über SSH öffnen:

```bash
ssh -L 8181:127.0.0.1:8181 user@server
```

Danach lokal `http://127.0.0.1:8181` öffnen.

Demo:

```text
http://SERVER-IP:45130
```

Demo-Zugang: `admin` / `proxydeck-demo`. Demo-Änderungen bleiben ausschließlich im lokalen Browser.

### Zertifikate

Für HTTP-01 müssen A- und/oder AAAA-Record auf das ProxyManagerDeck2-Gateway zeigen und Port 80 von außen erreichbar sein. Wildcards wie `*.example.com` benötigen DNS-01 und ein konfiguriertes DNS-Plugin. Ein Zertifikat wird zunächst bewusst in der Zertifikatsverwaltung angefordert und anschließend dem Proxy Host zugewiesen. Bereits ausgestellte Zertifikate werden automatisch erneuert.

### Updates

ProxyManagerDeck2 prüft standardmäßig alle sechs Stunden sowie manuell über die Oberfläche auf neue Commits. Der Updater besitzt einen Heartbeat und beendet festhängende Git-Abfragen per Timeout. Er erstellt sich während eines Updates nicht mehr selbst neu, sondern lädt sein aktualisiertes Skript ohne Unterbrechung.

Manuelles Update:

```bash
git pull --ff-only
docker compose up -d --build
```

Status prüfen:

```bash
docker compose ps
docker compose logs --tail=100 control gateway updater
```

Nach der Umstellung von einer älteren Testversion muss der Updater einmal manuell neu erstellt werden, damit nicht mehr der frühere selbstlöschende Prozess läuft: `docker compose up -d --build --force-recreate updater`.

### Proxmox LXC

Auf dem Proxmox-Host müssen für den LXC normalerweise Nesting und Keyctl aktiviert werden:

```bash
pct set CTID -features nesting=1,keyctl=1
```

Danach den Container neu starten. Docker-IPv6 benötigt außerdem aktiviertes IPv6 im LXC. Bei überlappenden Docker-Netzen die bestehenden Netze mit `docker network ls` und `docker network inspect` prüfen und in `compose.yml` ein freies Subnetz wählen.

### Daten und Sicherheit

Persistente Daten liegen in Docker-Volumes für SQLite, Zertifikate, generierte Konfigurationen, Logs und Updatezustand. Vor Updates oder Änderungen an Volumes sollte ein Backup erstellt werden. `PROXYDECK_SECURE_COOKIE=1` darf erst gesetzt werden, wenn das Dashboard ausschließlich über HTTPS erreichbar ist.

---

## English

### Overview

ProxyManagerDeck2 manages reverse proxies, redirects, TCP/UDP streams, certificates, and health checks through a dedicated web interface. It stores persistent state in SQLite and generates real Nginx configuration. Changes are written atomically, validated with `nginx -t`, and reloaded without restarting the entire gateway.

A proxy host may contain multiple mixed targets, such as an internal IPv4 address and a public IPv6 address. The domain is created once and traffic can still be distributed across several destinations.

### Features

- multiple IPv4, IPv6, and hostname upstreams per domain
- round robin, least connections, IP hash, weights, and backup targets
- real HTTP(S) health checks with latency and availability status
- real Nginx activation with validated automatic reloads
- automatic HTTP-to-HTTPS redirects when SSL is enabled
- Let's Encrypt using ACME HTTP-01 and DNS-01
- multi-domain/SAN and wildcard certificates
- dedicated certificate page with per-certificate status, ZIP download, and safe deletion
- DNS providers: Cloudflare, DigitalOcean, AWS Route 53, IONOS, Hetzner DNS, IPv64.net, STRATO, and PowerDNS
- HTTP redirects and TCP/UDP streams
- user management with `admin`, `operator`, and `viewer` roles
- dedicated user page for editing, enabling/disabling, password changes, and protected deletion
- PBKDF2-SHA256 password hashes, HttpOnly sessions, and CSRF protection
- automatic sign-out after ten minutes without user activity
- encrypted API secrets in SQLite; changing secrets requires password confirmation
- SMTP/email, Telegram, and WhatsApp Cloud API notifications
- traffic, request, latency, and error analytics from real Nginx logs
- audit log and system log
- customizable colors, background, logo, and favicon up to 2 MB each
- German and English language support plus interface scaling
- responsive desktop, tablet, and mobile layouts
- integrated update checks with status, timeout, and updater heartbeat
- separate interactive demo
- Docker support for AMD64, ARM64, and limited ARMv7 support

### Quick installation

```bash
git clone https://github.com/IT-Bachmann/ProxyManagerDeck2.git
cd ProxyManagerDeck2
chmod +x install.sh
sudo ./install.sh
```

The installer detects Linux, CPU architecture, LXC, available disk space, port conflicts, Docker, and Docker Compose. It installs missing Docker packages on supported distributions.

Manual installation:

```bash
cp .env.example .env
nano .env
docker compose up -d --build
```

At minimum, configure:

```env
PROXYDECK_ADMIN_USER=admin
PROXYDECK_ADMIN_PASSWORD=a-random-password-with-at-least-16-characters
PROXYDECK_SECRET_KEY=a-valid-fernet-key
```

Generate a Fernet key:

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Access and ports

| Service | Port | Description |
|---|---:|---|
| Dashboard | `8181` | Management interface, bound to `127.0.0.1` by default |
| Demo | `45130` | Public interactive demo |
| HTTP | `80` | Proxy and ACME HTTP-01 |
| HTTPS | `443` | TLS reverse proxy |
| Stream example | `9000/tcp`, `9000/udp` | Example only; publish additional ports in `compose.yml` |

For a remote server, use an SSH tunnel:

```bash
ssh -L 8181:127.0.0.1:8181 user@server
```

Then open `http://127.0.0.1:8181` locally. The demo is available at `http://SERVER-IP:45130` using `admin` / `proxydeck-demo`.

### Certificates

For HTTP-01, the domain's A and/or AAAA records must point to the ProxyManagerDeck2 gateway and port 80 must be publicly reachable. Wildcards such as `*.example.com` require DNS-01 and a configured DNS plugin. Certificates are deliberately requested from the certificate manager and then assigned to a proxy host. Issued certificates are renewed automatically.

### Updates

ProxyManagerDeck2 checks for new commits every six hours by default and can also be checked manually from the interface. The updater uses a heartbeat and timeouts for stalled Git operations. It no longer recreates its own container during an update; it reloads the updated script without interruption.

Manual update:

```bash
git pull --ff-only
docker compose up -d --build
```

Check the service status:

```bash
docker compose ps
docker compose logs --tail=100 control gateway updater
```

When upgrading from an older test build, recreate the updater once so the former self-removing process is no longer running: `docker compose up -d --build --force-recreate updater`.

### Proxmox LXC

Nesting and Keyctl normally need to be enabled on the Proxmox host:

```bash
pct set CTID -features nesting=1,keyctl=1
```

Restart the container afterwards. Docker IPv6 also requires IPv6 to be enabled inside the LXC. If Docker reports overlapping networks, inspect existing networks and select an unused subnet in `compose.yml`.

### Data and security

Persistent data is stored in Docker volumes for SQLite, certificates, generated configuration, logs, and updater state. Back up these volumes before upgrades or storage changes. Enable `PROXYDECK_SECURE_COOKIE=1` only when the dashboard is exclusively available through HTTPS.

### Project layout

- `server.py` — API, authentication, SQLite, ACME, health checks, and Nginx generator
- `public/` — management interface
- `gateway/` — Nginx gateway and validated reload watcher
- `updater/` — GitHub and Docker updater
- `demo/` — standalone interactive demo
- `compose.yml` — complete Docker Compose stack
- `install.sh` — Linux installer

### License

See [LICENSE](LICENSE).
