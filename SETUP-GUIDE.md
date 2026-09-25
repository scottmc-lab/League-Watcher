# Setup guide (for someone who's never used GitHub before)

This will take about 20 minutes, once. After that, it just runs itself every
day and emails you.

Two things to know before you start:
- **GitHub** is a free website for storing and running code. You don't need
  to know how to code — you're just uploading three files and clicking a
  few buttons.
- **GitHub Actions** is GitHub's built-in "run this automatically, on a
  schedule" feature. That's what checks the league table every day for you.

---

## Step 1: Create a GitHub account

1. Go to **https://github.com**
2. Click **Sign up**, top right.
3. Enter an email, password, and username. Verify your email when it asks.
4. When it asks about a plan, choose the **Free** plan.

---

## Step 2: Create a repository (your project folder)

1. Once logged in, click the **+** icon in the top-right corner → **New repository**.
2. Repository name: `league-watcher` (or anything you like, no spaces).
3. Set it to **Private** (so only you can see it).
4. Leave everything else as default.
5. Click **Create repository**.

You'll land on an empty repository page with an "upload files" link on it.

---

## Step 3: Upload the project files

First, unzip the `league-watcher.zip` file I gave you, on your computer. You
should see:
```
check_league.py
README.md
SETUP-GUIDE.md
.github/
  workflows/
    check-league.yml
```

Now, on your new repository's GitHub page:

1. Click **Add file → Upload files** (or the "uploading an existing file"
   link if the repo is empty).
2. Drag in `check_league.py` and `README.md`.
3. **Important:** also drag in the whole `.github` folder (not just the
   `.yml` file inside it) — GitHub will keep the folder structure. If your
   browser only lets you drag files (not folders), drag the individual file
   `.github/workflows/check-league.yml` — GitHub is usually smart enough to
   recreate the folder path from that, but if not, see the note at the
   bottom of this guide.
4. Scroll down and click **Commit changes**.

Afterwards, your repository should show a `.github` folder, `check_league.py`,
and `README.md` in the file list.

---

## Step 4: Get a Gmail "app password"

This is a special password just for this one script — it's safer than using
your real Gmail password, and Google requires it for this kind of thing.

1. Go to **https://myaccount.google.com/security**
2. Under "How you sign in to Google", make sure **2-Step Verification** is
   turned on (turn it on if it isn't — you'll need your phone).
3. Go to **https://myaccount.google.com/apppasswords**
4. Under "App name", type something like `league watcher` and click **Create**.
5. Google will show you a 16-character password (like `abcd efgh ijkl mnop`).
   **Copy this down somewhere** — you won't be able to see it again, and
   you'll paste it into GitHub in the next step (spaces don't matter,
   you can include or remove them).

(Not a Gmail user? Any email provider with SMTP works — search "[your
provider] SMTP settings" and "[your provider] app password", and use those
details instead of Gmail's in the next step.)

---

## Step 5: Add your secrets to GitHub

"Secrets" are just GitHub's name for passwords/settings that stay hidden
(never shown in logs, never visible to anyone but you).

1. On your repository page, click **Settings** (top menu of the repo, not
   your account settings).
2. In the left sidebar, click **Secrets and variables → Actions**.
3. Click **New repository secret** and add each of these one at a time
   (name exactly as shown, then the value, then **Add secret**):

   | Name | Value |
   |---|---|
   | `SMTP_SERVER` | `smtp.gmail.com` |
   | `SMTP_PORT` | `587` |
   | `SMTP_USERNAME` | your full Gmail address |
   | `SMTP_PASSWORD` | the 16-character app password from Step 4 |
   | `EMAIL_FROM` | your full Gmail address (same as `SMTP_USERNAME`) |
   | `EMAIL_TO` | the email address you want the digest sent to |

   You should end up with 6 secrets listed.

---

## Step 6: Let the automation save its notes

The script needs to remember yesterday's table so it can tell you what
changed. To let it save that:

1. Still in **Settings**, click **Actions → General** in the left sidebar.
2. Scroll down to **Workflow permissions**.
3. Select **Read and write permissions**.
4. Click **Save**.

---

## Step 7: Test it

1. Click the **Actions** tab (top menu of the repo).
2. You should see a workflow called **Check league table** in the left
   list — click it.
3. Click **Run workflow** (a button on the right, sometimes under a small
   dropdown) → **Run workflow** again to confirm.
4. Wait ~15–30 seconds, then refresh the page. You'll see a run appear with
   either a green tick (success) or a red cross (something went wrong).
5. Click into the run, then into the "Run check and send email" step, to
   read the log.

**If it succeeded:** check your inbox (and spam/junk folder — the first
email from a new sender sometimes lands there). You should have a league
digest email.

**If it failed:** the log will tell you why. The most likely issues:
- A secret is missing or misspelled — check Step 5.
- `No <table> found in the page` — the website's data isn't in the format
  expected. Copy the error and send it to me, along with the URL, and I'll
  adjust the script.
- Something about the team not being found — the log will print the team
  names it *did* find; send me that list and I'll fix the name matching.

---

## Step 8: You're done

Once you've had one successful test email, there's nothing more to do — it
runs automatically every morning (07:00 UTC by default) and emails you.
If you ever want to check it ran, the **Actions** tab always shows the
history.

---

### If uploading the `.github` folder didn't work

Some browsers only let you upload individual files, not folders, via
drag-and-drop. If your repository doesn't end up with a
`.github/workflows/check-league.yml` file in that exact location:

1. On the repo page, click **Add file → Create new file**.
2. In the "Name your file" box, type the full path:
   `.github/workflows/check-league.yml` (GitHub will automatically create
   the folders for you when you type the slashes).
3. Open `check-league.yml` from the unzipped files on your computer with
   any text editor (Notepad, TextEdit), copy all its contents, and paste
   them into the GitHub editor.
4. Click **Commit changes**.
