#!/usr/bin/env bash
# Run on a fresh GPU instance (Hostinger RTX PRO 6000 96 GB, Vultr L40S, etc.).
# 1. Paste the export block printed by setup-cpu-box.sh
# 2. curl -fsSL <raw URL of this file> | bash      (or copy the file over and run it)
#
# Starts vLLM on 127.0.0.1:8000 (never exposed publicly) and opens a reverse SSH tunnel
# so the CPU box sees it on its own 127.0.0.1:8001. Do NOT add an "exposed service" in hPanel.
set -euo pipefail

: "${CPU_HOST:?paste the export block from setup-cpu-box.sh first}"
: "${CPU_HOSTKEY:?missing CPU_HOSTKEY}"
: "${LLM_API_KEY:?missing LLM_API_KEY}"
: "${TUNNEL_KEY_B64:?missing TUNNEL_KEY_B64}"

MODEL="${MODEL:-Qwen/Qwen3.6-27B}"          # bf16 weights ~55 GB; fits a 96 GB card with room for KV cache
MAX_LEN="${MAX_LEN:-65536}"
GPU_UTIL="${GPU_UTIL:-0.92}"
TUNNEL_USER="${TUNNEL_USER:-lstunnel}"
WORK="${WORK:-$HOME/leadscout-gpu}"
mkdir -p "$WORK" && cd "$WORK"

echo "==> GPU"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader

echo "==> SSH tunnel key (pinned host key, no TOFU)"
install -d -m 700 "$HOME/.ssh"
echo "$TUNNEL_KEY_B64" | base64 -d > "$HOME/.ssh/leadscout_tunnel"
chmod 600 "$HOME/.ssh/leadscout_tunnel"
echo "$CPU_HOSTKEY" > "$HOME/.ssh/leadscout_known_hosts"

echo "==> vLLM"
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
[[ -d .venv ]] || uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -q vllm
.venv/bin/python -c "import vllm; print('vllm', vllm.__version__)"

echo "==> Starting vLLM (first start downloads the model; takes several minutes)"
cat > serve.sh <<EOF
#!/usr/bin/env bash
exec "$WORK/.venv/bin/vllm" serve "$MODEL" \\
  --host 127.0.0.1 --port 8000 \\
  --served-model-name leadscout \\
  --api-key "$LLM_API_KEY" \\
  --max-model-len $MAX_LEN \\
  --gpu-memory-utilization $GPU_UTIL \\
  --kv-cache-dtype fp8 \\
  --language-model-only \\
  --reasoning-parser qwen3 \\
  --enable-auto-tool-choice --tool-call-parser qwen3_coder
EOF
chmod +x serve.sh
pkill -f "vllm serve" 2>/dev/null || true
setsid nohup ./serve.sh > vllm.log 2>&1 < /dev/null &

echo "==> Starting reverse tunnel to ${CPU_HOST} (auto-reconnects)"
cat > tunnel.sh <<EOF
#!/usr/bin/env bash
while true; do
  ssh -N -i "$HOME/.ssh/leadscout_tunnel" \\
      -o UserKnownHostsFile="$HOME/.ssh/leadscout_known_hosts" -o StrictHostKeyChecking=yes \\
      -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \\
      -R 127.0.0.1:8001:127.0.0.1:8000 "${TUNNEL_USER}@${CPU_HOST}"
  sleep 5
done
EOF
chmod +x tunnel.sh
pkill -f "leadscout_tunnel" 2>/dev/null || true
setsid nohup ./tunnel.sh > tunnel.log 2>&1 < /dev/null &

echo "==> Waiting for the model to load"
for _ in $(seq 1 120); do
  if curl -fsS -H "Authorization: Bearer $LLM_API_KEY" http://127.0.0.1:8000/v1/models >/dev/null 2>&1; then
    echo "vLLM is up. The CPU box worker will start processing queued leads within a few seconds."
    echo "Logs: $WORK/vllm.log  $WORK/tunnel.log"
    exit 0
  fi
  if ! pgrep -f "vllm serve" >/dev/null; then
    echo "vLLM exited. Last log lines:"; tail -n 40 vllm.log; exit 1
  fi
  sleep 15
done
echo "Still loading after 30 min; check $WORK/vllm.log"; exit 1
