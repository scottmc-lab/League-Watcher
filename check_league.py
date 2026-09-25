#!/usr/bin/env python3
"""
Daily AYFL league digest email for Glenburn Miners Welfare FC Blue (2014).

Fetches the league table and the match feed, and emails a digest containing:
  - what's changed since the last run (table movement, new results, fixture changes)
  - the full league table (Glenburn's row highlighted)
  - a one-line summary of every team's record, last result and next fixture
  - Glenburn's results in full this season

Run daily by GitHub Actions (see .github/workflows/check-league.yml).
State is persisted to state.json, which the workflow commits back to the repo.
"""

import json
import os
import re
import smtplib
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape as esc
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

# ---- Configuration ----

LEAGUE_URL = "https://www.ayfl.co.uk/leaguetablefeed/1055"
MATCH_URL = "https://www.ayfl.co.uk/matchfeed/1053"
TEAM_NAME = "Glenburn Miners Welfare Fc Blue (2014)"

SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
EMAIL_FROM = os.environ.get("EMAIL_FROM", SMTP_USERNAME)
EMAIL_TO = os.environ.get("EMAIL_TO", "")

STATE_FILE = Path(__file__).parent / "state.json"
HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def normalise_header(text):
    return re.sub(r"[^a-z0-9+/#]", "", text.strip().lower())


def fetch_html(url):
    resp = requests.get(url, headers=HTTP_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def names_match(a, b):
    """Exact-ish match between two team names as they appear on the site."""
    return (a or "").strip().lower() == (b or "").strip().lower()


def is_our_team(name, team_name=TEAM_NAME):
    """Fuzzy match for OUR configured team name, tolerant of minor formatting
    differences between what's typed in TEAM_NAME and what the site renders."""
    if not name:
        return False
    if names_match(name, team_name):
        return True
    words = [w for w in re.split(r"\W+", team_name.lower()) if w and w != "fc"]
    return all(w in name.strip().lower() for w in words)


def ordinal(n):
    try:
        n = int(n)
    except (TypeError, ValueError):
        return str(n)
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


# ---------------------------------------------------------------------------
# League table
# ---------------------------------------------------------------------------

LEAGUE_COLUMN_ALIASES = {
    "pos": ["pos", "position", "#"],
    "played": ["p", "pld", "played"],
    "won": ["w", "won"],
    "drawn": ["d", "drn", "drawn"],
    "lost": ["l", "lost"],
    "gf": ["f", "gf", "for"],
    "ga": ["a", "ga", "against"],
    "gd": ["gd", "+/-", "diff", "goaldiff"],
    "points": ["pts", "points"],
}


def fetch_league_table(url):
    """Returns a list of dicts, one per team, in table order."""
    soup = BeautifulSoup(fetch_html(url), "html.parser")
    table = soup.find("table")
    if table is None:
        raise RuntimeError(
            "No <table> found on the league table page. It may be rendered by "
            "JavaScript - see README for how to find the real data source."
        )
    rows = table.find_all("tr")
    if not rows:
        raise RuntimeError("League table has no rows.")

    header_cells = rows[0].find_all(["th", "td"])
    headers_norm = [normalise_header(c.get_text()) for c in header_cells]

    col_index = {}
    for canonical, aliases in LEAGUE_COLUMN_ALIASES.items():
        for i, h in enumerate(headers_norm):
            if h in [normalise_header(a) for a in aliases]:
                col_index[canonical] = i
                break

    matched = set(col_index.values())
    team_col = next(
        (i for i, h in enumerate(headers_norm) if i not in matched and h not in ("", "form", "logo")),
        1,
    )

    teams = []
    for tr in rows[1:]:
        cells = tr.find_all(["td", "th"])
        if not cells or len(cells) <= team_col:
            continue
        team_text = cells[team_col].get_text(strip=True)
        if not team_text:
            continue
        entry = {"team": team_text}
        for canonical, idx in col_index.items():
            if idx < len(cells):
                entry[canonical] = cells[idx].get_text(strip=True)
        teams.append(entry)
    return teams


def find_team(teams, team_name):
    for row in teams:
        if is_our_team(row["team"], team_name):
            return row
    return None


def diff_league_row(old, new):
    if old is None:
        return []
    labels = {
        "pos": "League position", "played": "Played", "won": "Won", "drawn": "Drawn",
        "lost": "Lost", "gf": "Goals for", "ga": "Goals against",
        "gd": "Goal difference", "points": "Points",
    }
    changes = []
    for key, label in labels.items():
        old_val, new_val = old.get(key), new.get(key)
        if old_val is not None and new_val is not None and old_val != new_val:
            if key == "pos":
                changes.append(f"League position: {ordinal(old_val)} -> {ordinal(new_val)}")
            else:
                changes.append(f"{label}: {old_val} -> {new_val}")
    return changes


# ---------------------------------------------------------------------------
# Match feed (results + fixtures, for the whole league)
# ---------------------------------------------------------------------------

MATCH_COLUMN_ALIASES = {
    "date": ["date"],
    "time": ["time", "kickoff", "ko"],
    "home": ["home", "hometeam", "home team"],
    "away": ["away", "awayteam", "away team"],
    "score": ["score", "result", "ft"],
    "fixture": ["fixture", "match"],
    "venue": ["venue", "ground"],
    "competition": ["competition", "league", "division"],
}
SCORE_RE = re.compile(r"(\d+)\s*[-:]\s*(\d+)")


def fetch_all_matches(url):
    """Returns every match found in the feed (all teams), most recent info first
    order is whatever the page uses; we sort separately where it matters."""
    soup = BeautifulSoup(fetch_html(url), "html.parser")
    matches = []

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        header_cells = rows[0].find_all(["th", "td"])
        headers_norm = [normalise_header(c.get_text()) for c in header_cells]

        col_index = {}
        for canonical, aliases in MATCH_COLUMN_ALIASES.items():
            for i, h in enumerate(headers_norm):
                if h in [normalise_header(a) for a in aliases]:
                    col_index[canonical] = i
                    break

        has_home_away = "home" in col_index and "away" in col_index
        has_fixture_col = "fixture" in col_index
        if not has_home_away and not has_fixture_col:
            continue

        for tr in rows[1:]:
            cells = tr.find_all(["td", "th"])
            if not cells:
                continue

            def cell(key):
                idx = col_index.get(key)
                return cells[idx].get_text(strip=True) if idx is not None and idx < len(cells) else None

            home, away = cell("home"), cell("away")
            if not has_home_away:
                fixture_text = cell("fixture") or ""
                parts = re.split(r"\s+v\s+|\s+vs\s+", fixture_text, flags=re.IGNORECASE)
                if len(parts) == 2:
                    home, away = parts[0].strip(), parts[1].strip()
            if not home or not away:
                continue

            date_raw = cell("date") or ""
            date_parsed = None
            if date_raw:
                try:
                    date_parsed = dateparser.parse(date_raw, dayfirst=True, fuzzy=True)
                except (ValueError, OverflowError):
                    date_parsed = None

            score_text = cell("score") or ""
            score_match = SCORE_RE.search(score_text)

            matches.append({
                "key": f"{date_raw}|{home}|{away}",
                "date": date_raw,
                "date_parsed": date_parsed.isoformat() if date_parsed else None,
                "time": cell("time") or "",
                "home": home,
                "away": away,
                "venue": cell("venue") or "",
                "competition": cell("competition") or "",
                "played": bool(score_match),
                "score": f"{score_match.group(1)}-{score_match.group(2)}" if score_match else "",
            })
    return matches


def sort_key(m):
    return (0, m["date_parsed"]) if m["date_parsed"] else (1, m["date"])


def team_matches_for(matches, team_name):
    return [m for m in matches if is_our_team(m["home"], team_name) or is_our_team(m["away"], team_name)]


def diff_matches(old_matches, new_matches, team_name):
    old_by_key = {m["key"]: m for m in (old_matches or [])}
    result_changes, fixture_changes = [], []
    for m in new_matches:
        old = old_by_key.get(m["key"])
        opponent = m["away"] if is_our_team(m["home"], team_name) else m["home"]
        venue_note = f" ({m['venue']})" if m["venue"] else ""
        if m["played"]:
            if old is None or not old.get("played"):
                suffix = f" - {m['date']}" if m["date"] else ""
                result_changes.append(f"Result: {m['home']} {m['score']} {m['away']}{suffix}")
        else:
            if old is None:
                fixture_changes.append(f"New fixture: vs {opponent} - {m['date']} {m['time']}{venue_note}".strip())
            elif old.get("time") != m["time"] or old.get("venue") != m["venue"]:
                was = f"{old.get('time') or 'TBC'}{(' / ' + old.get('venue')) if old.get('venue') else ''}"
                fixture_changes.append(
                    f"Fixture updated: vs {opponent} - {m['date']} {m['time']}{venue_note} (was {was})".strip()
                )
    return result_changes, fixture_changes


def group_by_team(matches, team_names):
    groups = {name: [] for name in team_names}
    for m in matches:
        for name in team_names:
            if names_match(m["home"], name) or names_match(m["away"], name):
                groups[name].append(m)
    for name in groups:
        groups[name].sort(key=sort_key)
    return groups


def team_summary(team_name, matches):
    results = [m for m in matches if m["played"]]
    fixtures = [m for m in matches if not m["played"]]
    last_result, next_fixture = None, None
    if results:
        m = results[-1]
        home = names_match(m["home"], team_name)
        opponent = m["away"] if home else m["home"]
        last_result = f"{m['score']} vs {opponent} ({'H' if home else 'A'})"
    if fixtures:
        m = fixtures[0]
        home = names_match(m["home"], team_name)
        opponent = m["away"] if home else m["home"]
        next_fixture = f"vs {opponent} ({'H' if home else 'A'}) - {m['date']} {m['time']}".strip()
    return last_result, next_fixture


def glenburn_full_results(matches, team_name):
    results = [m for m in matches if m["played"] and
               (is_our_team(m["home"], team_name) or is_our_team(m["away"], team_name))]
    results.sort(key=sort_key)
    out = []
    for m in results:
        home = is_our_team(m["home"], team_name)
        opponent = m["away"] if home else m["home"]
        try:
            gf, ga = (int(x) for x in m["score"].split("-"))
            if not home:
                gf, ga = ga, gf
            outcome = "W" if gf > ga else ("D" if gf == ga else "L")
            score_display = f"{gf}-{ga}"
        except ValueError:
            outcome, score_display = "?", m["score"]
        out.append({
            "date": m["date"], "venue": "H" if home else "A",
            "opponent": opponent, "score": score_display, "outcome": outcome,
        })
    return out


# ---------------------------------------------------------------------------
# Email building
# ---------------------------------------------------------------------------

def build_html_email(our_row, changes, teams, team_summaries, glenburn_results, is_first_run):
    if is_first_run:
        changes_html = "<p>First automated check for this team — here's today's snapshot. You'll see what's changed from the next check onward.</p>"
    elif changes:
        changes_html = "<ul>" + "".join(f"<li>{esc(c)}</li>" for c in changes) + "</ul>"
    else:
        changes_html = "<p>No changes since the last check.</p>"

    table_rows = "".join(
        f"<tr{' style=\"background:#fff6cc;font-weight:bold;\"' if is_our_team(t['team']) else ''}>"
        f"<td>{esc(t.get('pos','?'))}</td><td style='text-align:left;'>{esc(t['team'])}</td>"
        f"<td>{esc(t.get('played','?'))}</td><td>{esc(t.get('won','?'))}</td>"
        f"<td>{esc(t.get('drawn','?'))}</td><td>{esc(t.get('lost','?'))}</td>"
        f"<td>{esc(t.get('gf','?'))}</td><td>{esc(t.get('ga','?'))}</td>"
        f"<td>{esc(t.get('gd','?'))}</td><td>{esc(t.get('points','?'))}</td></tr>"
        for t in teams
    )
    league_table_html = (
        "<table cellpadding='6' cellspacing='0' style='border-collapse:collapse;width:100%;font-size:14px;text-align:center;'>"
        "<tr style='background:#222;color:#fff;'><th>Pos</th><th style='text-align:left;'>Team</th>"
        "<th>P</th><th>W</th><th>D</th><th>L</th><th>GF</th><th>GA</th><th>GD</th><th>Pts</th></tr>"
        f"{table_rows}</table>"
    )

    summary_rows = "".join(
        f"<tr{' style=\"background:#fff6cc;font-weight:bold;\"' if s['is_us'] else ''}>"
        f"<td style='text-align:left;'>{esc(s['team'])}</td><td>{esc(s['record'])}</td>"
        f"<td>{esc(s['last_result'])}</td><td>{esc(s['next_fixture'])}</td></tr>"
        for s in team_summaries
    )
    summary_html = (
        "<table cellpadding='6' cellspacing='0' style='border-collapse:collapse;width:100%;font-size:14px;text-align:center;'>"
        "<tr style='background:#222;color:#fff;'><th style='text-align:left;'>Team</th><th>W-D-L</th>"
        "<th>Last result</th><th>Next fixture</th></tr>"
        f"{summary_rows}</table>"
    )

    if glenburn_results:
        gb_rows = "".join(
            f"<tr><td>{esc(r['date'])}</td><td>{esc(r['venue'])}</td>"
            f"<td style='text-align:left;'>{esc(r['opponent'])}</td><td>{esc(r['score'])}</td>"
            f"<td><b>{esc(r['outcome'])}</b></td></tr>"
            for r in glenburn_results
        )
        gb_html = (
            "<table cellpadding='6' cellspacing='0' style='border-collapse:collapse;width:100%;font-size:14px;text-align:center;'>"
            "<tr style='background:#222;color:#fff;'><th>Date</th><th>H/A</th>"
            "<th style='text-align:left;'>Opponent</th><th>Score</th><th>W/D/L</th></tr>"
            f"{gb_rows}</table>"
        )
    else:
        gb_html = "<p>No completed results found yet.</p>"

    pos, pts = our_row.get("pos", "?"), our_row.get("points", "?")
    return f"""<html><body style="font-family:Arial,Helvetica,sans-serif;color:#111;line-height:1.4;">
      <h2 style="margin-bottom:0;">{esc(TEAM_NAME)}</h2>
      <p style="margin-top:4px;color:#555;">Currently {esc(ordinal(pos))}, {esc(pts)} points.</p>

      <h3>What's changed</h3>
      {changes_html}

      <h3>League table</h3>
      {league_table_html}

      <h3>Team-by-team summary</h3>
      {summary_html}

      <h3>{esc(TEAM_NAME)} — results in full</h3>
      {gb_html}
    </body></html>"""


def build_text_email(our_row, changes, teams, team_summaries, glenburn_results, is_first_run):
    lines = [TEAM_NAME, f"Currently {ordinal(our_row.get('pos','?'))}, {our_row.get('points','?')} points.", ""]

    lines.append("WHAT'S CHANGED")
    if is_first_run:
        lines.append("First automated check - today's snapshot. Changes will show from next time.")
    elif changes:
        lines += [f"- {c}" for c in changes]
    else:
        lines.append("No changes since the last check.")
    lines.append("")

    lines.append("LEAGUE TABLE")
    lines.append("Pos  Team                              P   W   D   L   GF  GA  GD  Pts")
    for t in teams:
        marker = " *" if is_our_team(t["team"]) else "  "
        lines.append(
            f"{marker}{str(t.get('pos','?')):<4}{t['team'][:30]:<34}"
            f"{str(t.get('played','?')):<4}{str(t.get('won','?')):<4}{str(t.get('drawn','?')):<4}"
            f"{str(t.get('lost','?')):<4}{str(t.get('gf','?')):<4}{str(t.get('ga','?')):<4}"
            f"{str(t.get('gd','?')):<4}{str(t.get('points','?'))}"
        )
    lines.append("")

    lines.append("TEAM-BY-TEAM SUMMARY")
    for s in team_summaries:
        marker = "*" if s["is_us"] else " "
        lines.append(f"{marker} {s['team']}: {s['record']} | Last: {s['last_result']} | Next: {s['next_fixture']}")
    lines.append("")

    lines.append(f"{TEAM_NAME.upper()} - RESULTS IN FULL")
    if glenburn_results:
        for r in glenburn_results:
            lines.append(f"{r['date']:<12} {r['venue']}  vs {r['opponent']:<28} {r['score']:<6} {r['outcome']}")
    else:
        lines.append("No completed results found yet.")

    return "\n".join(lines)


def send_email(subject, text_body, html_body):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls(context=context)
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        recipients = [addr.strip() for addr in EMAIL_TO.split(",") if addr.strip()]
        server.sendmail(EMAIL_FROM, recipients, msg.as_string())


# ---------------------------------------------------------------------------
# State + main
# ---------------------------------------------------------------------------

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"league": None, "matches": []}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def main():
    state = load_state()
    is_first_run = state.get("league") is None

    teams = fetch_league_table(LEAGUE_URL)
    our_row = find_team(teams, TEAM_NAME)
    if our_row is None:
        raise LookupError(f"Team not found in league table. Teams seen: {[t['team'] for t in teams]}")

    all_matches = fetch_all_matches(MATCH_URL)
    our_matches = team_matches_for(all_matches, TEAM_NAME)

    league_changes = diff_league_row(state.get("league"), our_row)
    result_changes, fixture_changes = diff_matches(state.get("matches"), our_matches, TEAM_NAME)
    changes = league_changes + result_changes + fixture_changes

    team_names = [t["team"] for t in teams]
    groups = group_by_team(all_matches, team_names)
    team_summaries = []
    for t in teams:
        last_result, next_fixture = team_summary(t["team"], groups.get(t["team"], []))
        team_summaries.append({
            "team": t["team"],
            "record": f"{t.get('won','?')}-{t.get('drawn','?')}-{t.get('lost','?')}",
            "last_result": last_result or "—",
            "next_fixture": next_fixture or "—",
            "is_us": is_our_team(t["team"]),
        })

    glenburn_results = glenburn_full_results(all_matches, TEAM_NAME)

    subject = f"AYFL League update - {TEAM_NAME} - {datetime.now():%d %b %Y}"
    html_body = build_html_email(our_row, changes, teams, team_summaries, glenburn_results, is_first_run)
    text_body = build_text_email(our_row, changes, teams, team_summaries, glenburn_results, is_first_run)

    if EMAIL_TO and SMTP_USERNAME and SMTP_PASSWORD:
        send_email(subject, text_body, html_body)
        print("Email sent.")
    else:
        print("Email settings not fully configured - printing digest instead:\n")
        print(text_body)

    save_state({"league": our_row, "matches": our_matches})


if __name__ == "__main__":
    main()
