#!/usr/bin/env bash
# Bootstrap a fresh EC2 instance into a running Meridian stack.
#
#   sudo bash provision.sh            # on the instance, as the default user
#
# Idempotent: every step checks before it acts, so a half-finished run is
# re-runnable rather than a reason to terminate the instance and start again.
#
# WHAT THIS DOES NOT DO, on purpose:
#   * It does not create .env. Secrets never live in this repo or this script.
#     The runbook has the operator scp it, and this script REFUSES to start the
#     stack without it rather than coming up half-configured.
#   * It does not restore the database. That is migrate.sh, run from the
#     laptop, because the dump lives there.
#   * It does not open any port to the world. The security group allows SSH
#     from one address; the dashboard is reached over an SSH tunnel.
set -euo pipefail

REPO_URL="${MERIDIAN_REPO_URL:-https://github.com/yyardi/Meridian.git}"
REPO_DIR="/opt/meridian"
SERVICE_USER="meridian"

log() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[31mFAILED: %s\033[0m\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "run with sudo"

# --------------------------------------------------------------------------- #
log "1/7  OS packages"
# --------------------------------------------------------------------------- #
if command -v apt-get >/dev/null; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq ca-certificates curl gnupg git jq unzip
  PKG=apt
elif command -v dnf >/dev/null; then
  dnf install -y -q ca-certificates curl gnupg2 git jq unzip
  PKG=dnf
else
  die "neither apt-get nor dnf found; this expects Ubuntu 22.04+ or AL2023"
fi

# --------------------------------------------------------------------------- #
log "2/7  Docker + compose plugin"
# --------------------------------------------------------------------------- #
if ! command -v docker >/dev/null; then
  if [[ $PKG == apt ]]; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
      | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
      > /etc/apt/sources.list.d/docker.list
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io \
      docker-buildx-plugin docker-compose-plugin
  else
    dnf install -y -q docker
    systemctl enable --now docker
    # AL2023 ships no compose plugin; install it where docker looks for plugins.
    mkdir -p /usr/local/lib/docker/cli-plugins
    ARCH=$(uname -m)
    curl -fsSL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-${ARCH}" \
      -o /usr/local/lib/docker/cli-plugins/docker-compose
    chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
  fi
fi
systemctl enable --now docker
docker compose version >/dev/null || die "docker compose plugin missing"

# --------------------------------------------------------------------------- #
log "3/7  service user"
# --------------------------------------------------------------------------- #
id -u "$SERVICE_USER" >/dev/null 2>&1 || useradd --system --create-home --shell /bin/bash "$SERVICE_USER"
usermod -aG docker "$SERVICE_USER"

# --------------------------------------------------------------------------- #
log "4/7  repository at $REPO_DIR"
# --------------------------------------------------------------------------- #
if [[ -d "$REPO_DIR/.git" ]]; then
  git -C "$REPO_DIR" fetch --quiet origin main
  git -C "$REPO_DIR" checkout --quiet main
  git -C "$REPO_DIR" reset --hard --quiet origin/main
else
  git clone --quiet "$REPO_URL" "$REPO_DIR"
fi
chown -R "$SERVICE_USER:$SERVICE_USER" "$REPO_DIR"

# --------------------------------------------------------------------------- #
log "5/7  secrets check (this script never creates .env)"
# --------------------------------------------------------------------------- #
# Refusing here is the point. A stack that starts without credentials looks
# healthy — containers up, heartbeats beating — and records nothing from the
# authenticated venue. Silent-and-running is the failure mode this project
# keeps paying for; better to stop with a sentence the operator can act on.
if [[ ! -f "$REPO_DIR/.env" ]]; then
  cat >&2 <<'MSG'

  .env is not present at /opt/meridian/.env

  Copy it from the laptop before running this step:

      scp -i ~/.ssh/meridian-aws.pem \
          /Users/<you>/Documents/Quant/Meridian/.env \
          ubuntu@<instance-ip>:/tmp/meridian.env
      sudo install -o meridian -g meridian -m 600 /tmp/meridian.env /opt/meridian/.env
      rm /tmp/meridian.env

  Then re-run this script. Nothing has been started.
MSG
  exit 1
fi
chown "$SERVICE_USER:$SERVICE_USER" "$REPO_DIR/.env"
chmod 600 "$REPO_DIR/.env"

for key in DATABASE_URL POLYMARKET_KEY_ID POLYMARKET_SECRET_KEY COMPOSE_FILE; do
  grep -q "^${key}=." "$REPO_DIR/.env" || die "$key missing or empty in .env"
done
echo "  .env present, mode 600, required keys non-empty (values never printed)"

# --------------------------------------------------------------------------- #
log "6/7  artifact root"
# --------------------------------------------------------------------------- #
# core/paths.py: MERIDIAN_DATA_DIR is the single root, and compose binds
# $MERIDIAN_DATA_DIR/ticks into the postgres container at /backups. Create both
# halves now so the first retention run does not fail on a missing directory.
DATA_DIR=$(grep -E '^MERIDIAN_DATA_DIR=' "$REPO_DIR/.env" | cut -d= -f2- || true)
DATA_DIR="${DATA_DIR:-$REPO_DIR/backups}"
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" "$DATA_DIR"/{ticks,supabase,reports,exports}
echo "  artifact root: $DATA_DIR"

# --------------------------------------------------------------------------- #
log "7/8  health venv (small, on the HOST — see the runbook for why)"
# --------------------------------------------------------------------------- #
# scripts/ is deliberately not in the container image, and health.py's whole
# reason for existing is to see what a container CANNOT: `docker compose ps`
# and the host's disk. Running it inside a container would need the docker
# socket mounted in, which hands root-equivalent host access to a container on
# a box holding the venue secret key — too much privilege for a status
# command.
#
# So it runs on the host, in its own venv. The dependency list below was found
# by RUNNING it, not by reading imports: healthchecks.py's own imports are just
# httpx and sqlalchemy, but it lazily imports core.storage (dotenv) and
# core.heartbeat (structlog) partway through a run. Reading the top of one file
# under-counted, and the failure arrived three checks in. Measured size: 63 MB.
if [[ ! -x "$REPO_DIR/.venv-health/bin/python" ]]; then
  if [[ $PKG == apt ]]; then
    apt-get install -y -qq python3-venv python3-pip
  else
    dnf install -y -q python3 python3-pip
  fi
  sudo -H -u "$SERVICE_USER" python3 -m venv "$REPO_DIR/.venv-health"
  sudo -H -u "$SERVICE_USER" "$REPO_DIR/.venv-health/bin/pip" install -q --upgrade pip
  sudo -H -u "$SERVICE_USER" "$REPO_DIR/.venv-health/bin/pip" install -q \
    'httpx>=0.27' 'sqlalchemy>=2.0' 'psycopg[binary]>=3.1' 'python-dotenv>=1.0' \
    'structlog>=24.1'
fi
sudo -H -u "$SERVICE_USER" "$REPO_DIR/.venv-health/bin/python" \
  -c 'import httpx, sqlalchemy, psycopg, dotenv, structlog' \
  || die "health venv is missing a dependency"
echo "  $REPO_DIR/.venv-health ready"

# --------------------------------------------------------------------------- #
log "8/8  build and start the stack"
# --------------------------------------------------------------------------- #
# COMPOSE_FILE in .env selects the stack (base + quote + pulse + espn-live).
# --build is not optional: Dockerfile COPYs core/ and static/ into the image,
# so a plain `up -d` would serve whatever the last build contained.
cd "$REPO_DIR"
# -H, not --preserve-env=HOME. Keeping the invoking user's HOME leaves
# HOME=/root, and the docker CLI looks for plugins under $HOME/.docker/cli-plugins
# — so `compose` is simply not found and the error surfaces as the baffling
# "unknown flag: --env-file" rather than "no such subcommand". -H sets HOME to
# the target user's own. This bit us live.
sudo -H -u "$SERVICE_USER" docker compose --env-file .env up -d --build

echo
docker compose --env-file .env ps
cat <<'MSG'

Stack is up, and the database is EMPTY until migrate.sh runs from the laptop.

Verify before migrating:
    docker compose exec postgres pg_isready -U meridian -d meridian

Reach the dashboard over a tunnel rather than opening a port:
    ssh -i ~/.ssh/meridian-aws.pem -N -L 8008:localhost:8008 ubuntu@<instance-ip>
    open http://localhost:8008
MSG
