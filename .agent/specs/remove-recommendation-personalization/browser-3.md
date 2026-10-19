# Browser/manual feasibility — round 3

Limited evaluation of AC1, AC4, and AC8 only. Read `spec.md`, `VERIFY.md`, and
`eval-2.md` before testing. No backend tests, DB commands, migrations, model calls,
authentication bypasses, or app/config edits were performed.

## Setup

No listeners existed on 3000/3001/8000 initially. Started only a host frontend:

```text
. ./.agent/specs/remove-recommendation-personalization/artifacts/browser-3-start.ps1
{
    "AUTH_SECRET_PRESENT":  true,
    "AUTH_SECRET_SOURCE":  "existing root .env (secret only; no OAuth credentials imported)",
    "AUTH_GOOGLE_ID_PRESENT":  false,
    "AUTH_GOOGLE_SECRET_PRESENT":  false,
    "PORT":  3000
}
STARTED_FRONTEND_PID=14468
```

The script starts installed Next.js with `dev --turbopack --hostname 127.0.0.1
--port 3000`. Existing root secret was reused in the child process only; no values
were printed and no env files were modified. Root Google credentials were **not**
imported: VERIFY requires approval to reuse the production client. No backend or
Compose stack was started. Logs: `artifacts/browser-3-frontend.stdout.log` and
`artifacts/browser-3-frontend.stderr.log`.

Before opening the browser, set `PLAYWRIGHT_MCP_OUTPUT_DIR` to the absolute path of
this spec's `artifacts` directory. All commands used
`playwright-cli -s=remove-recommendation-personalization`.

## Results

These are browser/manual verdicts, not verdicts on builders' concurrent unit-test work.
UNVERIFIED counts as failure; observing an auth gate does not verify protected workflows.

| Criterion | Verdict | Exact command and observed output |
|---|---|---|
| AC1 | UNVERIFIED | `playwright-cli -s=remove-recommendation-personalization goto http://localhost:3000/decks/00000000-0000-4000-8000-000000000001/coach` → `Page URL: http://localhost:3000/signin?callbackUrl=%2Fdecks%2F00000000-0000-4000-8000-000000000001%2Fcoach`; `snapshot` → `paragraph: AI-powered Commander deck builder. Sign in to get started.` and `button "Continue with Google"`. No authorized deck or answer was reached. |
| AC4 | UNVERIFIED | `playwright-cli -s=remove-recommendation-personalization open http://localhost:3000/preferences` → `Page URL: http://localhost:3000/signin?callbackUrl=%2Fpreferences`; `snapshot` → `link "Preferences"` with `/url: /preferences`, but heading `MTG Helper` and `button "Continue with Google"`. The retained nav link is verified, not the protected page's exact empty-state copy or absence of settings/requests. |
| AC8 | UNVERIFIED | `playwright-cli -s=remove-recommendation-personalization goto http://localhost:3000/decks/00000000-0000-4000-8000-000000000001/build` → `Page URL: http://localhost:3000/signin?callbackUrl=%2Fdecks%2F00000000-0000-4000-8000-000000000001%2Fbuild`; `snapshot` → `button "Continue with Google"`. No Builder suggestion, Reject, New Cards, or Discover action was reached. |

Independent HTTP confirmation (no redirect following):

```text
curl.exe -sS -o NUL -w 'HTTP=%{http_code} REDIRECT=%{redirect_url}\n' http://localhost:3000/preferences
HTTP=307 REDIRECT=http://localhost:3000/signin?callbackUrl=%2Fpreferences
curl.exe -sS -o NUL -w 'HTTP=%{http_code} REDIRECT=%{redirect_url}\n' http://localhost:3000/decks/00000000-0000-4000-8000-000000000001/coach
HTTP=307 REDIRECT=http://localhost:3000/signin?callbackUrl=%2Fdecks%2F00000000-0000-4000-8000-000000000001%2Fcoach
curl.exe -sS -o NUL -w 'HTTP=%{http_code} REDIRECT=%{redirect_url}\n' http://localhost:3000/decks/00000000-0000-4000-8000-000000000001/build
HTTP=307 REDIRECT=http://localhost:3000/signin?callbackUrl=%2Fdecks%2F00000000-0000-4000-8000-000000000001%2Fbuild
```

Edge probes:

```text
playwright-cli -s=remove-recommendation-personalization goto http://localhost:3000/decks/not-a-uuid/coach
Page URL: http://localhost:3000/signin?callbackUrl=%2Fdecks%2Fnot-a-uuid%2Fcoach
playwright-cli -s=remove-recommendation-personalization goto http://localhost:3000/decks/not-a-uuid/build
Page URL: http://localhost:3000/signin?callbackUrl=%2Fdecks%2Fnot-a-uuid%2Fbuild
playwright-cli -s=remove-recommendation-personalization resize 375 812
await page.setViewportSize({ width: 375, height: 812 });
playwright-cli -s=remove-recommendation-personalization goto http://localhost:3000/preferences
Page URL: http://localhost:3000/signin?callbackUrl=%2Fpreferences
```

Screenshots captured **and visually inspected**: `artifacts/browser-3-preferences.png`,
`browser-3-assistant.png`, `browser-3-builder.png`, and
`browser-3-preferences-mobile.png`. Each shows the Google sign-in screen, not the
requested protected page. Matching `browser-3-*-console.txt` files captured using
`console`: desktop Preferences reported `Total messages: 2 (Errors: 1, Warnings: 0)`
with `404 (Not Found) @ http://localhost:3000/favicon.ico:0`; subsequent pages reported
`Total messages: 1 (Errors: 0, Warnings: 0)` (React DevTools info only).

`requests` on Preferences returned `Note: 17 static requests not shown`; no retired
network request was observed on the **sign-in** page. This does not establish
protected-page request behavior. One optional compound DOM eval failed because of
PowerShell argument quoting; snapshot evidence above does not depend on it. A
separate `eval '() => location.href'` succeeded and returned
`"http://localhost:3000/signin?callbackUrl=%2Fpreferences"`.

## Exact blocker / what a human needs to supply

Genuine authenticated navigation cannot be completed with this unattended setup.
The browser has no authenticated session. The host frontend has no process-local
Google OAuth credentials; root credentials exist but their production reuse is not
approved here. A human must approve/configure the Google client for the documented
`http://localhost:3000/api/auth/callback/google`, then complete Google sign-in.
Assistant verification additionally needs an isolated authorized fixture deck and a
running deterministic provider adapter; none was booted here. Do not replace that
with paid calls, fabricated sessions, middleware bypasses, or live-data writes.

Round 2's AC4 static-page PASS is **not reproduced** with working Auth.js secret
configuration: middleware now returns the normal 307 sign-in redirect. Round 2
reported `MissingSecret`, so its exposed static page is not evidence of successful
authenticated navigation. No new claim is made about protected-page correctness.

## Cleanup and self-violation check

```text
playwright-cli -s=remove-recommendation-personalization close
Browser 'remove-recommendation-personalization' closed
taskkill /PID 14468 /T /F
SUCCESS: The process with PID 24868 (child process of PID 3316) has been terminated.
SUCCESS: The process with PID 28160 (child process of PID 14468) has been terminated.
SUCCESS: The process with PID 3316 (child process of PID 14468) has been terminated.
SUCCESS: The process with PID 14468 (child process of PID 26612) has been terminated.
Get-NetTCPConnection -State Listen -LocalPort 3000 -ErrorAction SilentlyContinue
[no output]
```

Only this evaluator's frontend process tree and browser session were stopped.
Rancher Desktop and builders' PostgreSQL were not touched.

Final `git status --porcelain` saved to `artifacts/browser-3-status-after.txt`.
All writes made by this evaluator are under this spec directory. Concurrent builders
changed backend test paths and created `gate-3.md`; those were neither edited nor
reverted here. No observed self-violation. No build-notes read: this was the delegated
limited browser feasibility check, not a full round evaluation or scope review.

## Follow-up: approved local OAuth reuse

The user subsequently explicitly approved reusing the existing Google OAuth client
locally, without Google configuration changes, and offered to complete sign-in.
Started a new frontend with the existing `AUTH_SECRET`, `AUTH_GOOGLE_ID`, and
`AUTH_GOOGLE_SECRET` read privately into the child process only. `AUTH_URL` is fixed
to `http://localhost:3000`. No env files were edited and no credential values were
printed. No frontend build process was detected before startup; none was stopped.

```text
. ./.agent/specs/remove-recommendation-personalization/artifacts/browser-3-oauth-start.ps1
EXISTING_OAUTH_VALUES_IMPORTED_PRIVATELY=True
AUTH_URL=http://localhost:3000
STARTED_FRONTEND_PID=1976
curl.exe -sS -o NUL -w 'GET /signin HTTP=%{http_code}\n' http://localhost:3000/signin
GET /signin HTTP=200
FRONTEND_PID_1976_RUNNING=True
```

The requested visible Review-pane browser could not be opened:

```text
tools.browser.tabs.open({url:'http://localhost:3000/signin',focus:true})
[browser.disconnected] No desktop browser is connected to this session. Open this session in the desktop app and wait for it to connect. Then call browser.tabs.list({}). Repeating browser actions while disconnected will not help.
```

**No tabID exists for this attempt.** No Google sign-in click or callback was reached,
so localhost redirect compatibility remains unverified. User/main must connect the
desktop browser to this session (or open the local sign-in URL manually). No hidden
browser, fake session, backend, DB, or paid model was used as a substitute.

Per the follow-up instruction, **frontend PID 1976 is intentionally left running**
for human sign-in; main must coordinate its eventual cleanup. Logs are
`artifacts/browser-3-oauth-frontend.stdout.log` and
`artifacts/browser-3-oauth-frontend.stderr.log`; PID file is
`artifacts/browser-3-oauth-frontend.pid`. There is no new browser session to clean up.
Final status saved to `artifacts/browser-3-oauth-status-after.txt`; evaluator edits
remain inside this spec directory. Earlier manual criterion verdicts are unchanged.
