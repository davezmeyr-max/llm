# Connecting a Base44 site to LeadScout

LeadScout serves its own portal at `https://<PUBLIC_HOSTNAME>/`. Base44 does one thing: when a
signed-in user clicks **Lead Research**, a Base44 backend function builds a short-lived signed link
and sends the browser there. The user lands in the portal already signed in. No Base44 pages call the
LLM, and no Base44 AI features are involved.

```
User signed in to Base44 ── clicks "Lead Research"
   │  Base44 backend function: confirms the user, signs {email|name|exp} with SSO_SECRET
   ▼
https://<PUBLIC_HOSTNAME>/sso?email=…&name=…&exp=…&sig=…
   │  LeadScout checks the signature (valid 5 min, single use), sets its own session cookie
   ▼
https://<PUBLIC_HOSTNAME>/   (Lead Research portal)
```

## 1. Base44 secrets

| Name | Value |
|---|---|
| `LEADSCOUT_URL` | `https://<PUBLIC_HOSTNAME>` (no trailing slash) |
| `LEADSCOUT_SSO_SECRET` | the `SSO_SECRET` value from `.env` on the CPU box |

Set them with the Base44 CLI (`base44 secrets set NAME value`) or ask the Base44 AI chat to add them.

## 2. Prompt to paste into the Base44 builder

> Add a "Lead Research" item to the navigation, visible only to signed-in users. It must NOT use any
> built-in AI/LLM integration. Remove any existing Lead Research pages or AI research features.
>
> Create a backend function `leadResearchLink` that:
> 1. Gets the current user with `createClientFromRequest(req)` and `base44.auth.me()`; returns 401 if
>    there is no user.
> 2. Reads secrets `LEADSCOUT_URL` and `LEADSCOUT_SSO_SECRET` inside the handler.
> 3. Sets `email` = the user's email in lowercase, `name` = the user's full name or "" , and
>    `exp` = current Unix time in seconds + 120.
> 4. Computes `sig` = lowercase hex HMAC-SHA256 of the string `email + "|" + name + "|" + exp`, keyed
>    with `LEADSCOUT_SSO_SECRET` (use Web Crypto `crypto.subtle`).
> 5. Returns `{ url: LEADSCOUT_URL + "/sso?" + URLSearchParams({email, name, exp, sig}) }`.
>
> When the user clicks "Lead Research", call `leadResearchLink` and open the returned `url` in the same
> tab (`window.location.href = url`). Never expose the secret to the browser.

## 3. Reference implementation (if you prefer to paste code)

```ts
import { createClientFromRequest } from "npm:@base44/sdk";
import { secrets } from "base44:runtime";

async function hmacHex(key: string, msg: string): Promise<string> {
  const k = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(key), { name: "HMAC", hash: "SHA-256" }, false, ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", k, new TextEncoder().encode(msg));
  return [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

Deno.serve(async (req) => {
  const base44 = createClientFromRequest(req);
  const user = await base44.auth.me();
  if (!user) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const base = secrets.get("LEADSCOUT_URL");
  const secret = secrets.get("LEADSCOUT_SSO_SECRET");
  if (!base || !secret) return Response.json({ error: "LeadScout not configured" }, { status: 500 });

  const email = String(user.email).toLowerCase();
  const name = String(user.full_name ?? "");
  const exp = String(Math.floor(Date.now() / 1000) + 120);
  const sig = await hmacHex(secret, `${email}|${name}|${exp}`);
  return Response.json({ url: `${base}/sso?${new URLSearchParams({ email, name, exp, sig })}` });
});
```

Base44's runtime conventions change; if this doesn't run as-is, use the prompt in step 2 and let the
builder adapt it. The contract that matters is the signed string and the URL parameters.

## 4. Test without Base44

On the CPU box, generate a link by hand and open it in your browser:

```bash
python3 - <<'EOF'
import hmac, hashlib, time, urllib.parse
secret = open(".env").read().split("SSO_SECRET=")[1].split()[0]
email, name, exp = "you@yourcompany.com", "You", str(int(time.time()) + 120)
sig = hmac.new(secret.encode(), f"{email}|{name}|{exp}".encode(), hashlib.sha256).hexdigest()
print("https://llm.readycomply.app/sso?" + urllib.parse.urlencode(dict(email=email, name=name, exp=exp, sig=sig)))
EOF
```

Administrators can also sign in at `https://<PUBLIC_HOSTNAME>/login` with `ADMIN_PASSWORD` from `.env`.

## Notes

- Who gets in is decided entirely by your Base44 login: anyone who can click the button gets a link.
- Every lead records the email of the person who submitted it.
- The token API (`/leads`, `/status`, `/export.csv` with `Authorization: Bearer API_TOKEN`) still works for
  scripts and other integrations.
