#!/bin/sh
set -eu

cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
[ -f compose.yml ] || { echo "compose.yml fehlt" >&2; exit 1; }

printf 'Benutzer [admin]: '
read -r reset_user
reset_user=${reset_user:-admin}
printf 'Neues Passwort (mindestens 16 Zeichen): '
stty -echo
read -r reset_password
stty echo
printf '\nPasswort wiederholen: '
stty -echo
read -r reset_confirm
stty echo
printf '\n'

[ "$reset_password" = "$reset_confirm" ] || { echo "Passwörter stimmen nicht überein." >&2; exit 1; }
[ "$(printf %s "$reset_password" | wc -c)" -ge 16 ] || { echo "Das Passwort muss mindestens 16 Zeichen lang sein." >&2; exit 1; }

PROXYDECK_RESET_USER=$reset_user PROXYDECK_RESET_PASSWORD=$reset_password \
  docker compose exec -T \
  -e PROXYDECK_RESET_USER="$reset_user" \
  -e PROXYDECK_RESET_PASSWORD="$reset_password" \
  control python -c 'import os,sqlite3; from server import password_hash,DB; db=sqlite3.connect(DB); user=os.environ["PROXYDECK_RESET_USER"]; password=os.environ["PROXYDECK_RESET_PASSWORD"]; changed=db.execute("UPDATE users SET password_hash=? WHERE username=?",(password_hash(password),user)).rowcount; db.execute("DELETE FROM sessions"); db.commit(); assert changed, "Benutzer nicht gefunden"'

if [ -f .env ]; then
  tmp_env=$(mktemp "${TMPDIR:-/tmp}/proxydeck-env.XXXXXX")
  awk -v value="$reset_password" 'BEGIN{done=0} /^PROXYDECK_ADMIN_PASSWORD=/{print "PROXYDECK_ADMIN_PASSWORD=" value; done=1; next} {print} END{if(!done) print "PROXYDECK_ADMIN_PASSWORD=" value}' .env > "$tmp_env"
  mv "$tmp_env" .env
  chmod 600 .env
fi

if [ -f proxydeck-login.txt ]; then
  tmp_login=$(mktemp "${TMPDIR:-/tmp}/proxydeck-login.XXXXXX")
  awk -v value="$reset_password" 'BEGIN{done=0} /^Passwort:/{print "Passwort: " value; done=1; next} {print} END{if(!done) print "Passwort: " value}' proxydeck-login.txt > "$tmp_login"
  mv "$tmp_login" proxydeck-login.txt
  chmod 600 proxydeck-login.txt
fi

unset reset_password reset_confirm PROXYDECK_RESET_PASSWORD
printf 'Passwort für %s wurde geändert. Alle Sitzungen wurden beendet.\n' "$reset_user"
