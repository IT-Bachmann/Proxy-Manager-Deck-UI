#!/bin/sh
set -u
mkdir -p /updates
touch /updates/update.log
chmod 777 /updates
chmod 666 /updates/update.log
git config --global --add safe.directory /workspace
check_updates() {
  printf 'checking' > /updates/status
  date +%s > /updates/check_started
  if timeout 90 git -C /workspace fetch origin "${UPDATE_BRANCH:-main}" >> /updates/update.log 2>&1; then
    local_commit=$(git -C /workspace rev-parse HEAD 2>/dev/null || true)
    remote_commit=$(git -C /workspace rev-parse "origin/${UPDATE_BRANCH:-main}" 2>/dev/null || true)
    printf '%s' "$local_commit" > /updates/local_commit
    printf '%s' "$remote_commit" > /updates/remote_commit
    date +%s > /updates/last_checked
    if [ -n "$remote_commit" ] && [ "$local_commit" != "$remote_commit" ]; then
      printf 'available' > /updates/status
      date -u +'%Y-%m-%dT%H:%M:%SZ Neues Update verfügbar' >> /updates/update.log
    else
      printf 'current' > /updates/status
      date -u +'%Y-%m-%dT%H:%M:%SZ Keine neuen Updates' >> /updates/update.log
    fi
  else
    printf 'check_failed' > /updates/status
    date +%s > /updates/last_checked
    date -u +'%Y-%m-%dT%H:%M:%SZ Update-Prüfung fehlgeschlagen' >> /updates/update.log
  fi
  rm -f /updates/check_started
  chmod 666 /updates/status /updates/last_checked /updates/local_commit /updates/remote_commit 2>/dev/null || true
}
while true; do
  date +%s > /updates/heartbeat
  chmod 666 /updates/heartbeat 2>/dev/null || true
  if [ -f /updates/request ]; then
    rm -f /updates/request
    date -u +'%Y-%m-%dT%H:%M:%SZ UPDATE gestartet' >> /updates/update.log
    printf 'running' > /updates/status
    chmod 666 /updates/status
    date -u +'%Y-%m-%dT%H:%M:%SZ [1/4] GitHub-Änderungen abrufen' >> /updates/update.log
    if timeout 120 git -C /workspace fetch origin "${UPDATE_BRANCH:-main}" >> /updates/update.log 2>&1; then
      date -u +'%Y-%m-%dT%H:%M:%SZ [2/4] Fast-Forward-Merge prüfen' >> /updates/update.log
    else
      printf 'failed' > /updates/status; date -u +'%Y-%m-%dT%H:%M:%SZ UPDATE fehlgeschlagen: GitHub nicht erreichbar' >> /updates/update.log; continue
    fi
    if git -C /workspace merge --ff-only "origin/${UPDATE_BRANCH:-main}" >> /updates/update.log 2>&1; then
      date -u +'%Y-%m-%dT%H:%M:%SZ [3/4] Docker-Images bauen' >> /updates/update.log
    else
      printf 'failed' > /updates/status; date -u +'%Y-%m-%dT%H:%M:%SZ UPDATE fehlgeschlagen: lokale Änderungen oder Merge-Konflikt' >> /updates/update.log; continue
    fi
    if docker compose -p "${COMPOSE_PROJECT_NAME:-proxy-manager-deck2}" -f /workspace/compose.yml --project-directory /workspace build control gateway demo updater >> /updates/update.log 2>&1; then
      date -u +'%Y-%m-%dT%H:%M:%SZ [4/4] Container neu erstellen und Healthcheck abwarten' >> /updates/update.log
    else
      printf 'failed' > /updates/status; date -u +'%Y-%m-%dT%H:%M:%SZ UPDATE fehlgeschlagen: Image-Build' >> /updates/update.log; continue
    fi
    if docker compose -p "${COMPOSE_PROJECT_NAME:-proxy-manager-deck2}" -f /workspace/compose.yml --project-directory /workspace up -d --force-recreate control gateway demo >> /updates/update.log 2>&1; then
      printf 'success' > /updates/status
      git -C /workspace rev-parse HEAD > /updates/local_commit 2>/dev/null || true
      git -C /workspace rev-parse HEAD > /updates/remote_commit 2>/dev/null || true
      date +%s > /updates/last_checked
      date -u +'%Y-%m-%dT%H:%M:%SZ UPDATE erfolgreich' >> /updates/update.log
      # Never recreate this container from inside itself. Docker may remove the
      # running updater before its Compose client has created the replacement.
      # Reload the freshly pulled script in the existing container instead.
      if [ -r /workspace/updater/update.sh ]; then
        date -u +'%Y-%m-%dT%H:%M:%SZ Updater-Skript wird ohne Container-Unterbrechung neu geladen' >> /updates/update.log
        exec /bin/sh /workspace/updater/update.sh
      fi
    else
      printf 'failed' > /updates/status
      date -u +'%Y-%m-%dT%H:%M:%SZ UPDATE fehlgeschlagen' >> /updates/update.log
    fi
  elif [ -f /updates/check ]; then
    rm -f /updates/check
    check_updates
  else
    now=$(date +%s)
    last=$(cat /updates/last_checked 2>/dev/null || printf '0')
    interval=${UPDATE_CHECK_INTERVAL:-21600}
    if [ $((now - last)) -ge "$interval" ]; then check_updates; fi
  fi
  sleep 3
done
