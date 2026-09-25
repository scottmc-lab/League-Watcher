# Glenburn Miners Welfare FC Blue (2014) — League Digest Emailer

Every day, this emails you a digest containing:
- **What's changed** since yesterday (league position/points movement, new
  results, new or rescheduled fixtures)
- **The full league table**, with Glenburn's row highlighted
- **A one-line summary for every team** in the league — record, last result,
  next fixture
- **Glenburn Blue (2014)'s results in full** — every match played this
  season, with venue and W/D/L

Unlike a change-only alert, this sends an email every day the workflow runs,
so you always get the full picture even if nothing's changed.

## 1. Set up an email account to send from (5 minutes)

The simplest free option is a Gmail account with an **app password**
(you don't need a new account — your own Gmail works, or make a throwaway
one just for this):

1. Turn on 2-Step Verification on the Google account, if not already on:
   https://myaccount.google.com/security
2. Create an app password: https://myaccount.google.com/apppasswords
   — choose "Mail" as the app, name it anything (e.g. "league-watcher"),
   and copy the 16-character password it gives you.

(Any other SMTP provider works too — Outlook, iCloud, a work email, etc.
Just change `SMTP_SERVER`/`SMTP_PORT` accordingly.)

## 2. Create the GitHub repo (5 minutes)

1. Go to github.com, create a **new repository** (private is fine), e.g. `league-watcher`.
2. Upload these items, keeping the folder structure:
   - `check_league.py`
   - `.github/workflows/check-league.yml`
   - `README.md` (optional, but handy)
3. Go to **Settings → Secrets and variables → Actions → New repository secret**
   and add each of these:

   | Secret name     | Value                                                |
   |-----------------|-------------------------------------------------------|
   | `SMTP_SERVER`   | `smtp.gmail.com` (or your provider's SMTP server)     |
   | `SMTP_PORT`     | `587`                                                  |
   | `SMTP_USERNAME` | your full email address                               |
   | `SMTP_PASSWORD` | the app password from step 1                          |
   | `EMAIL_FROM`    | same as `SMTP_USERNAME` (or leave it — it defaults to that) |
   | `EMAIL_TO`      | the address(es) to send the digest to (comma-separate for more than one) |

4. Go to **Settings → Actions → General → Workflow permissions** and select
   "Read and write permissions" (needed so the workflow can save its state file).

## 3. Test it

Go to the **Actions** tab → "Check league table" → **Run workflow** to
trigger it immediately. Check the run's log:

- Success looks like `Email sent.` — check your inbox (and spam folder,
  the first email from a new sender sometimes lands there).
- If it fails with `No <table> found in the page` — either the league table
  or the match feed is being loaded by JavaScript rather than included in
  the raw page. Open the relevant page in Chrome, open Dev Tools (F12) →
  Network tab, refresh, and look for a request that returns the actual data
  (often a `.json` URL). Send me that and I'll adjust the script.
- If it fails saying it couldn't find the team, check the printed list of
  team names — the exact spelling/formatting on the site might differ
  slightly from `TEAM_NAME` in `check_league.py`.
- The match feed's layout is the biggest unknown — some sites put "Home"/
  "Away" in separate columns, others put "Team A v Team B" in one cell.
  The script tries to handle both; if the "results in full" section comes
  back empty, send me a sample of the actual table and I'll tune it.

## First run

The first run saves a baseline and the "What's changed" section will say so
rather than listing changes (there's nothing yet to compare against). From
the second run onward, it'll show real changes.

## How it works

`check_league.py` fetches both feeds, parses the HTML tables (matching
columns by header text rather than assuming fixed positions, so it's
reasonably tolerant of layout quirks), builds an HTML+plaintext email, and
sends it via SMTP. It saves the day's league position and match list to
`state.json` so the next run can tell what's changed; the GitHub Action
commits that file back to the repo after each run.

## A note on scraping

This checks two public pages once a day for your own son's team — about as
light-touch as scraping gets. Still, if AYFL ever changes their site or asks
for this kind of access to stop, it's worth respecting that.
