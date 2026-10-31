#!/usr/bin/env bash
# One-time setup for the always-on CPU box (Ubuntu 22.04/24.04, run as root from the repo root).
#   sudo ./deploy/setup-cpu-box.sh <public-ip-or-hostname-of-this-box>
# Idempotent: safe to re-run. Prints the block you paste into the GPU instance.
set -euo pipefail

CPU_HOST="${1:?usage: setup-cpu-box.sh <public IP or hostname of this box>}"
TUNNEL_USER=lstunnel
TUNNEL_PORT=8001
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"

[[ $EUID -eq 0 ]] || { echo "run as root"; exit 1; }

echo "==> Docker"
if ! command -v docker >/dev/null; then
  apt-get update -q
  apt-get install -y -q docker.io docker-compose-v2
  systemctl enable --now docker
fi

echo "==> .env and secrets"
gen() { openssl rand -hex 32; }
[[ -f .env ]] || cp .env.example .env
set_if_empty() {  # key value
  if grep -qE "^$1=$" .env; then sed -i "s|^$1=$|$1=$2|" .env; fi
}
set_if_empty API_TOKEN "$(gen)"
set_if_empty SEARXNG_SECRET "$(gen)"
set_if_empty LLM_API_KEY "$(gen)"
chmod 600 .env
LLM_API_KEY="$(grep -E '^LLM_API_KEY=' .env | cut -d= -f2-)"

echo "==> Tunnel user (reverse-forward to 127.0.0.1:${TUNNEL_PORT} only, no shell)"
id "$TUNNEL_USER" >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin "$TUNNEL_USER"
install -d -m 700 secrets
if [[ ! -f secrets/gpu_tunnel_key ]]; then
  ssh-keygen -q -t ed25519 -N "" -C "leadscout-gpu-tunnel" -f secrets/gpu_tunnel_key
fi
install -d -m 700 -o "$TUNNEL_USER" -g "$TUNNEL_USER" "/home/$TUNNEL_USER/.ssh"
echo "restrict,port-forwarding,permitlisten=\"127.0.0.1:${TUNNEL_PORT}\",command=\"/bin/false\" $(cat secrets/gpu_tunnel_key.pub)" \
  > "/home/$TUNNEL_USER/.ssh/authorized_keys"
chown "$TUNNEL_USER:$TUNNEL_USER" "/home/$TUNNEL_USER/.ssh/authorized_keys"
chmod 600 "/home/$TUNNEL_USER/.ssh/authorized_keys"

cat > /etc/ssh/sshd_config.d/60-leadscout-tunnel.conf <<EOF
Match User ${TUNNEL_USER}
    AllowTcpForwarding remote
    PermitListen 127.0.0.1:${TUNNEL_PORT}
    GatewayPorts no
    X11Forwarding no
    AllowAgentForwarding no
    PermitTTY no
    PasswordAuthentication no
EOF
sshd -t
systemctl reload ssh 2>/dev/null || systemctl reload sshd

echo "==> Build and start"
TAG="$(python3 -c 'import re;print(re.search(r"\"(.+)\"",open("app/leadscout/__init__.py").read()).group(1))')"
export LEADSCOUT_TAG="$TAG"
docker build -t "leadscout:${TAG}" ./app
PROFILE_ARGS=()
if grep -qE '^PUBLIC_HOSTNAME=.+' .env; then
  PROFILE_ARGS=(--profile public)
  echo "    publishing the API at https://$(grep -E '^PUBLIC_HOSTNAME=' .env | cut -d= -f2-) via Caddy"
fi
docker compose "${PROFILE_ARGS[@]}" up -d --force-recreate
sleep 5
docker run --rm "leadscout:${TAG}" python -c "import leadscout; print('image version', leadscout.__version__)"
curl -fsS http://127.0.0.1:8090/health && echo

HOSTKEY="$(awk '{print $1" "$2}' /etc/ssh/ssh_host_ed25519_key.pub)"
cat <<EOF

==================================================================
CPU box ready. Save this block; paste it into each new GPU instance
before running gpu/bootstrap.sh.  (Contains a private key: keep it safe.)
------------------------------------------------------------------
export CPU_HOST='${CPU_HOST}'
export CPU_HOSTKEY='${CPU_HOST} ${HOSTKEY}'
export LLM_API_KEY='${LLM_API_KEY}'
export TUNNEL_KEY_B64='$(base64 -w0 secrets/gpu_tunnel_key)'
==================================================================
API token: grep API_TOKEN ${REPO_DIR}/.env
EOF
