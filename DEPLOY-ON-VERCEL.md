# Deploy Bainbot on Vercel

This package contains the frontend, Python backend, database support and integrations. Secrets are deliberately blank. Use newly rotated keys, because the earlier keys were shared in chat.

## 1. Upload to GitHub

Extract the ZIP. Upload the CONTENTS of `bainbot-project` to a private GitHub repository. The root must contain `main.py`, `vercel.json`, `requirements.txt`, `backend/` and `dist/`. Include `.github/`, `.gitignore` and `.env.example`. Do not upload the ZIP as the application, `.env`, or database files.

## 2. Get the Supabase database connection

The project URL you supplied (`https://rodnekigvjnluypuzcmq.supabase.co`) identifies the project but is NOT a database connection string.

Open that project's Supabase dashboard → **Connect → Transaction pooler**. Copy the PostgreSQL URI, insert its database password, URL-encode reserved password characters, and retain SSL configuration. Set it as `DATABASE_URL` in Vercel. Never paste it into public code or chat.

Example shape only:

```text
postgresql://postgres.PROJECT_REF:ENCODED_PASSWORD@POOLER_HOST:6543/postgres?sslmode=require
```

Use a dedicated Bainbot database/project. Disable Supabase's **Data API** on that dedicated project: the app connects directly to PostgreSQL and does not create RLS policies for the custom auth tables. Do not disable APIs on a project used by another product. This implementation uses custom Python authentication, not Supabase Auth; users appear in the application's `users` table.

## 3. Import into Vercel

Import the GitHub repository. Choose the **FastAPI** framework and repository root. Leave build/output overrides unset; do not use `dist` as the output directory. Python 3.12 and the function entrypoint are included. `vercel.json` gives the function 180 seconds; the bounded workflow stops after 120 seconds. Use Fluid compute and a plan/configuration that permits the declared duration.

## 4. Enter environment variables

Add the following under Vercel → Project → Settings → Environment Variables for the deployment environment you intend to use.

| Name | Value |
|---|---|
| `DATABASE_URL` | Your real Supabase transaction-pooler URI |
| `PUBLIC_ORIGIN` | `https://YOUR-PROJECT.vercel.app` (replace with your final URL; no trailing slash) |
| `COOKIE_SECURE` | `true` |
| `REQUIRE_EMAIL_VERIFICATION` | `true` |
| `LLM_BASE_URL` | `https://openrouter.ai/api/v1` |
| `LLM_API_KEY` | Your NEW OpenRouter key |
| `LLM_MODEL` | `openrouter/free` |
| `LLM_TIMEOUT_SECONDS` | `35` |
| `LLM_OUTPUT_LIMIT` | `1200` |
| `RESEND_API_KEY` | Your NEW Resend key |
| `EMAIL_FROM` | `Bainbot <onboarding@resend.dev>` for your initial test |
| `EMAIL_TEST_RECIPIENT` | `kiskobiswal@gmail.com` for your initial test |
| `SEARCH_PROVIDER` | `tinyfish` |
| `TINYFISH_API_KEY` | Your NEW TinyFish key |
| `TAVILY_API_KEY` | Optional: your NEW Tavily key if switching to Tavily |
| `FREE_DAILY_DRAFTS` | `20` |
| `FREE_DAILY_SEARCHES` | `20` |
| `GLOBAL_DAILY_REQUESTS` | `40` |

To use Tavily instead, set `SEARCH_PROVIDER=tavily` and supply `TAVILY_API_KEY`. The model key always belongs in `LLM_API_KEY`; Tavily is not the model provider. No SMTP settings are necessary when using Resend.

## 5. Deploy and set the final URL

Deploy once to obtain the Vercel URL. Replace `PUBLIC_ORIGIN` with that exact HTTPS origin and redeploy. This URL must be set before registration emails are sent. When adding a custom domain later, update it and redeploy. Use separate databases and keys for preview deployments.

## 6. Test your own account

1. Visit `/api/health`: database should be `postgresql`; model/search/email flags should be true. Flags check configuration, not provider credentials.
2. Open `/app` signed out. It should redirect to `/login`.
3. Register using `kiskobiswal@gmail.com`.
4. Open the verification email, click its link, then click **Verify email**.
5. Log in. Open an agent, choose **Agent workflow**, and enter: “Research recent trends in customer support and draft a LinkedIn post with sources.” Approve research when prompted.
6. The model may search the web, read results and write the draft. Open Tasks to review it. No social post is published.
7. Use **Chat only** for writing from supplied information; use **Search only** for search results without a model call.
8. Test logout and password reset.

Resend's test sender only sends to the account owner's email. The test-recipient setting enforces this without redirecting anyone else's verification token. Other users cannot register successfully through email verification until you finish step 7 below. SMTP or the Resend API accepting an email is not a guarantee of inbox delivery; check spam and Resend delivery logs.

## 7. Open registration to other users

Verify a domain you own under Resend → Domains. Set `EMAIL_FROM` to an address on that verified domain (e.g. `Bainbot <hello@yourdomain.com>`), clear `EMAIL_TEST_RECIPIENT`, and redeploy. Gmail is your Resend login, not your sender domain. Use two accounts to confirm separate workspaces. Team invitation links are still shared manually.

## Troubleshooting

- Database unavailable: check the pooler URI, password, SSL and whether the Supabase project is running.
- Cross-origin request rejected: `PUBLIC_ORIGIN` must exactly match the URL used in the browser, with no trailing slash.
- Verification email fails: check Resend key, sender verification and owner-only test restrictions. Failed signup email requests roll back the new account; you can retry.
- Model request fails: check key, selected model, credits and free-tier availability. Switch to Chat only if the selected model cannot handle tools.
- Workflow reaches its step limit: narrow the task. Maximum three model calls and two searches per run.
- Free usage exhausted: wait for provider limits to reset or adjust your plan; creating additional Bainbot users does not create additional provider quota.
- No external post/email was sent: external business integrations are not present; this version completes research and writing, not publishing or outreach delivery.

Updates: push code to your connected GitHub branch; Vercel redeploys. Environment changes also require redeployment. Keep the same database URL to retain data, and back up before schema changes.
