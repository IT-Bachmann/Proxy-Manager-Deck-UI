#!/bin/sh
set -eu

PROGRAM="ProxyManagerDeck2"
MIN_DOCKER_MAJOR=24
SKIP_DOCKER_INSTALL=0
NO_START=0
FORCE_PORTS=0

say() { printf '\n\033[1;32m%s\033[0m\n' "$*"; }
warn() { printf '\033[1;33mWarning:\033[0m %s\n' "$*" >&2; }
die() { printf '\033[1;31mError:\033[0m %s\n' "$*" >&2; exit 1; }
has() { command -v "$1" >/dev/null 2>&1; }

usage() {
  printf '%s\n' \
    'Usage: ./install.sh [options]' \
    '' \
    'Options:' \
    '  --skip-docker-install  Do not install Docker when it is missing' \
    '  --no-start             Prepare the installation without starting containers' \
    '  --force-ports          Continue despite detected port conflicts' \
    '  -h, --help             Show this help' \
    '' \
    'Run this script from the ProxyManagerDeck2 repository directory.'
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --skip-docker-install) SKIP_DOCKER_INSTALL=1 ;;
    --no-start) NO_START=1 ;;
    --force-ports) FORCE_PORTS=1 ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown option: $1" ;;
  esac
  shift
done

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"
[ -f compose.yml ] || die "compose.yml not found. Run the script from a complete ProxyManagerDeck2 checkout."

if [ "$(uname -s)" != "Linux" ]; then
  die "This installer supports Linux. On other systems install Docker Compose and run: docker compose up -d --build"
fi

container_type=""
if has systemd-detect-virt; then container_type=$(systemd-detect-virt --container 2>/dev/null || true); fi
if [ "$container_type" = "lxc" ] || grep -qaE 'lxc|container=' /proc/1/environ 2>/dev/null; then
  warn "LXC detected. On the Proxmox host, enable nesting=1 and keyctl=1 for this container before running Docker."
  warn "Example on the PVE host: pct set CTID -features nesting=1,keyctl=1"
  if [ -r /proc/sys/net/ipv6/conf/all/disable_ipv6 ] && [ "$(cat /proc/sys/net/ipv6/conf/all/disable_ipv6)" = "1" ]; then
    warn "IPv6 is disabled inside this LXC. ProxyManagerDeck2 starts with its private Docker ULA subnet, but external IPv6 upstreams require IPv6 on the LXC network interface."
  fi
fi

architecture=$(uname -m)
case "$architecture" in
  x86_64|amd64|aarch64|arm64) ;;
  armv7l) warn "32-bit ARM is not covered by the automated image test matrix." ;;
  *) warn "Architecture $architecture has not been tested with all container images." ;;
esac

free_kb=$(df -Pk "$SCRIPT_DIR" 2>/dev/null | awk 'NR==2 {print $4}' || true)
if [ -n "$free_kb" ] && [ "$free_kb" -lt 2097152 ] 2>/dev/null; then
  warn "Less than 2 GiB disk space is available. Docker builds may fail."
fi

if [ "$(id -u)" -eq 0 ]; then
  AS_ROOT=""
elif has sudo; then
  AS_ROOT="sudo"
else
  die "Root privileges are needed to install Docker. Run as root or install sudo."
fi

install_packages() {
  manager=$1
  shift
  case "$manager" in
    apt)
      $AS_ROOT apt-get update
      $AS_ROOT apt-get install -y "$@"
      ;;
    dnf) $AS_ROOT dnf install -y "$@" ;;
    yum) $AS_ROOT yum install -y "$@" ;;
    zypper) $AS_ROOT zypper --non-interactive install "$@" ;;
    pacman) $AS_ROOT pacman -Sy --needed --noconfirm "$@" ;;
    apk) $AS_ROOT apk add --no-cache "$@" ;;
    *) return 1 ;;
  esac
}

install_docker() {
  [ "$SKIP_DOCKER_INSTALL" -eq 0 ] || die "Docker is missing and --skip-docker-install was specified."
  say "Installing Docker and Compose"

  if has apt-get; then
    install_packages apt ca-certificates curl openssl docker.io
    install_packages apt docker-compose-v2 2>/dev/null || install_packages apt docker-compose-plugin 2>/dev/null || install_packages apt docker-compose
  elif has dnf; then
    install_packages dnf ca-certificates curl openssl moby-engine docker-compose 2>/dev/null || install_packages dnf ca-certificates curl openssl docker docker-compose-plugin
  elif has yum; then
    install_packages yum ca-certificates curl openssl docker docker-compose-plugin 2>/dev/null || install_packages yum ca-certificates curl openssl docker docker-compose
  elif has zypper; then
    install_packages zypper ca-certificates curl openssl docker docker-compose
  elif has pacman; then
    install_packages pacman ca-certificates curl openssl docker docker-compose
  elif has apk; then
    install_packages apk ca-certificates curl openssl docker docker-cli-compose
  else
    die "No supported package manager found. Install Docker Engine 24+ and Docker Compose v2, then rerun with --skip-docker-install."
  fi
}

has docker || install_docker
has openssl || {
  if has apt-get; then install_packages apt openssl
  elif has dnf; then install_packages dnf openssl
  elif has yum; then install_packages yum openssl
  elif has zypper; then install_packages zypper openssl
  elif has pacman; then install_packages pacman openssl
  elif has apk; then install_packages apk openssl
  else die "OpenSSL is required to generate secure credentials."
  fi
}

if has systemctl; then
  $AS_ROOT systemctl enable --now docker
elif has rc-update; then
  $AS_ROOT rc-update add docker default >/dev/null 2>&1 || true
  $AS_ROOT rc-service docker start
elif has service; then
  $AS_ROOT service docker start
fi

if ! has curl; then
  if has apt-get; then install_packages apt curl
  elif has dnf; then install_packages dnf curl
  elif has yum; then install_packages yum curl
  elif has zypper; then install_packages zypper curl
  elif has pacman; then install_packages pacman curl
  elif has apk; then install_packages apk curl
  else die "curl is required for the post-install healthcheck."
  fi
fi

docker_major=$($AS_ROOT docker version --format '{{.Server.Version}}' 2>/dev/null | cut -d. -f1 || true)
[ -n "$docker_major" ] || die "Docker daemon is not reachable. Check the service and permissions."
if [ "$docker_major" -lt "$MIN_DOCKER_MAJOR" ] 2>/dev/null; then
  warn "Docker $docker_major is older than the recommended version $MIN_DOCKER_MAJOR."
fi

$AS_ROOT docker info >/dev/null 2>&1 || die "Docker daemon healthcheck failed."

if $AS_ROOT docker compose version >/dev/null 2>&1; then
  COMPOSE="$AS_ROOT docker compose"
elif has docker-compose; then
  COMPOSE="$AS_ROOT docker-compose"
  warn "Legacy docker-compose detected. Docker Compose v2 is recommended."
else
  die "Docker Compose was not found after installation. Install Compose v2 and rerun."
fi

compose_version=$($COMPOSE version --short 2>/dev/null || $COMPOSE version 2>/dev/null || true)
say "Preflight checks"
printf 'Architecture: %s\nDocker:       %s\nCompose:      %s\n' "$architecture" "$($AS_ROOT docker version --format '{{.Server.Version}}')" "$compose_version"

port_in_use() {
  checked_port=$1
  if has ss; then ss -lnt 2>/dev/null | awk '{print $4}' | grep -Eq "(^|:)$checked_port$"
  elif has netstat; then netstat -lnt 2>/dev/null | awk '{print $4}' | grep -Eq "(^|:)$checked_port$"
  else return 1
  fi
}

conflicting_ports=""
existing_project=$($COMPOSE ps -q 2>/dev/null || true)
if [ -n "$existing_project" ]; then
  warn "An existing ProxyManagerDeck2 Compose project was detected; host-port collision checks are skipped for this upgrade."
else
  for checked_port in 80 443 8181 45130; do
    if port_in_use "$checked_port"; then conflicting_ports="$conflicting_ports $checked_port"; fi
  done
fi
if [ -n "$conflicting_ports" ]; then
  if [ "$FORCE_PORTS" -eq 1 ]; then warn "Ports already in use:$conflicting_ports"
  else die "Ports already in use:$conflicting_ports. Stop the conflicting services or rerun with --force-ports after reviewing compose.yml."
  fi
fi

if [ -r /proc/sys/net/ipv6/conf/all/disable_ipv6 ] && [ "$(cat /proc/sys/net/ipv6/conf/all/disable_ipv6)" = "1" ]; then
  warn "IPv6 is disabled in the host kernel. IPv4 works, but dual-stack listeners will not be reachable over IPv6."
fi

if has ufw && $AS_ROOT ufw status 2>/dev/null | grep -q 'Status: active'; then
  warn "UFW is active. Allow TCP 80/443, demo TCP 45130 and every configured stream port manually."
elif has firewall-cmd && $AS_ROOT firewall-cmd --state >/dev/null 2>&1; then
  warn "firewalld is active. Allow TCP 80/443, demo TCP 45130 and every configured stream port manually."
fi

primary_ipv4=""
primary_ipv6=""
if has ip; then
  primary_ipv4=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}' || true)
  primary_ipv6=$(ip -6 route get 2606:4700:4700::1111 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}' || true)
  if [ -z "$primary_ipv6" ]; then
    primary_ipv6=$(ip -6 -o addr show scope global 2>/dev/null | awk 'NR==1 {split($4,a,"/"); print a[1]}' || true)
  fi
fi
if [ -z "$primary_ipv4" ] && has hostname; then
  primary_ipv4=$(hostname -I 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i !~ /:/ && $i !~ /^127\./){print $i; exit}}' || true)
fi
dashboard_host=${primary_ipv4:-localhost}
dashboard_url="http://${dashboard_host}:8181"
demo_url="http://${dashboard_host}:45130"

if [ ! -f .env ]; then
  say "Generating secure local configuration"
  admin_password=$(openssl rand -base64 30 | tr -d '\n')
  secret_key=$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '\n')
  umask 077
  {
    printf 'PROXYDECK_ADMIN_USER=admin\n'
    printf 'PROXYDECK_ADMIN_PASSWORD=%s\n' "$admin_password"
    printf 'PROXYDECK_BIND_ADDRESS=0.0.0.0\n'
    printf 'PROXYDECK_BIND_ADDRESS_IPV6=::\n'
    printf 'PROXYDECK_SECRET_KEY=%s\n' "$secret_key"
    printf 'PROXYDECK_SECURE_COOKIE=0\n'
  } > .env
  {
    printf 'ProxyManagerDeck2 Dashboard IPv4: %s\n' "$dashboard_url"
    printf 'ProxyManagerDeck2 Demo IPv4: %s\n' "$demo_url"
    if [ -n "$primary_ipv6" ]; then
      printf 'ProxyManagerDeck2 Dashboard IPv6: http://[%s]:8181\n' "$primary_ipv6"
      printf 'ProxyManagerDeck2 Demo IPv6: http://[%s]:45130\n' "$primary_ipv6"
    fi
    printf 'Benutzer: admin\n'
    printf 'Passwort: %s\n' "$admin_password"
    printf 'Bind-Adresse IPv4: 0.0.0.0:8181 (alle IPv4-Schnittstellen)\n'
    printf 'Bind-Adresse IPv6: [::]:8181 (alle IPv6-Schnittstellen)\n'
    printf 'Direkter Zugriff: %s\n' "$dashboard_url"
  } > proxydeck-login.txt
  chmod 600 .env proxydeck-login.txt
  credentials_created=1
else
  credentials_created=0
  warn ".env already exists; existing credentials were preserved."
fi
if ! grep -q '^PROXYDECK_BIND_ADDRESS=' .env; then
  printf 'PROXYDECK_BIND_ADDRESS=0.0.0.0\n' >> .env
fi
if ! grep -q '^PROXYDECK_BIND_ADDRESS_IPV6=' .env; then
  printf 'PROXYDECK_BIND_ADDRESS_IPV6=::\n' >> .env
fi
chmod 600 .env

# Refresh addresses in the credentials note on every run without changing the password.
if [ -f proxydeck-login.txt ]; then
  login_tmp=$(mktemp "${TMPDIR:-/tmp}/proxydeck-login.XXXXXX")
  {
    printf 'ProxyManagerDeck2 Dashboard IPv4: %s\n' "$dashboard_url"
    printf 'ProxyManagerDeck2 Demo IPv4: %s\n' "$demo_url"
    if [ -n "$primary_ipv6" ]; then
      printf 'ProxyManagerDeck2 Dashboard IPv6: http://[%s]:8181\n' "$primary_ipv6"
      printf 'ProxyManagerDeck2 Demo IPv6: http://[%s]:45130\n' "$primary_ipv6"
    fi
    printf 'Bind-Adresse IPv4: 0.0.0.0:8181 (alle IPv4-Schnittstellen)\n'
    printf 'Bind-Adresse IPv6: [::]:8181 (alle IPv6-Schnittstellen)\n'
    printf 'Direkter Zugriff: %s\n' "$dashboard_url"
    awk '!/^ProxyManagerDeck2 Dashboard/ && !/^ProxyManagerDeck2 Demo/ && !/^Remote-Zugriff:/ && !/^Bind-Adresse/ && !/^Direkter Zugriff:/' proxydeck-login.txt
  } > "$login_tmp"
  mv "$login_tmp" proxydeck-login.txt
  chmod 600 proxydeck-login.txt
fi

say "Validating Docker Compose configuration"
$COMPOSE config --quiet

if [ "$NO_START" -eq 0 ]; then
  say "Building and starting ProxyManagerDeck2"
  $COMPOSE up -d --build
  say "Container status"
  $COMPOSE ps
  say "Waiting for the dashboard healthcheck"
  attempt=1
  ready=0
  while [ "$attempt" -le 30 ]; do
    if curl -fsS --max-time 2 http://127.0.0.1:8181/ >/dev/null 2>&1; then ready=1; break; fi
    sleep 2
    attempt=$((attempt + 1))
  done
  if [ "$ready" -ne 1 ]; then
    $COMPOSE logs --tail=40 control gateway || true
    die "Dashboard did not become healthy within 60 seconds. Recent logs are shown above."
  fi
fi

printf '\n\033[1;32mProxyManagerDeck2 installation prepared successfully.\033[0m\n'
printf 'Dashboard IPv4: %s\n' "$dashboard_url"
printf 'Demo IPv4:      %s\n' "$demo_url"
if [ -n "$primary_ipv6" ]; then
  printf 'Dashboard IPv6: http://[%s]:8181\n' "$primary_ipv6"
  printf 'Demo IPv6:      http://[%s]:45130\n' "$primary_ipv6"
fi
printf 'User:      admin\n'
printf 'Bind IPv4: 0.0.0.0:8181 (alle IPv4-Schnittstellen)\n'
printf 'Bind IPv6: [::]:8181 (alle IPv6-Schnittstellen)\n'
if [ "$credentials_created" -eq 1 ]; then
  printf 'Password:  %s\n' "$admin_password"
  printf '\nSave this password now. It is stored in .env and proxydeck-login.txt and will not be printed again.\n'
fi
printf '\nDirekter Zugriff im Netzwerk: %s\n' "$dashboard_url"
printf 'Firewall: TCP-Port 8181 nur für vertrauenswürdige Netze freigeben.\n'
printf '\nNext: read SECURITY.md and change PROXYDECK_SECURE_COOKIE only after enabling HTTPS.\n'
