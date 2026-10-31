# LeadScout

Self-hosted lead research. Give it a company name ("Joe Inc", hints "Chicago, IL"); it searches the web,
reads the company site, pulls Secretary of State records (officers, registered agent, status), checks MX
records for the email platform, and returns a structured profile with sources.

```
 Always-on CPU box (Hostinger KVM 2, ~$10-15/mo)          GPU instance (on demand, ~$0.65/hr)
 ┌──────────────────────────────────────────────┐        ┌────────────────────────────────────┐
 │ SearXNG :8888   API :8090   worker   SQLite  │◄─ssh ──│ vLLM  Qwen3.6-27B  127.0.0.1:8000  │
 │ LLM appears on 127.0.0.1:8001 via tunnel     │  -R    │ (nothing exposed publicly)         │
 └──────────────────────────────────────────────┘        └────────────────────────────────────┘
```

The GPU box dials out to the CPU box, so the model is never exposed to the internet.

## 1. CPU box (once)

Ubuntu 22.04/24.04 VPS. Copy this folder over, then:

```bash
sudo ./deploy/setup-cpu-box.sh <public-ip-of-this-box>
```

It installs Docker, generates secrets into `.env`, creates a locked-down `lstunnel` SSH user that can only
open the one reverse port, builds and starts the stack, and prints an **export block**. Save that block in
your password manager; it contains the tunnel private key.

Optional, in `.env` then `docker compose up -d --force-recreate`:
- `OPENCORPORATES_API_TOKEN` for Secretary of State data. Without it the agent uses web search for registrations.
- `NOTIFY_WEBHOOK_URL` (Teams/Slack webhook or ntfy topic) for "deploy the GPU" and "destroy the GPU" notices.
- `FETCH_USER_AGENT` with your real contact address.

## 2. Queue leads (any time, GPU can be off)

```bash
TOKEN=$(grep ^API_TOKEN .env | cut -d= -f2)
curl -s -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"leads":[{"company":"Joe Inc","hints":"Chicago, IL"},{"company":"Acme Plumbing LLC","hints":"Naperville IL"}]}' \
  http://127.0.0.1:8090/leads/bulk
```

The API listens on 127.0.0.1 only. From your desk use `ssh -L 8090:127.0.0.1:8090 cpu-box`, or set
`API_BIND` to the box's WireGuard IP.

## 3. Run a batch

1. Deploy a GPU instance in hPanel (RTX PRO 6000, 96 GB). Do **not** add an "exposed service".
2. SSH in, paste the export block, then run `gpu/bootstrap.sh` (copy it over or curl it from your repo).
3. The model downloads and loads (first start ~10-20 min). The worker starts processing automatically.
4. When the queue drains you get the "batch done" notice. **Destroy the instance in hPanel.**

Hostinger GPU instances have no stop button: they bill every hour they exist and are only stopped by
destroying them. They are also deleted without warning if account credits hit zero, so keep credits
topped up during a batch. Nothing on the GPU box needs to persist; results live on the CPU box, and an
interrupted lead is requeued automatically.

## 4. Get results

| Endpoint | What |
|---|---|
| `GET /status` | Queue counts and whether the LLM is online |
| `GET /leads?status=done` | Finished profiles (JSON) |
| `GET /leads/{id}` | One profile plus the tool-call trace |
| `POST /leads/{id}/retry` | Re-run a lead |
| `GET /export.csv` | Flat CSV for CRM import |

## Connect your website (optional)

Set `PUBLIC_HOSTNAME` in `.env` (DNS A record pointing at this box, ports 80/443 open) and re-run
`setup-cpu-box.sh`. Caddy publishes the API over HTTPS with an automatic certificate. Your site's
backend calls it with the API token. For Base44 see [integrations/base44.md](integrations/base44.md).

## Guardrails built in

- Business facts only. The prompt forbids home addresses, personal phones, family and other personal-life details.
- LinkedIn, social networks and people-search sites are blocked at the fetch layer. Each person gets a
  `linkedin_search_url` a human can click instead.
- The page fetcher refuses non-public IPs (including after redirects), so web content cannot steer it at
  SearXNG, the API or cloud metadata endpoints. Fetched pages are treated as untrusted data.
- All tools are read-only.

## Test locally

```bash
cd app && pip install -r requirements.txt pytest && python -m pytest -q
LLM_BASE_URL=http://127.0.0.1:8001/v1 LLM_API_KEY=... python -m leadscout.cli "Joe Inc" --hints "Chicago, IL" --trace
```

## Tuning

- Hostinger RTX PRO 6000 is a **shared** GPU: pick the **2 Cores / 64 GB RAM** size. The platform parks your GPU
  memory in system RAM when another tenant needs the card, so the defaults use the NVFP4 build (~18 GB) and claim
  45% of the GPU. On a dedicated GPU with plenty of RAM: `MODEL=Qwen/Qwen3.6-27B QUANT= GPU_UTIL=0.92`.
- `AGENT_MAX_STEPS` (default 24) caps tool calls per lead.
- `LLM_THINKING=true` turns on Qwen's reasoning mode: slower, sometimes better on ambiguous names.

Version is in `app/leadscout/__init__.py`. Bump it for every change; the setup script tags the image with it.
