#!/bin/sh
set -eu
watch_config() {
  while inotifywait -qq -e close_write,create,move /etc/nginx/proxydeck; do
    if nginx -t; then nginx -s reload; else echo "ProxyManagerDeck2: invalid config rejected" >&2; fi
  done
}
watch_config &
exec nginx -g 'daemon off;'
