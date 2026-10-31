import json
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("DB_PATH", ":memory:")
os.environ.setdefault("API_TOKEN", "test-token")
os.environ.setdefault("SSO_SECRET", "sso-test-secret")
os.environ.setdefault("SESSION_SECRET", "session-test-secret")
os.environ.setdefault("ADMIN_PASSWORD", "admin-test-pw")

from leadscout import tools  # noqa: E402
from leadscout.agent import LeadAgent, _shrink_old_pages  # noqa: E402
from leadscout.db import LeadStore  # noqa: E402
from leadscout.schema import LeadProfile  # noqa: E402

# ------------------------------------------------------------------ SSRF / blocklist


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8888/search",
        "http://localhost:8090/leads",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/",
        "http://[::1]/",
        "file:///etc/passwd",
        "ftp://example.com/x",
        "https://www.linkedin.com/in/someone",
        "https://linkedin.com/company/joe-inc",
        "https://www.whitepages.com/name/Joe",
    ],
)
def test_unsafe_urls_rejected(url):
    with pytest.raises(tools.FetchBlocked):
        tools.check_url_safe(url)


def test_fetch_page_reports_block_as_error():
    out = tools.fetch_page("http://127.0.0.1:8090/")
    assert "blocked" in out["error"]


def test_redirect_to_private_ip_blocked(monkeypatch):
    calls = []

    class FakeResp:
        is_redirect = True
        headers = {"location": "http://127.0.0.1/admin"}
        status_code = 302

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def stream(self, method, url):
            calls.append(url)
            return FakeResp()

    monkeypatch.setattr(tools, "_client", lambda: FakeClient())
    # example.com resolves public; IP literals resolve to themselves
    monkeypatch.setattr(
        tools.socket,
        "getaddrinfo",
        lambda host, port: [(None, None, None, None, (host if host[0].isdigit() else "93.184.216.34", port))],
    )
    out = tools.fetch_page("https://example.com/")
    assert "blocked" in out["error"]
    assert calls == ["https://example.com/"]


def test_registry_without_token_degrades():
    assert "not configured" in tools.registry_search("Joe Inc")["error"]


def test_mx_classification(monkeypatch):
    class Ans:
        def __init__(self, items):
            self.items = items

        def __iter__(self):
            return iter(self.items)

    def resolve(self, name, rtype):
        if rtype == "MX":
            return Ans([SimpleNamespace(exchange="joeinc-com.mail.protection.outlook.com.")])
        return Ans([SimpleNamespace(strings=[b"v=spf1 include:spf.protection.outlook.com -all"])])

    monkeypatch.setattr(tools.dns.resolver.Resolver, "resolve", resolve)
    out = tools.dns_lookup("https://www.joeinc.com/about")
    assert out["domain"] == "joeinc.com"
    assert out["email_provider"] == "Microsoft 365"


# ------------------------------------------------------------------ schema


def test_finalize_adds_linkedin_search_links_and_dedupes_sources():
    p = LeadProfile(
        input_name="Joe Inc",
        company_name="Joe Inc.",
        people=[{"name": "Jane Doe", "role": "President"}],
        sources=["https://b", "https://a", "https://b"],
        confidence="certain",
    ).finalize()
    assert p.people[0].linkedin_search_url.startswith("https://www.linkedin.com/search/results/people/?keywords=Jane+Doe")
    assert p.sources == ["https://a", "https://b"]
    assert p.confidence == "low"


# ------------------------------------------------------------------ agent loop with a fake LLM


def _call(cid, name, args):
    return SimpleNamespace(id=cid, function=SimpleNamespace(name=name, arguments=json.dumps(args)))


class FakeLLM:
    """Scripted chat.completions client."""

    def __init__(self, script):
        self.script = list(script)
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.requests.append(kwargs)
        calls = self.script.pop(0)
        msg = SimpleNamespace(content="", tool_calls=calls)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


def test_agent_runs_tools_then_submits():
    llm = FakeLLM(
        [
            [_call("1", "web_search", {"query": "Joe Inc Chicago"})],
            [_call("2", "submit_profile", {"company_name": "Joe Inc", "people": [], "confidence": "high"})],
        ]
    )
    seen = {}

    def fake_search(query, max_results=8):
        seen["q"] = query
        return {"results": [{"title": "Joe Inc", "url": "https://joeinc.example"}]}

    agent = LeadAgent(client=llm, tool_funcs={"web_search": fake_search})
    profile = agent.run("Joe Inc", "Chicago")
    assert seen["q"] == "Joe Inc Chicago"
    assert profile.input_name == "Joe Inc"
    assert profile.confidence == "high"
    # private bookkeeping keys never go over the wire
    for m in llm.requests[1]["messages"]:
        assert not any(k.startswith("_") for k in m)


def test_agent_recovers_from_invalid_submit():
    llm = FakeLLM(
        [
            [_call("1", "submit_profile", {"people": [{"role": "CEO"}]})],  # missing person name
            [_call("2", "submit_profile", {"company_name": "Joe Inc"})],
        ]
    )
    profile = LeadAgent(client=llm, tool_funcs={}).run("Joe Inc")
    assert profile.company_name == "Joe Inc"
    tool_msgs = [m for m in llm.requests[1]["messages"] if m["role"] == "tool"]
    assert "failed validation" in tool_msgs[0]["content"]


def test_agent_forces_submit_at_budget(monkeypatch):
    from leadscout import agent as agent_mod

    monkeypatch.setattr(agent_mod.settings.__class__, "__setattr__", object.__setattr__)
    object.__setattr__(agent_mod.settings, "max_steps", 2)
    try:
        llm = FakeLLM(
            [
                [_call("1", "web_search", {"query": "a"})],
                [_call("2", "web_search", {"query": "b"})],
                [_call("3", "submit_profile", {"company_name": "Joe Inc"})],
            ]
        )
        LeadAgent(client=llm, tool_funcs={"web_search": lambda query, max_results=8: {"results": []}}).run("Joe Inc")
        last = llm.requests[-1]
        assert last["tool_choice"]["function"]["name"] == "submit_profile"
        assert [t["function"]["name"] for t in last["tools"]] == ["submit_profile"]
    finally:
        object.__setattr__(agent_mod.settings, "max_steps", 24)


def test_old_pages_are_shrunk():
    msgs = [
        {"role": "tool", "_tool": "fetch_page", "content": json.dumps({"url": f"u{i}", "text": "x" * 5000})}
        for i in range(5)
    ]
    _shrink_old_pages(msgs)
    sizes = [len(json.loads(m["content"])["text"]) for m in msgs]
    assert sizes[:2] == [1500 + len(" …[older page shortened]")] * 2
    assert sizes[2:] == [5000, 5000, 5000]


# ------------------------------------------------------------------ queue


def test_queue_lifecycle_and_retry_limit():
    s = LeadStore(":memory:")
    lid = s.add("Joe Inc", "Chicago")
    lead = s.claim_next()
    assert lead["id"] == lid and lead["attempts"] == 1
    assert s.claim_next() is None
    s.fail(lid, "boom", lead["attempts"])
    assert s.get(lid)["status"] == "queued"
    for _ in range(2):
        lead = s.claim_next()
        s.fail(lid, "boom", lead["attempts"])
    assert s.get(lid)["status"] == "failed"
    assert s.retry(lid)
    lead = s.claim_next()
    s.complete(lid, {"input_name": "Joe Inc"}, [{"tool": "x"}])
    assert s.get(lid)["profile"]["input_name"] == "Joe Inc"


def test_running_requeued_on_restart():
    s = LeadStore(":memory:")
    s.add("A")
    s.claim_next()
    assert s.requeue_running() == 1
    assert s.counts() == {"queued": 1}


# ------------------------------------------------------------------ API


def test_api_auth_and_flow():
    from fastapi.testclient import TestClient

    from leadscout import api

    c = TestClient(api.app)
    assert c.post("/leads", json={"company": "Joe Inc"}).status_code == 401
    h = {"Authorization": "Bearer test-token"}
    r = c.post("/leads/bulk", json={"leads": [{"company": "Joe Inc", "hints": "Chicago"}, {"company": "Acme LLC"}]}, headers=h)
    assert r.status_code == 201 and len(r.json()["ids"]) == 2
    lid = r.json()["ids"][0]
    api.store.claim_next()
    profile = LeadProfile(input_name="Joe Inc", company_name="Joe Inc", people=[{"name": "Jane Doe", "role": "CEO"}])
    api.store.complete(lid, profile.finalize().model_dump(), [])
    csv_text = c.get("/export.csv", headers=h).text
    assert "Jane Doe (CEO)" in csv_text
    assert c.get(f"/leads/{lid}", headers=h).json()["status"] == "done"


def test_api_docs_not_published():
    from fastapi.testclient import TestClient

    from leadscout import api

    c = TestClient(api.app)
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert c.get(path).status_code == 404


# ------------------------------------------------------------------ web portal


def _sso_url(email="jane@cis.example", name="Jane Doe", exp_offset=60, secret="sso-test-secret"):
    import hashlib
    import hmac
    import time
    from urllib.parse import urlencode

    exp = int(time.time()) + exp_offset
    sig = hmac.new(secret.encode(), f"{email}|{name}|{exp}".encode(), hashlib.sha256).hexdigest()
    return "/sso?" + urlencode({"email": email, "name": name, "exp": exp, "sig": sig})


def _client():
    from fastapi.testclient import TestClient

    from leadscout import api

    return TestClient(api.app, follow_redirects=False)


def test_portal_redirects_to_login_without_session():
    c = _client()
    r = c.get("/")
    assert r.status_code == 303 and r.headers["location"] == "/login"
    assert c.get("/ui/api/leads").status_code == 401


def test_sso_signs_in_and_is_single_use():
    c = _client()
    url = _sso_url()
    r = c.get(url)
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert "httponly" in r.headers["set-cookie"].lower()
    assert c.get("/").status_code == 200
    assert c.get("/ui/api/me").json()["email"] == "jane@cis.example"
    c2 = _client()
    assert c2.get(url).status_code == 401  # replay rejected


@pytest.mark.parametrize(
    "kwargs",
    [{"secret": "wrong"}, {"exp_offset": -10}, {"exp_offset": 3600}, {"email": "not-an-email"}],
)
def test_sso_rejects_bad_links(kwargs):
    assert _client().get(_sso_url(**kwargs)).status_code == 401


def test_tampered_session_cookie_rejected():
    c = _client()
    c.get(_sso_url(email="a@b.example"))
    from leadscout.web import COOKIE

    good = c.cookies.get(COOKIE)
    body, sig = good.rsplit(".", 1)
    c.cookies.set(COOKIE, body + "." + ("0" * len(sig)))
    assert c.get("/ui/api/me").status_code == 401


def test_ui_post_requires_csrf_header_and_records_submitter():
    c = _client()
    c.get(_sso_url(email="bob@cis.example", name="Bob"))
    body = {"leads": [{"company": "Lakeshore Dental", "hints": "Chicago"}]}
    assert c.post("/ui/api/leads", json=body).status_code == 403
    r = c.post("/ui/api/leads", json=body, headers={"X-Requested-With": "leadscout"})
    assert r.status_code == 201
    rows = c.get("/ui/api/leads").json()
    assert any(x["company"] == "Lakeshore Dental" and x["submitted_by"] == "bob@cis.example" for x in rows)
    csv_resp = c.get("/ui/api/export.csv")
    assert csv_resp.status_code == 200 and "attachment" in csv_resp.headers["content-disposition"]


def test_admin_password_login_and_lockout():
    c = _client()
    h = {"X-Requested-With": "leadscout", "X-Forwarded-For": "203.0.113.9"}
    assert c.post("/login", json={"password": "admin-test-pw"}, headers={"X-Requested-With": "leadscout"}).status_code == 200
    assert c.get("/ui/api/me").json()["email"] == "admin"
    bad = _client()
    codes = [bad.post("/login", json={"password": "nope"}, headers=h).status_code for _ in range(11)]
    assert codes[:10] == [401] * 10 and codes[10] == 429


def test_logout_clears_session():
    c = _client()
    c.get(_sso_url(email="z@cis.example"))
    c.get("/logout")
    assert c.get("/ui/api/me").status_code == 401
