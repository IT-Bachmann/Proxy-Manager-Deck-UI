import base64
import hashlib
import hmac
import http.cookies
import http.server
import ipaddress
import json
import io
import logging
from logging.handlers import RotatingFileHandler
import os
import re
import secrets
import shutil
import smtplib
import socket
import sqlite3
import ssl
import subprocess
import threading
import time
import urllib.parse
import urllib.request
import urllib.error
import zipfile
from email.message import EmailMessage
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
DATA = Path(os.environ.get("PROXYDECK_DATA", ROOT / "data"))
GENERATED = Path(os.environ.get("PROXYDECK_CONFIG", ROOT / "generated"))
ACME_WEBROOT = Path(os.environ.get("PROXYDECK_ACME_WEBROOT", ROOT / "acme-webroot"))
DB = DATA / "proxydeck.db"
ACCESS_LOG = Path(os.environ.get("PROXYDECK_ACCESS_LOG", "/logs/access.log"))
UPDATE_DIR = Path(os.environ.get("PROXYDECK_UPDATE_DIR", "/updates"))
PORT = int(os.environ.get("PORT", "3000"))
SESSION_TTL = 60 * 10
SESSION_COOKIE_TTL = 60 * 60 * 12
SYSTEM_STARTED = int(time.time())
HOST_RE = re.compile(r"^(?=.{1,253}$)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}$")
MIME = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".svg": "image/svg+xml"}

for directory in (DATA, GENERATED, ACME_WEBROOT):
    directory.mkdir(parents=True, exist_ok=True)
LOGGER = logging.getLogger("proxydeck")
LOGGER.setLevel(logging.INFO)
if not LOGGER.handlers:
    handler = RotatingFileHandler(DATA / "proxydeck.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOGGER.addHandler(handler)


def connect():
    db = sqlite3.connect(DB, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA journal_mode=WAL")
    return db


def password_hash(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return f"pbkdf2_sha256$310000${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def password_ok(password, encoded):
    try:
        _, rounds, salt, expected = encoded.split("$")
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt), int(rounds))
        return hmac.compare_digest(actual, base64.b64decode(expected))
    except (ValueError, TypeError):
        return False


def init_db():
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','operator','viewer')), enabled INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, csrf TEXT NOT NULL, expires_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS proxy_hosts(id INTEGER PRIMARY KEY, domain TEXT UNIQUE NOT NULL, scheme TEXT NOT NULL, port INTEGER NOT NULL, websocket INTEGER NOT NULL DEFAULT 1, strategy TEXT NOT NULL DEFAULT 'least_conn', ssl_enabled INTEGER NOT NULL DEFAULT 0, enabled INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS upstreams(id INTEGER PRIMARY KEY, proxy_id INTEGER NOT NULL REFERENCES proxy_hosts(id) ON DELETE CASCADE, address TEXT NOT NULL, family TEXT NOT NULL, weight INTEGER NOT NULL DEFAULT 100, mode TEXT NOT NULL DEFAULT 'active', health_path TEXT NOT NULL DEFAULT '/', healthy INTEGER, latency_ms INTEGER, checked_at INTEGER);
        CREATE TABLE IF NOT EXISTS redirects(id INTEGER PRIMARY KEY, domain TEXT UNIQUE NOT NULL, target TEXT NOT NULL, code INTEGER NOT NULL DEFAULT 301, enabled INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS streams(id INTEGER PRIMARY KEY, listen_port INTEGER NOT NULL, protocol TEXT NOT NULL, target_host TEXT NOT NULL, target_port INTEGER NOT NULL, enabled INTEGER NOT NULL DEFAULT 1, UNIQUE(listen_port,protocol));
        CREATE TABLE IF NOT EXISTS certificates(id INTEGER PRIMARY KEY, domain TEXT UNIQUE NOT NULL, email TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', expires_at INTEGER, last_error TEXT, created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS acme_providers(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, provider TEXT NOT NULL, secret_data TEXT NOT NULL, created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY, user_id INTEGER, action TEXT NOT NULL, detail TEXT, created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS notification_channels(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, channel_type TEXT NOT NULL CHECK(channel_type IN ('smtp','telegram','whatsapp')), config_data TEXT NOT NULL, events TEXT NOT NULL DEFAULT '["down","up","certificate"]', enabled INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS traffic_hourly(domain TEXT NOT NULL, bucket INTEGER NOT NULL, hits INTEGER NOT NULL DEFAULT 0, bytes INTEGER NOT NULL DEFAULT 0, total_time REAL NOT NULL DEFAULT 0, errors INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(domain,bucket));
        """)
        cert_columns = {row[1] for row in db.execute("PRAGMA table_info(certificates)")}
        if "challenge" not in cert_columns: db.execute("ALTER TABLE certificates ADD COLUMN challenge TEXT NOT NULL DEFAULT 'http-01'")
        if "provider_id" not in cert_columns: db.execute("ALTER TABLE certificates ADD COLUMN provider_id INTEGER REFERENCES acme_providers(id)")
        if "domains_json" not in cert_columns: db.execute("ALTER TABLE certificates ADD COLUMN domains_json TEXT")
        if "cert_name" not in cert_columns: db.execute("ALTER TABLE certificates ADD COLUMN cert_name TEXT")
        proxy_columns = {row[1] for row in db.execute("PRAGMA table_info(proxy_hosts)")}
        if "certificate_id" not in proxy_columns: db.execute("ALTER TABLE proxy_hosts ADD COLUMN certificate_id INTEGER REFERENCES certificates(id)")
        if not db.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            password = os.environ.get("PROXYDECK_ADMIN_PASSWORD")
            if not password or len(password) < 16:
                raise RuntimeError("PROXYDECK_ADMIN_PASSWORD must contain at least 16 characters on first start")
            db.execute("INSERT INTO users(username,password_hash,role,created_at) VALUES(?,?,?,?)", (os.environ.get("PROXYDECK_ADMIN_USER", "admin"), password_hash(password), "admin", int(time.time())))


def rowdict(row):
    return dict(row) if row else None


def secret_box():
    key = os.environ.get("PROXYDECK_SECRET_KEY", "")
    if not key:
        raise RuntimeError("PROXYDECK_SECRET_KEY is required for DNS provider credentials")
    try: return Fernet(key.encode())
    except ValueError as error: raise RuntimeError("PROXYDECK_SECRET_KEY must be a Fernet key") from error


def encrypt_secret(data):
    return secret_box().encrypt(json.dumps(data).encode()).decode()


def decrypt_secret(value):
    try: return json.loads(secret_box().decrypt(value.encode()).decode())
    except InvalidToken as error: raise RuntimeError("DNS provider credentials cannot be decrypted") from error


def send_notification(channel, subject, message):
    config = decrypt_secret(channel["config_data"])
    kind = channel["channel_type"]
    if kind == "smtp":
        mail = EmailMessage(); mail["Subject"] = subject; mail["From"] = config["from_email"]; mail["To"] = config["to_email"]; mail.set_content(message)
        context = ssl.create_default_context()
        if config.get("security", "starttls") == "ssl":
            client = smtplib.SMTP_SSL(config["host"], int(config.get("port", 465)), timeout=15, context=context)
        else:
            client = smtplib.SMTP(config["host"], int(config.get("port", 587)), timeout=15)
            if config.get("security", "starttls") == "starttls": client.starttls(context=context)
        try:
            if config.get("username"): client.login(config["username"], config.get("password", ""))
            client.send_message(mail)
        finally: client.quit()
    elif kind == "telegram":
        url = f"https://api.telegram.org/bot{config['bot_token']}/sendMessage"
        payload = json.dumps({"chat_id": config["chat_id"], "text": f"{subject}\n\n{message}", "disable_web_page_preview": True}).encode()
        with urllib.request.urlopen(urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}), timeout=15) as response:
            if response.status >= 300: raise RuntimeError(f"Telegram returned HTTP {response.status}")
    else:
        version = config.get("api_version", "v23.0")
        url = f"https://graph.facebook.com/{version}/{config['phone_number_id']}/messages"
        payload = json.dumps({"messaging_product": "whatsapp", "to": config["recipient"], "type": "text", "text": {"body": f"{subject}\n\n{message}"}}).encode()
        request = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {config['access_token']}"})
        with urllib.request.urlopen(request, timeout=15) as response:
            if response.status >= 300: raise RuntimeError(f"WhatsApp returned HTTP {response.status}")


def dispatch_notification(event, subject, message):
    with connect() as db: channels = db.execute("SELECT * FROM notification_channels WHERE enabled=1").fetchall()
    for channel in channels:
        if event not in json.loads(channel["events"]): continue
        def deliver(item=channel):
            try: send_notification(item, subject, message)
            except Exception as error: print(f"notification {item['name']}:", error)
        threading.Thread(target=deliver, daemon=True).start()


def valid_address(address, family):
    if family in ("IPv4", "IPv6"):
        try:
            return ipaddress.ip_address(address).version == (4 if family == "IPv4" else 6)
        except ValueError:
            return False
    return bool(re.match(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,252}$", address))


def nginx_name(domain):
    return "relay_" + re.sub(r"[^a-zA-Z0-9]", "_", domain)


def generate_nginx():
    with connect() as db:
        proxies = db.execute("SELECT * FROM proxy_hosts WHERE enabled=1 ORDER BY domain").fetchall()
        redirects = db.execute("SELECT * FROM redirects WHERE enabled=1 ORDER BY domain").fetchall()
        streams = db.execute("SELECT * FROM streams WHERE enabled=1 ORDER BY listen_port").fetchall()
        http_parts = ["# Generated by ProxyManagerDeck2. Do not edit.\n"]
        for proxy in proxies:
            targets = db.execute("SELECT * FROM upstreams WHERE proxy_id=? AND mode!='off' ORDER BY id", (proxy["id"],)).fetchall()
            if not targets:
                continue
            name = nginx_name(proxy["domain"])
            balance = "" if proxy["strategy"] == "round_robin" else f"    {proxy['strategy']};\n"
            servers = []
            for target in targets:
                host = f"[{target['address']}]" if target["family"] == "IPv6" else target["address"]
                backup = " backup" if target["mode"] == "backup" else ""
                servers.append(f"    server {host}:{proxy['port']} weight={target['weight']}{backup} max_fails=3 fail_timeout=30s;")
            http_parts.append(f"upstream {name} {{\n{balance}{chr(10).join(servers)}\n    keepalive 32;\n}}\n")
            ssl = bool(proxy["ssl_enabled"])
            listen = "    listen 443 ssl;\n    listen [::]:443 ssl;" if ssl else "    listen 80;\n    listen [::]:80;"
            cert_domain = proxy["domain"]
            if ssl and proxy["certificate_id"]:
                selected_cert = db.execute("SELECT domain,cert_name FROM certificates WHERE id=? AND status='issued'", (proxy["certificate_id"],)).fetchone()
                if selected_cert: cert_domain = selected_cert["cert_name"] or selected_cert["domain"]
            cert = f"\n    ssl_certificate /etc/letsencrypt/live/{cert_domain}/fullchain.pem;\n    ssl_certificate_key /etc/letsencrypt/live/{cert_domain}/privkey.pem;" if ssl else ""
            websocket = "\n        proxy_set_header Upgrade $http_upgrade;\n        proxy_set_header Connection $connection_upgrade;" if proxy["websocket"] else ""
            http_parts.append(f"""server {{
{listen}{cert}
    server_name {proxy['domain']};
    location ^~ /.well-known/acme-challenge/ {{ root /var/www/acme; }}
    location / {{
        proxy_pass {proxy['scheme']}://{name};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;{websocket}
    }}
}}
""")
            if ssl:
                http_parts.append(f"""server {{
    listen 80;
    listen [::]:80;
    server_name {proxy['domain']};
    location ^~ /.well-known/acme-challenge/ {{ root /var/www/acme; }}
    location / {{ return 308 https://$host$request_uri; }}
}}
""")
        for redirect in redirects:
            http_parts.append(f"server {{ listen 80; listen [::]:80; server_name {redirect['domain']}; return {redirect['code']} {redirect['target']}$request_uri; }}\n")
        stream_parts = ["# Generated stream routes\n"]
        for stream in streams:
            udp = " udp" if stream["protocol"] == "udp" else ""
            stream_parts.append(f"server {{ listen {stream['listen_port']}{udp}; listen [::]:{stream['listen_port']}{udp}; proxy_pass {stream['target_host']}:{stream['target_port']}; }}\n")
    for filename, content in (("proxydeck-http.conf", "\n".join(http_parts)), ("proxydeck-stream.conf", "\n".join(stream_parts))):
        temp = GENERATED / (filename + ".tmp")
        temp.write_text(content, encoding="utf-8")
        os.replace(temp, GENERATED / filename)


def health_loop():
    while True:
        try:
            changes = []
            with connect() as db:
                targets = db.execute("SELECT u.*,p.scheme,p.port FROM upstreams u JOIN proxy_hosts p ON p.id=u.proxy_id WHERE p.enabled=1 AND u.mode!='off'").fetchall()
                for target in targets:
                    started = time.monotonic()
                    healthy = 0
                    try:
                        host = f"[{target['address']}]" if target["family"] == "IPv6" else target["address"]
                        url = f"{target['scheme']}://{host}:{target['port']}{target['health_path']}"
                        req = urllib.request.Request(url, method="GET", headers={"User-Agent": "ProxyManagerDeck2-Health/1.0"})
                        with urllib.request.urlopen(req, timeout=4) as response:
                            healthy = 1 if response.status < 500 else 0
                    except urllib.error.HTTPError as error:
                        healthy = 1 if error.code < 500 else 0
                    except Exception:
                        healthy = 0
                    latency = int((time.monotonic() - started) * 1000)
                    db.execute("UPDATE upstreams SET healthy=?,latency_ms=?,checked_at=? WHERE id=?", (healthy, latency, int(time.time()), target["id"]))
                    if target["healthy"] is not None and int(target["healthy"]) != healthy:
                        changes.append(("up" if healthy else "down", target["address"], latency))
                        LOGGER.warning("health state=%s target=%s latency_ms=%s", "up" if healthy else "down", target["address"], latency)
                db.commit()
            for event, address, latency in changes:
                state = "wieder erreichbar" if event == "up" else "nicht erreichbar"
                dispatch_notification(event, f"ProxyManagerDeck2: Upstream {state}", f"Ziel: {address}\nStatus: {state}\nLatenz: {latency} ms")
        except Exception as error:
            print("healthcheck:", error)
        time.sleep(30)


def renewal_loop():
    while True:
        time.sleep(12 * 60 * 60)
        try:
            result = subprocess.run(["certbot", "renew", "--non-interactive", "--quiet"], capture_output=True, text=True, timeout=600)
            acme_result = subprocess.run(["/opt/acme.sh-3.1.2/acme.sh", "--home", "/data/acme-sh", "--cron"], capture_output=True, text=True, timeout=600)
            if result.returncode == 0 and acme_result.returncode == 0:
                generate_nginx()  # atomic rewrite triggers the gateway's validated reload
            else:
                print("acme renewal:", ((result.stderr or result.stdout) + (acme_result.stderr or acme_result.stdout))[-1000:])
        except Exception as error:
            print("acme renewal:", error)


def traffic_loop():
    """Incrementally aggregate the shared Nginx JSON access log into hourly SQLite rows."""
    while True:
        try:
            if not ACCESS_LOG.exists(): time.sleep(5); continue
            with connect() as db:
                saved = db.execute("SELECT value FROM settings WHERE key='traffic_offset'").fetchone()
                offset = int(saved["value"]) if saved else 0
            size = ACCESS_LOG.stat().st_size
            if offset > size: offset = 0
            rows = {}
            with ACCESS_LOG.open("r", encoding="utf-8", errors="replace") as handle:
                handle.seek(offset)
                for line in handle:
                    try:
                        item = json.loads(line); domain = str(item.get("host", "unknown"))[:253]
                        timestamp = int(float(item.get("ts", time.time()))); bucket = timestamp - timestamp % 3600
                        key = (domain, bucket); current = rows.setdefault(key, [0, 0, 0.0, 0]); current[0] += 1
                        current[1] += max(0, int(item.get("bytes", 0))); current[2] += max(0.0, float(item.get("time", 0)))
                        current[3] += int(int(item.get("status", 0)) >= 400)
                    except (ValueError, TypeError, json.JSONDecodeError): pass
                offset = handle.tell()
            with connect() as db:
                for (domain, bucket), values in rows.items():
                    db.execute("INSERT INTO traffic_hourly(domain,bucket,hits,bytes,total_time,errors) VALUES(?,?,?,?,?,?) ON CONFLICT(domain,bucket) DO UPDATE SET hits=hits+excluded.hits,bytes=bytes+excluded.bytes,total_time=total_time+excluded.total_time,errors=errors+excluded.errors", (domain, bucket, *values))
                db.execute("INSERT INTO settings(key,value) VALUES('traffic_offset',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(offset),))
                db.execute("DELETE FROM traffic_hourly WHERE bucket<?", (int(time.time()) - 90 * 86400,))
        except Exception as error: print("traffic:", error)
        time.sleep(5)


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "ProxyManagerDeck2/0.2"

    def json_body(self):
        length = int(self.headers.get("content-length", "0"))
        # Two 2 MiB images need roughly 5.6 MiB after Base64 encoding.
        if length > 6 * 1024 * 1024:
            raise ValueError("body too large")
        return json.loads(self.rfile.read(length) or b"{}")

    def send_json(self, status, payload, headers=None):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        for key, value in (headers or {}).items(): self.send_header(key, value)
        self.end_headers(); self.wfile.write(body)

    def session(self):
        cookie = http.cookies.SimpleCookie(self.headers.get("cookie"))
        token = cookie.get("proxydeck_session")
        if not token: return None
        token_hash = hashlib.sha256(token.value.encode()).hexdigest()
        with connect() as db:
            row = db.execute("SELECT s.csrf,s.expires_at,u.id,u.username,u.role,u.enabled FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=?", (token_hash,)).fetchone()
        if not row or not row["enabled"] or row["expires_at"] < time.time(): return None
        return rowdict(row)

    def require(self, roles=("admin", "operator", "viewer"), csrf=False):
        session = self.session()
        if not session or session["role"] not in roles:
            self.send_json(401 if not session else 403, {"error": "Nicht autorisiert"}); return None
        if csrf and not hmac.compare_digest(self.headers.get("x-csrf-token", ""), session["csrf"]):
            self.send_json(403, {"error": "Ungültiges CSRF-Token"}); return None
        return session

    def audit(self, user_id, action, detail=""):
        with connect() as db: db.execute("INSERT INTO audit_log(user_id,action,detail,created_at) VALUES(?,?,?,?)", (user_id, action, detail[:1000], int(time.time())))

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/branding":
            with connect() as db: settings = {row["key"]: row["value"] for row in db.execute("SELECT key,value FROM settings WHERE key IN ('accent','background','logo','favicon','gateway_ipv4','gateway_ipv6','ui_scale')")}
            self.send_json(200, {"accent": settings.get("accent", "#16966a"), "background": settings.get("background", "#f3f6f4"), "logo": settings.get("logo", ""), "favicon": settings.get("favicon", ""), "gateway_ipv4": settings.get("gateway_ipv4", ""), "gateway_ipv6": settings.get("gateway_ipv6", ""), "ui_scale": settings.get("ui_scale", "1")}); return
        if path == "/api/session":
            session = self.require()
            if session: self.send_json(200, {"user": {"id": session["id"], "username": session["username"], "role": session["role"]}, "csrf": session["csrf"]})
            return
        if path == "/api/logs":
            session = self.require(("admin",))
            if not session: return
            try: lines = (DATA / "proxydeck.log").read_text(encoding="utf-8", errors="replace").splitlines()[-500:]
            except OSError: lines = []
            self.send_json(200, {"items": lines}); return
        if path == "/api/update/status":
            session = self.require(("admin",))
            if not session: return
            try: status = (UPDATE_DIR / "status").read_text(encoding="utf-8").strip()
            except OSError: status = "idle"
            if status == "checking":
                started = 0
                for marker in ("check_started", "check"):
                    try: started = max(started, int((UPDATE_DIR / marker).read_text(encoding="utf-8").strip() or 0))
                    except (OSError, ValueError): pass
                if started and int(time.time()) - started > 120:
                    status = "check_failed"
                    try: (UPDATE_DIR / "status").write_text(status, encoding="utf-8")
                    except OSError: pass
                    LOGGER.warning("update check timed out after 120 seconds")
            try: update_log = (UPDATE_DIR / "update.log").read_text(encoding="utf-8", errors="replace").splitlines()[-120:]
            except OSError: update_log = []
            def update_value(name, default=""):
                try: return (UPDATE_DIR / name).read_text(encoding="utf-8").strip()
                except OSError: return default
            self.send_json(200, {"status": status, "log": update_log, "last_checked": int(update_value("last_checked", "0") or 0), "local_commit": update_value("local_commit")[:12], "remote_commit": update_value("remote_commit")[:12]}); return
        if path == "/api/system/status":
            if not self.require(): return
            try: update_status = (UPDATE_DIR / "status").read_text(encoding="utf-8").strip()
            except OSError: update_status = "idle"
            with connect() as db:
                hosts = db.execute("SELECT COUNT(*) FROM proxy_hosts").fetchone()[0]
                active_hosts = db.execute("SELECT COUNT(*) FROM proxy_hosts WHERE enabled=1").fetchone()[0]
                targets = db.execute("SELECT COUNT(*) total,SUM(CASE WHEN healthy=1 THEN 1 ELSE 0 END) healthy FROM upstreams").fetchone()
                certificates = db.execute("SELECT COUNT(*) total,SUM(CASE WHEN status='issued' THEN 1 ELSE 0 END) issued FROM certificates").fetchone()
            self.send_json(200, {"control": "online", "uptime_seconds": int(time.time()) - SYSTEM_STARTED, "update_status": update_status, "hosts": hosts, "active_hosts": active_hosts, "targets": {"total": targets["total"] or 0, "healthy": targets["healthy"] or 0}, "certificates": {"total": certificates["total"] or 0, "issued": certificates["issued"] or 0}}); return
        if path == "/api/proxy-hosts":
            if not self.require(): return
            with connect() as db:
                items = []
                for row in db.execute("SELECT * FROM proxy_hosts ORDER BY domain"):
                    item = rowdict(row); item["targets"] = [rowdict(x) for x in db.execute("SELECT * FROM upstreams WHERE proxy_id=? ORDER BY id", (row["id"],))]; items.append(item)
            self.send_json(200, {"items": items}); return
        certificate_download = re.fullmatch(r"/api/certificates/(\d+)/download", path)
        if certificate_download:
            if not self.require(("admin",)): return
            certificate_id = int(certificate_download.group(1))
            with connect() as db: certificate = db.execute("SELECT * FROM certificates WHERE id=? AND status='issued'", (certificate_id,)).fetchone()
            if not certificate: self.send_json(404, {"error": "Ausgestelltes Zertifikat nicht gefunden"}); return
            cert_name = certificate["cert_name"] or certificate["domain"]
            cert_dir = Path("/etc/letsencrypt/live") / cert_name
            files = [(name, cert_dir / name) for name in ("cert.pem", "chain.pem", "fullchain.pem", "privkey.pem")]
            if not all(file.is_file() for _, file in files): self.send_json(404, {"error": "Zertifikatsdateien sind nicht vollständig vorhanden"}); return
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                for name, file in files: archive.writestr(name, file.read_bytes())
            data = buffer.getvalue(); safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", cert_name)
            self.send_response(200); self.send_header("Content-Type", "application/zip"); self.send_header("Content-Disposition", f'attachment; filename="{safe_name}-certificate.zip"'); self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(data); return
        if path == "/api/traffic":
            if not self.require(): return
            try: hours = max(1, min(2160, int(urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("hours", [24])[0])))
            except ValueError: hours = 24
            since = int(time.time()) - hours * 3600
            with connect() as db:
                timeline = [rowdict(row) for row in db.execute("SELECT bucket,SUM(hits) hits,SUM(bytes) bytes,SUM(total_time) total_time,SUM(errors) errors FROM traffic_hourly WHERE bucket>=? GROUP BY bucket ORDER BY bucket", (since,))]
                hosts = [rowdict(row) for row in db.execute("SELECT domain,SUM(hits) hits,SUM(bytes) bytes,SUM(total_time) total_time,SUM(errors) errors FROM traffic_hourly WHERE bucket>=? GROUP BY domain ORDER BY hits DESC", (since,))]
            totals = {"hits": sum(x["hits"] for x in timeline), "bytes": sum(x["bytes"] for x in timeline), "errors": sum(x["errors"] for x in timeline), "average_ms": round(1000 * sum(x["total_time"] for x in timeline) / max(1, sum(x["hits"] for x in timeline)), 1)}
            for item in timeline + hosts: item["average_ms"] = round(1000 * item.pop("total_time") / max(1, item["hits"]), 1)
            self.send_json(200, {"hours": hours, "totals": totals, "timeline": timeline, "hosts": hosts}); return
        if path in ("/api/users", "/api/redirects", "/api/streams", "/api/certificates", "/api/acme-providers", "/api/notifications", "/api/audit"):
            if not self.require(("admin",) if path in ("/api/users", "/api/acme-providers", "/api/notifications") else ("admin", "operator", "viewer")): return
            table = path.rsplit("/", 1)[1]
            table = "audit_log" if table == "audit" else table
            table = "acme_providers" if table == "acme-providers" else table
            table = "notification_channels" if table == "notifications" else table
            with connect() as db:
                columns = "id,username,role,enabled,created_at" if table == "users" else "*"
                rows = [rowdict(x) for x in db.execute(f"SELECT {columns} FROM {table} ORDER BY id DESC LIMIT 250")]
            if table == "acme_providers":
                for item in rows: item.pop("secret_data", None); item["configured"] = True
            if table == "notification_channels":
                for item in rows: item.pop("config_data", None); item["events"] = json.loads(item["events"]); item["configured"] = True
            self.send_json(200, {"items": rows}); return
        self.serve_file(path)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        try: body = self.json_body()
        except ValueError as error:
            if str(error) == "body too large":
                self.close_connection = True
                self.send_json(413, {"error": "Upload zu groß: Logo und Favicon dürfen jeweils maximal 2 MB groß sein"}, {"Connection": "close"})
            else:
                self.send_json(400, {"error": "Ungültige Anfrage"})
            return
        except Exception: self.send_json(400, {"error": "Ungültige Anfrage"}); return
        if path == "/api/login":
            with connect() as db: user = db.execute("SELECT * FROM users WHERE username=? AND enabled=1", (body.get("username", ""),)).fetchone()
            if not user or not password_ok(body.get("password", ""), user["password_hash"]):
                time.sleep(.35); self.send_json(401, {"error": "Benutzername oder Passwort falsch"}); return
            token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
            with connect() as db: db.execute("INSERT INTO sessions(token_hash,user_id,csrf,expires_at) VALUES(?,?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), user["id"], csrf, int(time.time()) + SESSION_TTL))
            secure = "; Secure" if os.environ.get("PROXYDECK_SECURE_COOKIE", "0") == "1" else ""
            self.send_json(200, {"user": {"username": user["username"], "role": user["role"]}, "csrf": csrf}, {"Set-Cookie": f"proxydeck_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESSION_COOKIE_TTL}{secure}"}); return
        if path == "/api/session/activity":
            session = self.require(("admin", "operator", "viewer"), csrf=True)
            if not session: return
            cookie = http.cookies.SimpleCookie(self.headers.get("cookie")); token = cookie.get("proxydeck_session")
            if token:
                token_hash = hashlib.sha256(token.value.encode()).hexdigest()
                with connect() as db: db.execute("UPDATE sessions SET expires_at=? WHERE token_hash=?", (int(time.time()) + SESSION_TTL, token_hash))
            self.send_json(200, {"ok": True}); return
        session = self.require(("admin", "operator"), csrf=True)
        if not session: return
        if path == "/api/update":
            if session["role"] != "admin": self.send_json(403, {"error": "Nur Administratoren"}); return
            UPDATE_DIR.mkdir(parents=True, exist_ok=True)
            try: updater_alive = int(time.time()) - int((UPDATE_DIR / "heartbeat").read_text(encoding="utf-8").strip()) < 15
            except (OSError, ValueError): updater_alive = False
            if not updater_alive: self.send_json(503, {"error": "Der Updater ist nicht aktuell oder nicht erreichbar. Updater-Container neu bauen."}); return
            if (UPDATE_DIR / "status").exists() and (UPDATE_DIR / "status").read_text(encoding="utf-8").strip() == "running": self.send_json(409, {"error": "Ein Update läuft bereits"}); return
            (UPDATE_DIR / "request").write_text(str(int(time.time())), encoding="utf-8")
            (UPDATE_DIR / "status").write_text("queued", encoding="utf-8")
            LOGGER.info("update queued user=%s", session["username"]); self.audit(session["id"], "system.update_queued", session["username"])
            self.send_json(202, {"ok": True, "status": "queued"}); return
        if path == "/api/update/check":
            if session["role"] != "admin": self.send_json(403, {"error": "Nur Administratoren"}); return
            UPDATE_DIR.mkdir(parents=True, exist_ok=True)
            try: updater_alive = int(time.time()) - int((UPDATE_DIR / "heartbeat").read_text(encoding="utf-8").strip()) < 15
            except (OSError, ValueError): updater_alive = False
            if not updater_alive: self.send_json(503, {"error": "Der Updater ist nicht aktuell oder nicht erreichbar. Updater-Container neu bauen."}); return
            if (UPDATE_DIR / "status").exists() and (UPDATE_DIR / "status").read_text(encoding="utf-8").strip() in ("running", "queued"): self.send_json(409, {"error": "Während eines Updates ist keine Prüfung möglich"}); return
            (UPDATE_DIR / "check").write_text(str(int(time.time())), encoding="utf-8"); (UPDATE_DIR / "status").write_text("checking", encoding="utf-8")
            LOGGER.info("update check queued user=%s", session["username"]); self.send_json(202, {"ok": True, "status": "checking"}); return
        if path == "/api/account/password":
            current_password, new_password = body.get("current_password", ""), body.get("new_password", "")
            with connect() as db: user = db.execute("SELECT password_hash FROM users WHERE id=?", (session["id"],)).fetchone()
            if not user or not password_ok(current_password, user["password_hash"]): self.send_json(403, {"error": "Das aktuelle Passwort ist nicht korrekt"}); return
            if len(new_password) < 16 or new_password == current_password: self.send_json(400, {"error": "Das neue Passwort muss mindestens 16 Zeichen lang und unterschiedlich sein"}); return
            with connect() as db:
                db.execute("UPDATE users SET password_hash=? WHERE id=?", (password_hash(new_password), session["id"]))
                db.execute("DELETE FROM sessions WHERE user_id=?", (session["id"],))
                db.execute("INSERT INTO audit_log(user_id,action,detail,created_at) VALUES(?,?,?,?)", (session["id"], "account.password_changed", session["username"], int(time.time())))
            self.send_json(200, {"ok": True, "message": "Passwort geändert; alle Sitzungen wurden beendet"}, {"Set-Cookie": "proxydeck_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"}); return
        if path == "/api/account/username":
            username = body.get("username", "").strip(); current_password = body.get("current_password", "")
            if not re.fullmatch(r"[A-Za-z0-9_.-]{3,64}", username): self.send_json(400, {"error": "Benutzername: 3–64 Zeichen, nur Buchstaben, Zahlen, Punkt, Bindestrich und Unterstrich"}); return
            with connect() as db: user = db.execute("SELECT password_hash FROM users WHERE id=?", (session["id"],)).fetchone()
            if not user or not password_ok(current_password, user["password_hash"]): self.send_json(403, {"error": "Das aktuelle Passwort ist nicht korrekt"}); return
            try:
                with connect() as db: db.execute("UPDATE users SET username=? WHERE id=?", (username, session["id"]))
                self.audit(session["id"], "account.username_changed", username); self.send_json(200, {"ok": True, "username": username})
            except sqlite3.IntegrityError: self.send_json(409, {"error": "Dieser Benutzername ist bereits vergeben"})
            return
        if path == "/api/users/update":
            if session["role"] != "admin": self.send_json(403, {"error": "Nur Administratoren"}); return
            try:
                user_id = int(body["id"]); username = body["username"].strip(); role = body["role"]; enabled = int(bool(body.get("enabled", True))); password = body.get("password", "")
                if not re.fullmatch(r"[A-Za-z0-9_.-]{3,64}", username) or role not in ("admin", "operator", "viewer") or password and len(password) < 16: raise ValueError()
                with connect() as db:
                    target = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
                    if not target: self.send_json(404, {"error": "Benutzer nicht gefunden"}); return
                    if user_id == session["id"] and (role != "admin" or not enabled): self.send_json(400, {"error": "Das eigene Administratorkonto kann nicht deaktiviert oder herabgestuft werden"}); return
                    if target["role"] == "admin" and target["enabled"] and (role != "admin" or not enabled) and db.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND enabled=1").fetchone()[0] <= 1: self.send_json(400, {"error": "Der letzte aktive Administrator muss erhalten bleiben"}); return
                    if password:
                        db.execute("UPDATE users SET username=?,role=?,enabled=?,password_hash=? WHERE id=?", (username, role, enabled, password_hash(password), user_id)); db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
                    else: db.execute("UPDATE users SET username=?,role=?,enabled=? WHERE id=?", (username, role, enabled, user_id))
                self.audit(session["id"], "user.update", username); self.send_json(200, {"ok": True})
            except (ValueError, KeyError, sqlite3.IntegrityError): self.send_json(400, {"error": "Benutzerdaten ungültig oder Benutzername bereits vergeben"})
            return
        if path == "/api/users/delete":
            if session["role"] != "admin": self.send_json(403, {"error": "Nur Administratoren"}); return
            try: user_id = int(body["id"])
            except (ValueError, KeyError): self.send_json(400, {"error": "Ungültiger Benutzer"}); return
            if user_id == session["id"]: self.send_json(400, {"error": "Das eigene Konto kann nicht gelöscht werden"}); return
            with connect() as db:
                target = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
                if not target: self.send_json(404, {"error": "Benutzer nicht gefunden"}); return
                if target["role"] == "admin" and target["enabled"] and db.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND enabled=1").fetchone()[0] <= 1: self.send_json(400, {"error": "Der letzte aktive Administrator muss erhalten bleiben"}); return
                db.execute("DELETE FROM users WHERE id=?", (user_id,))
            self.audit(session["id"], "user.delete", target["username"]); self.send_json(200, {"ok": True}); return
        if path == "/api/certificates/delete":
            if session["role"] != "admin": self.send_json(403, {"error": "Nur Administratoren"}); return
            try: certificate_id = int(body["id"])
            except (ValueError, KeyError): self.send_json(400, {"error": "Ungültiges Zertifikat"}); return
            with connect() as db:
                certificate = db.execute("SELECT * FROM certificates WHERE id=?", (certificate_id,)).fetchone()
                if not certificate: self.send_json(404, {"error": "Zertifikat nicht gefunden"}); return
                db.execute("UPDATE proxy_hosts SET certificate_id=NULL,ssl_enabled=0 WHERE certificate_id=?", (certificate_id,)); db.execute("DELETE FROM certificates WHERE id=?", (certificate_id,))
            generate_nginx(); cert_name = certificate["cert_name"] or certificate["domain"]
            try:
                cleanup = subprocess.run(["certbot", "delete", "--non-interactive", "--cert-name", cert_name], capture_output=True, text=True, timeout=120)
                warning = "" if cleanup.returncode == 0 else "Der Datenbankeintrag wurde gelöscht; Certbot meldete bei der Dateibereinigung einen Fehler."
            except (OSError, subprocess.TimeoutExpired): warning = "Der Datenbankeintrag wurde gelöscht; die Zertifikatsdateien konnten nicht automatisch bereinigt werden."
            self.audit(session["id"], "certificate.delete", certificate["domain"]); self.send_json(200, {"ok": True, "warning": warning}); return
        if path == "/api/logout":
            cookie = http.cookies.SimpleCookie(self.headers.get("cookie")); token = cookie.get("proxydeck_session")
            if token:
                with connect() as db: db.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(token.value.encode()).hexdigest(),))
            self.send_json(200, {"ok": True}, {"Set-Cookie": "proxydeck_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"}); return
        if path == "/api/branding":
            if session["role"] != "admin": self.send_json(403, {"error": "Nur Administratoren"}); return
            accent, background, logo, favicon = body.get("accent", ""), body.get("background", ""), body.get("logo", ""), body.get("favicon", "")
            gateway_ipv4, gateway_ipv6 = body.get("gateway_ipv4", "").strip(), body.get("gateway_ipv6", "").strip(); ui_scale = str(body.get("ui_scale", "1"))
            image_re = re.compile(r"^data:image/(?:png|jpeg|x-icon|vnd\.microsoft\.icon);base64,[A-Za-z0-9+/=]+$")
            if ui_scale not in ("0.5", "1", "1.0", "1.5") or any(not re.fullmatch(r"#[0-9a-fA-F]{6}", color) for color in (accent, background)) or any(value and (len(value) > 2_800_000 or not image_re.fullmatch(value)) for value in (logo, favicon)):
                self.send_json(400, {"error": "Farbe oder Bilddatei ungültig (PNG/JPG/ICO, maximal 2 MB)"}); return
            try:
                if gateway_ipv4 and ipaddress.ip_address(gateway_ipv4).version != 4: raise ValueError()
                if gateway_ipv6 and ipaddress.ip_address(gateway_ipv6).version != 6: raise ValueError()
            except ValueError: self.send_json(400, {"error": "Gateway-IPv4 oder Gateway-IPv6 ist ungültig"}); return
            with connect() as db:
                for key, value in (("accent", accent.lower()), ("background", background.lower()), ("logo", logo), ("favicon", favicon), ("gateway_ipv4", gateway_ipv4), ("gateway_ipv6", gateway_ipv6), ("ui_scale", "1" if ui_scale == "1.0" else ui_scale)):
                    db.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
            self.audit(session["id"], "branding.update", accent.lower()); self.send_json(200, {"ok": True}); return
        if path == "/api/proxy-hosts":
            try:
                domain = body["domain"].lower().strip(); port = int(body["port"]); targets = body["targets"]
                if not HOST_RE.match(domain) or not 0 < port < 65536 or not targets: raise ValueError()
                for target in targets:
                    if not valid_address(target["address"], target["family"]): raise ValueError()
                with connect() as db:
                    host_id = body.get("id")
                    certificate_id = body.get("certificate_id") or None
                    if certificate_id and not db.execute("SELECT 1 FROM certificates WHERE id=? AND status='issued'", (int(certificate_id),)).fetchone(): raise ValueError()
                    values = (domain, body.get("scheme", "http"), port, int(bool(body.get("websocket", True))), body.get("strategy", "least_conn"), int(bool(body.get("ssl_enabled", False))), int(bool(body.get("enabled", True))), certificate_id)
                    if host_id:
                        db.execute("UPDATE proxy_hosts SET domain=?,scheme=?,port=?,websocket=?,strategy=?,ssl_enabled=?,enabled=?,certificate_id=? WHERE id=?", values + (host_id,)); db.execute("DELETE FROM upstreams WHERE proxy_id=?", (host_id,))
                    else:
                        cur = db.execute("INSERT INTO proxy_hosts(domain,scheme,port,websocket,strategy,ssl_enabled,enabled,certificate_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)", values + (int(time.time()),)); host_id = cur.lastrowid
                    for target in targets:
                        health_path = target.get("health_path", "/").strip() or "/"
                        if not health_path.startswith("/") or len(health_path) > 512: raise ValueError()
                        db.execute("INSERT INTO upstreams(proxy_id,address,family,weight,mode,health_path) VALUES(?,?,?,?,?,?)", (host_id, target["address"], target["family"], max(1, min(100, int(target.get("weight", 100)))), target.get("mode", "active").lower(), health_path))
                generate_nginx(); self.audit(session["id"], "proxy.save", domain); self.send_json(200, {"ok": True, "id": host_id})
            except (ValueError, KeyError, sqlite3.IntegrityError) as error: self.send_json(400, {"error": "Domain, Port oder Zieladresse ist ungültig oder bereits vorhanden"})
            return
        if path == "/api/users":
            if session["role"] != "admin": self.send_json(403, {"error": "Nur Administratoren"}); return
            try:
                if len(body["password"]) < 16 or body["role"] not in ("admin", "operator", "viewer"): raise ValueError()
                with connect() as db: cur = db.execute("INSERT INTO users(username,password_hash,role,created_at) VALUES(?,?,?,?)", (body["username"].strip(), password_hash(body["password"]), body["role"], int(time.time())))
                self.audit(session["id"], "user.create", body["username"]); self.send_json(201, {"id": cur.lastrowid})
            except (ValueError, KeyError, sqlite3.IntegrityError): self.send_json(400, {"error": "Ungültiger oder vorhandener Benutzer; Passwort mindestens 16 Zeichen"})
            return
        if path == "/api/acme-providers":
            if session["role"] != "admin": self.send_json(403, {"error": "Nur Administratoren"}); return
            provider = body.get("provider", "").lower(); name = body.get("name", "").strip(); credentials = body.get("credentials", {})
            required = {"cloudflare": ("api_token",), "digitalocean": ("token",), "route53": ("access_key_id", "secret_access_key"), "ionos": ("api_token",), "hetzner": ("api_token",), "ipv64": ("api_token",), "strato": ("username", "password"), "powerdns": ("api_url", "server_id", "api_token")}
            try:
                with connect() as db: current_user = db.execute("SELECT password_hash FROM users WHERE id=?", (session["id"],)).fetchone()
                if not current_user or not password_ok(body.get("current_password", ""), current_user["password_hash"]):
                    self.send_json(403, {"error": "Das aktuelle Passwort ist nicht korrekt"}); return
                if provider not in required or not name or any(not credentials.get(key) for key in required[provider]): raise ValueError()
                encrypted = encrypt_secret({key: credentials[key] for key in required[provider]})
                provider_id = body.get("id")
                with connect() as db:
                    if provider_id:
                        changed = db.execute("UPDATE acme_providers SET name=?,provider=?,secret_data=? WHERE id=?", (name, provider, encrypted, int(provider_id))).rowcount
                        if not changed: raise ValueError()
                        result_id = int(provider_id)
                    else:
                        cur = db.execute("INSERT INTO acme_providers(name,provider,secret_data,created_at) VALUES(?,?,?,?)", (name, provider, encrypted, int(time.time()))); result_id = cur.lastrowid
                action = "acme_provider.rotate" if provider_id else "acme_provider.create"
                self.audit(session["id"], action, f"{name}:{provider}"); self.send_json(200 if provider_id else 201, {"id": result_id})
            except (ValueError, KeyError, sqlite3.IntegrityError, RuntimeError) as error: self.send_json(400, {"error": str(error) if isinstance(error, RuntimeError) else "DNS-Anbieter ungültig oder bereits vorhanden"})
            return
        if path == "/api/notifications":
            if session["role"] != "admin": self.send_json(403, {"error": "Nur Administratoren"}); return
            channel_type, name, config = body.get("channel_type", ""), body.get("name", "").strip(), body.get("config", {})
            required = {"smtp": ("host", "from_email", "to_email"), "telegram": ("bot_token", "chat_id"), "whatsapp": ("access_token", "phone_number_id", "recipient")}
            try:
                with connect() as db: current_user = db.execute("SELECT password_hash FROM users WHERE id=?", (session["id"],)).fetchone()
                if not current_user or not password_ok(body.get("current_password", ""), current_user["password_hash"]): self.send_json(403, {"error": "Das aktuelle Passwort ist nicht korrekt"}); return
                if channel_type not in required or not name or any(not config.get(key) for key in required[channel_type]): raise ValueError()
                events = [item for item in body.get("events", ["down", "up", "certificate"]) if item in ("down", "up", "certificate")]
                encrypted = encrypt_secret(config); channel_id = body.get("id")
                with connect() as db:
                    if channel_id:
                        if not db.execute("UPDATE notification_channels SET name=?,channel_type=?,config_data=?,events=?,enabled=? WHERE id=?", (name, channel_type, encrypted, json.dumps(events), int(bool(body.get("enabled", True))), int(channel_id))).rowcount: raise ValueError()
                        result_id = int(channel_id)
                    else:
                        cur = db.execute("INSERT INTO notification_channels(name,channel_type,config_data,events,enabled,created_at) VALUES(?,?,?,?,?,?)", (name, channel_type, encrypted, json.dumps(events), int(bool(body.get("enabled", True))), int(time.time()))); result_id = cur.lastrowid
                self.audit(session["id"], "notification.save", f"{name}:{channel_type}"); self.send_json(200 if channel_id else 201, {"id": result_id})
            except (ValueError, sqlite3.IntegrityError, RuntimeError) as error: self.send_json(400, {"error": str(error) if isinstance(error, RuntimeError) else "Benachrichtigungskanal ungültig oder bereits vorhanden"})
            return
        if path == "/api/notifications/test":
            if session["role"] != "admin": self.send_json(403, {"error": "Nur Administratoren"}); return
            with connect() as db:
                current_user = db.execute("SELECT password_hash FROM users WHERE id=?", (session["id"],)).fetchone(); channel = db.execute("SELECT * FROM notification_channels WHERE id=?", (body.get("id"),)).fetchone()
            if not current_user or not password_ok(body.get("current_password", ""), current_user["password_hash"]): self.send_json(403, {"error": "Das aktuelle Passwort ist nicht korrekt"}); return
            if not channel: self.send_json(404, {"error": "Kanal nicht gefunden"}); return
            try: send_notification(channel, "ProxyManagerDeck2 Testnachricht", "Der Benachrichtigungskanal funktioniert."); self.audit(session["id"], "notification.test", channel["name"]); self.send_json(200, {"ok": True})
            except Exception as error: self.send_json(502, {"error": f"Versand fehlgeschlagen: {error}"})
            return
        if path == "/api/redirects":
            try:
                domain, target, code = body["domain"].lower().strip(), body["target"].strip(), int(body.get("code", 301))
                if not HOST_RE.match(domain) or not target.startswith(("http://", "https://")) or code not in (301, 302, 307, 308): raise ValueError()
                with connect() as db: cur = db.execute("INSERT INTO redirects(domain,target,code,enabled) VALUES(?,?,?,1)", (domain, target, code))
                generate_nginx(); self.audit(session["id"], "redirect.create", domain); self.send_json(201, {"id": cur.lastrowid})
            except (ValueError, KeyError, sqlite3.IntegrityError): self.send_json(400, {"error": "Weiterleitung ungültig oder bereits vorhanden"})
            return
        if path == "/api/streams":
            try:
                listen_port, target_port = int(body["listen_port"]), int(body["target_port"]); protocol = body.get("protocol", "tcp").lower(); target = body["target_host"].strip()
                if protocol not in ("tcp", "udp") or not 0 < listen_port < 65536 or not 0 < target_port < 65536 or not valid_address(target, body.get("family", "Hostname")): raise ValueError()
                with connect() as db: cur = db.execute("INSERT INTO streams(listen_port,protocol,target_host,target_port,enabled) VALUES(?,?,?,?,1)", (listen_port, protocol, target, target_port))
                generate_nginx(); self.audit(session["id"], "stream.create", f"{protocol}:{listen_port}"); self.send_json(201, {"id": cur.lastrowid})
            except (ValueError, KeyError, sqlite3.IntegrityError): self.send_json(400, {"error": "Stream ungültig oder Port bereits vergeben"})
            return
        if path == "/api/certificates/request":
            if session["role"] != "admin": self.send_json(403, {"error": "Nur Administratoren"}); return
            raw_domains, email = body.get("domains", body.get("domain", "")), body.get("email", "")
            domains = raw_domains if isinstance(raw_domains, list) else re.split(r"[\s,;]+", str(raw_domains))
            domains = list(dict.fromkeys(value.lower().strip().rstrip(".") for value in domains if value.strip()))
            if any(value.startswith("*.") for value in domains):
                for wildcard in [value for value in domains if value.startswith("*.")]:
                    base = wildcard[2:]
                    if base not in domains: domains.insert(0, base)
            valid_domain = lambda value: bool(HOST_RE.fullmatch(value[2:] if value.startswith("*.") else value))
            if not domains or len(domains) > 100 or any(not valid_domain(value) for value in domains) or "@" not in email: self.send_json(400, {"error": "Domainliste oder E-Mail ungültig"}); return
            challenge, provider_id = body.get("challenge", "http-01"), body.get("provider_id")
            if any(value.startswith("*.") for value in domains) and challenge != "dns-01": self.send_json(400, {"error": "Wildcard-Zertifikate benötigen DNS-01 und ein DNS-Plugin"}); return
            if challenge not in ("http-01", "dns-01") or challenge == "dns-01" and not provider_id: self.send_json(400, {"error": "Für DNS-01 muss ein DNS-Anbieter gewählt werden"}); return
            threading.Thread(target=self.request_certificate, args=(domains, email, session["id"], challenge, provider_id), daemon=True).start()
            self.send_json(202, {"status": "ACME-Anforderung gestartet", "domains": domains}); return
        if path == "/api/apply":
            generate_nginx(); LOGGER.info("nginx configuration generated user=%s", session["username"]); self.audit(session["id"], "nginx.apply"); self.send_json(200, {"ok": True, "message": "Konfiguration atomar geschrieben; Nginx-Watcher prüft und lädt neu."}); return
        self.send_json(404, {"error": "Nicht gefunden"})

    def request_certificate(self, domains, email, user_id, challenge="http-01", provider_id=None):
        domain = domains[0]; cert_name = next((value for value in domains if not value.startswith("*.")), domains[0].replace("*.", ""))
        with connect() as db: db.execute("INSERT INTO certificates(domain,email,status,challenge,provider_id,domains_json,cert_name,created_at) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(domain) DO UPDATE SET email=excluded.email,status='requesting',challenge=excluded.challenge,provider_id=excluded.provider_id,domains_json=excluded.domains_json,cert_name=excluded.cert_name,last_error=NULL", (domain, email, "requesting", challenge, provider_id, json.dumps(domains), cert_name, int(time.time())))
        command = ["certbot", "certonly", "--cert-name", cert_name, "--email", email, "--agree-tos", "--non-interactive", "--keep-until-expiring"] + [part for value in domains for part in ("-d", value)]
        environment = os.environ.copy(); credentials_file = None
        if challenge == "http-01": command += ["--webroot", "-w", str(ACME_WEBROOT)]
        else:
            with connect() as db: provider = db.execute("SELECT * FROM acme_providers WHERE id=?", (provider_id,)).fetchone()
            if not provider:
                with connect() as db: db.execute("UPDATE certificates SET status='failed',last_error='DNS provider not found' WHERE domain=?", (domain,))
                return
            try: credentials = decrypt_secret(provider["secret_data"])
            except RuntimeError as error:
                with connect() as db: db.execute("UPDATE certificates SET status='failed',last_error=? WHERE domain=?", (str(error), domain))
                return
            if provider["provider"] == "cloudflare":
                credentials_file = DATA / f"acme-{secrets.token_hex(8)}.ini"; credentials_file.write_text(f"dns_cloudflare_api_token = {credentials['api_token']}\n", encoding="utf-8"); os.chmod(credentials_file, 0o600)
                command += ["--dns-cloudflare", "--dns-cloudflare-credentials", str(credentials_file), "--dns-cloudflare-propagation-seconds", "30"]
            elif provider["provider"] == "digitalocean":
                credentials_file = DATA / f"acme-{secrets.token_hex(8)}.ini"; credentials_file.write_text(f"dns_digitalocean_token = {credentials['token']}\n", encoding="utf-8"); os.chmod(credentials_file, 0o600)
                command += ["--dns-digitalocean", "--dns-digitalocean-credentials", str(credentials_file), "--dns-digitalocean-propagation-seconds", "30"]
            elif provider["provider"] == "route53":
                environment["AWS_ACCESS_KEY_ID"] = credentials["access_key_id"]; environment["AWS_SECRET_ACCESS_KEY"] = credentials["secret_access_key"]
                command += ["--dns-route53"]
            else:
                acme_plugins = {
                    "ionos": ("dns_ionos_cloud", {"IONOS_TOKEN": credentials["api_token"]}),
                    "hetzner": ("dns_hetzner", {"HETZNER_Token": credentials["api_token"]}),
                    "ipv64": ("dns_ipv64", {"IPv64_Token": credentials["api_token"]}),
                    "strato": ("dns_strato", {"STRATO_Username": credentials["username"], "STRATO_Password": credentials["password"]}),
                    "powerdns": ("dns_pdns", {"PDNS_Url": credentials["api_url"], "PDNS_ServerId": credentials["server_id"], "PDNS_Token": credentials["api_token"], "PDNS_Ttl": str(credentials.get("ttl", 60))})
                }
                dns_hook, plugin_env = acme_plugins[provider["provider"]]; environment.update(plugin_env)
                cert_dir = Path("/etc/letsencrypt/live") / cert_name; cert_dir.mkdir(parents=True, exist_ok=True)
                command = ["/opt/acme.sh-3.1.2/acme.sh", "--home", "/data/acme-sh", "--server", "letsencrypt", "--issue", "--dns", dns_hook, "--accountemail", email] + [part for value in domains for part in ("-d", value)]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=300, env=environment)
            status, error = ("issued", None) if result.returncode == 0 else ("failed", (result.stderr or result.stdout)[-2000:])
            if status == "issued" and challenge == "dns-01" and provider["provider"] in ("ionos", "hetzner", "ipv64", "strato", "powerdns"):
                install = subprocess.run(["/opt/acme.sh-3.1.2/acme.sh", "--home", "/data/acme-sh", "--install-cert", "-d", domain, "--key-file", str(cert_dir / "privkey.pem"), "--fullchain-file", str(cert_dir / "fullchain.pem")], capture_output=True, text=True, timeout=120, env=environment)
                if install.returncode != 0: status, error = "failed", (install.stderr or install.stdout)[-2000:]
        except Exception as exc: status, error = "failed", str(exc)
        finally:
            if credentials_file: credentials_file.unlink(missing_ok=True)
        expires_at = None
        if status == "issued":
            try:
                decoded = ssl._ssl._test_decode_cert(str(Path("/etc/letsencrypt/live") / cert_name / "fullchain.pem"))
                expires_at = int(ssl.cert_time_to_seconds(decoded["notAfter"]))
            except Exception:
                pass
        with connect() as db: db.execute("UPDATE certificates SET status=?,last_error=?,expires_at=? WHERE domain=?", (status, error, expires_at, domain))
        self.audit(user_id, "certificate." + status, ", ".join(domains))
        LOGGER.info("certificate status=%s domains=%s error=%s", status, ",".join(domains), (error or "-").replace("\n", " ")[:500])
        if status == "failed": dispatch_notification("certificate", "ProxyManagerDeck2: Zertifikatsfehler", f"Domains: {', '.join(domains)}\nFehler: {error or 'Unbekannter ACME-Fehler'}")

    def serve_file(self, url_path):
        requested = "/index.html" if url_path == "/" else url_path
        file = (PUBLIC / requested.lstrip("/")).resolve()
        if PUBLIC.resolve() not in file.parents:
            self.send_error(403); return
        try: data = file.read_bytes()
        except OSError: self.send_error(404); return
        self.send_response(200); self.send_header("Content-Type", MIME.get(file.suffix, "application/octet-stream")); self.send_header("Content-Length", str(len(data))); self.send_header("X-Frame-Options", "DENY"); self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; script-src 'self'; img-src 'self' data:"); self.end_headers(); self.wfile.write(data)

    def log_message(self, fmt, *args):
        message = fmt % args
        LOGGER.info("http client=%s method=%s path=%s result=%s", self.address_string(), self.command, urllib.parse.urlparse(self.path).path, message)
        print(time.strftime("%Y-%m-%d %H:%M:%S"), self.address_string(), message)


if __name__ == "__main__":
    init_db(); generate_nginx(); LOGGER.info("ProxyManagerDeck2 started port=%s", PORT)
    threading.Thread(target=health_loop, daemon=True).start()
    threading.Thread(target=renewal_loop, daemon=True).start()
    threading.Thread(target=traffic_loop, daemon=True).start()
    server = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"ProxyManagerDeck2 API listening on :{PORT}")
    server.serve_forever()
