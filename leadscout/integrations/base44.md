# Connecting a Base44 site to LeadScout

The browser never talks to LeadScout directly and never sees the API token.

```
Visitor (logged in to your Base44 site)
   │  page calls a Base44 backend function
   ▼
Base44 backend function ── checks the user is logged in, adds the secret token
   │  HTTPS
   ▼
https://<PUBLIC_HOSTNAME>  (Caddy on the CPU box)  →  LeadScout API
```

## 1. Base44 secrets

In your Base44 app's settings, add two secrets / environment variables:

| Name | Value |
|---|---|
| `LEADSCOUT_API_URL` | `https://<PUBLIC_HOSTNAME>` (no trailing slash) |
| `LEADSCOUT_API_TOKEN` | the `API_TOKEN` value from `.env` on the CPU box |

## 2. Prompt to paste into the Base44 builder

> Add a "Lead Research" section to this app, visible only to logged-in users.
>
> Backend: create backend functions that call an external API. Read the base URL from the secret
> `LEADSCOUT_API_URL` and a bearer token from the secret `LEADSCOUT_API_TOKEN`. Send the header
> `Authorization: Bearer <token>` on every request. Every function must first confirm the caller is a
> logged-in user and return 401 otherwise. Never send the token or the URL to the browser.
>
> Functions:
> 1. `submitLeads(leads)` → `POST {URL}/leads/bulk` with JSON body `{"leads": [{"company": string, "hints": string}]}`
>    (1–500 items; company 2–200 chars; hints up to 500 chars). Returns `{"ids": [int]}`.
> 2. `listLeads(status?)` → `GET {URL}/leads?status=<queued|running|done|failed>&limit=200` (status optional).
>    Returns an array of `{id, company, hints, status, attempts, profile, error, created_at, updated_at}`.
> 3. `getLead(id)` → `GET {URL}/leads/{id}`. Returns one lead including `profile`.
> 4. `retryLead(id)` → `POST {URL}/leads/{id}/retry`.
> 5. `leadStatus()` → `GET {URL}/status`. Returns `{"queue": {status: count}, "llm_online": bool}`.
> 6. `exportCsv()` → `GET {URL}/export.csv`, returned to the user as a file download `leads.csv`.
>
> Pages:
> - **New research**: a form with Company name and Hints (city/state, website, industry), plus a
>   "Bulk add" textarea where each line is `Company name | hints`. Submit calls `submitLeads`.
> - **Leads**: a table (company, status badge, confidence, updated) with a status filter, auto-refresh
>   every 15 seconds while any lead is queued or running, a Retry button on failed rows, and an
>   "Export CSV" button. Show a small banner from `leadStatus()`: "Research engine online" or
>   "Research engine offline: leads will wait in the queue".
> - **Lead detail**: render `profile` with these sections: Summary (company_name, website link,
>   industry, employee_estimate, business_address, business_phone, confidence); Registrations table
>   (jurisdiction, entity_number, status, entity_type, formation_date, registered_agent, source_url
>   link); People table (name, role, source_url link, and a "Search LinkedIn" button that opens
>   `linkedin_search_url` in a new tab); IT signals (email_provider, mx_records, notes);
>   Open questions; Sources as links.

## 3. Test it

From the CPU box, before involving Base44:

```bash
TOKEN=$(grep ^API_TOKEN .env | cut -d= -f2)
curl -s -H "Authorization: Bearer $TOKEN" https://<PUBLIC_HOSTNAME>/status
```

Expect `{"queue": {...}, "llm_online": ...}`. Without the header you should get `401`.

## Notes

- All signed-in users of the site share one lead list. If you need per-user lists, that's a small
  change (store the submitting user on each lead); ask for it.
- Rotating the token: change `API_TOKEN` in `.env`, run `docker compose up -d --force-recreate api`,
  and update the Base44 secret.
