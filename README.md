# Bainbot — deployable free beta

**Start with [DEPLOY-ON-VERCEL.md](DEPLOY-ON-VERCEL.md).** It contains the exact settings for your chosen providers, your own-account email test and later public signup.

## Implemented

- Responsive Bainbot frontend with clean URLs, fixed sidebar and agent chat/tasks.
- Public registration creates an isolated workspace; email verification is required by default.
- Login-protected dashboard and backend APIs, secure sessions, password reset, resend verification and logout.
- Owner/member permissions, per-agent viewer/operator access and manual invitation links.
- Supabase PostgreSQL storage, with SQLite for local tests.
- OpenRouter-compatible chat/writing adapter. `openrouter/free` is the initial model setting.
- TinyFish Search API or Tavily Search API, selected with `SEARCH_PROVIDER`.
- Resend email API for verification and password resets, with SMTP retained as an alternative.
- Free plan, usage limits, task review, overview and agent settings.
- A bounded single-prompt research/writing agent loop: model → optional search → model response → saved draft.

## Three task modes

**Agent workflow** (default): model decides whether it needs public web search. A run allows up to three model calls and two searches, with a 120-second overall limit. Research approval is requested before the run when required by agent settings. Research-blocked agents can still write from supplied facts. Permissions are checked before each operation. Sources consulted are appended. Written results become Pending approval or Ready according to the agent's draft policy. Failed runs are recorded as Failed tasks. A hard host termination can leave a Running task; there is no durable queue/recovery worker yet.

**Chat only**: one model call without web tools.

**Search only**: one TinyFish or Tavily search, saved as completed research. Works without a model API.

Research/writing is the supported automation scope. The workflow never executes arbitrary tools, browser actions or external writes. TinyFish's Search API is integrated; its paid browser/agent/payment APIs are not. Agent-to-agent delegation, schedulers, social publishing, campaign email sending, CRM writes, file analysis, image/video generation, paid billing, MFA and Google login are not implemented. Resend is used for authentication mail only, not marketing outreach. Approval of a draft is not execution of a business action.

## Provider setup

Configuration is read exclusively from server environment variables. No user-supplied API secret is included in this archive. Rotate the earlier exposed keys and enter replacements in Vercel. See `.env.example` and the deployment guide.

- Model: `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`.
- Search: `SEARCH_PROVIDER=tinyfish` plus `TINYFISH_API_KEY`, or `tavily` plus `TAVILY_API_KEY`.
- Email: `RESEND_API_KEY`, `EMAIL_FROM`, `PUBLIC_ORIGIN`. During owner-only testing, also set `EMAIL_TEST_RECIPIENT`.
- Storage: `DATABASE_URL` (PostgreSQL URI, not the Supabase project URL).
- HTTPS: exact `PUBLIC_ORIGIN`, `COOKIE_SECURE=true`.

Free model routing may select different models and can be capacity/rate limited. For repeatable workflows, later choose a fixed tool-capable model ID. Model calls and searches in a workflow each consume quota. Provider costs and account-wide limits are separate from Bainbot's free user plan.

## Local run

Use Python 3.12. Create a virtual environment, activate it, and install:

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

Copy `.env.example` to `.env` and fill the secrets. Leave `DATABASE_URL` empty for local SQLite. Set `PUBLIC_ORIGIN=http://localhost:8000` and `COOKIE_SECURE=false`. For private local tests without email only, explicitly set `REQUIRE_EMAIL_VERIFICATION=false` (accounts created this way stay activated). Start:

```bash
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Open `http://localhost:8000/register`. Use localhost consistently so origin checks match.

## Existing installations

Back up before upgrading. Startup migrates the older single-workspace schema idempotently: existing users, agents and invitations stay in workspace `legacy`; new public registrations get distinct workspace IDs. Existing accounts remain activated. The migration does not delete old data. Supabase Auth is not used. Each email belongs to one workspace; joining multiple workspaces with one account is not yet supported. Members assigned to an agent share its conversations.

## Tests

```bash
python -m pytest backend -q
node --check dist/app.js
node --check dist/auth.js
node scripts/check_frontend.cjs
```

PostgreSQL tests require `TEST_DATABASE_URL` pointing to a disposable database. GitHub Actions creates one. Never use a customer database for tests. Provider contracts are mocked; actual service credentials and deployed behavior must be verified after configuration. See `TEST-RESULTS.md`.

## Files

- `backend/main.py`: auth, tenant authorization, agents, tasks, mail and workflow endpoint.
- `backend/provider.py`: OpenRouter/OpenAI-compatible model calls.
- `backend/search.py`: TinyFish/Tavily search adapters.
- `backend/workflow.py`: constrained tool execution loop.
- `backend/database.py`: PostgreSQL/SQLite compatibility.
- `dist/`: frontend and assets.
- `main.py`, `vercel.json`, `.python-version`, `requirements.txt`: deployment.
- `.env.example`: configuration template.
- `.github/workflows/test.yml`: CI.

## Operations and limits

The included environment template sets 20 draft/model attempts and 20 search attempts per workspace per UTC day, with 40 combined provider attempts across the deployment. Failed attempts count. These can be changed with `FREE_DAILY_DRAFTS`, `FREE_DAILY_SEARCHES`, and `GLOBAL_DAILY_REQUESTS`. They are request caps, not financial budgets. Free provider allowances are shared by all users.

Set provider-side spending caps and monitor errors/usage. Maintain independent database backups. Tokens in verification/reset/invitation query strings should be redacted from hosting logs. Verification and reset tokens are removed from the address bar on load, with a no-referrer policy. A broader security/operational review is still needed before a large public launch.

## Reference documentation

- https://openrouter.ai/docs/quickstart
- https://openrouter.ai/openrouter/free
- https://docs.tinyfish.ai/search-api/reference
- https://docs.tavily.com/documentation/api-reference/endpoint/search
- https://resend.com/docs/api-reference/emails/send-email
- https://resend.com/docs/knowledge-base/403-error-resend-dev-domain
- https://vercel.com/docs/frameworks/backend/fastapi
- https://supabase.com/docs/guides/database/connecting-to-postgres
