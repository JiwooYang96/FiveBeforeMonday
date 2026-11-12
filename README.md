# Five Before Monday

Website for the Five Before Monday newsletter.

- `index.html`, `sample.html`, legal pages, `styles.css`, `app.js`: the static site (deploys to Vercel as-is).
- `config.js`: Kit form IDs and contact email. Fill in before launch.
- `engine/charts.py`: renders email-safe chart PNGs from an issue JSON.
  `python3 engine/charts.py engine/data/sample-2026-11-06.json img/`

- `engine/emails.py`: renders the Saturday brief and Sunday report as email-safe HTML.
  `python3 engine/emails.py engine/data/sample-2026-11-06.json emails/out/`
  Rendered samples are served at `/emails/out/` on the site.

## Sending through Kit

`engine/send.py` turns a rendered email into a Kit broadcast using the
`KIT_API_KEY` repository secret (a Kit v4 key). Run it from GitHub: Actions → **Send issue
email** → Run workflow. `draft` (default) leaves an unsent draft in Kit to
review; `schedule` sends the Saturday brief at the next Saturday 8:00 am New
York time unless a UTC time is given. Broadcasts aren't targeted yet,
so the Sunday report is draft-only until paid members exist.

## Weekly issue (automatic)

Friday after the close: `market-data.yml` saves closing prices to `engine/data/raw/`. A scheduled Claude Code
task (instructions in `docs/RESEARCH_TASK.md`, run on the Claude subscription) researches the week and pushes
`engine/data/research/<week>.json`, including reel ideas. That push starts `weekly-issue.yml`, which checks every
research quote against its page (`engine/verify_research.py`) and builds the issue; if no research arrives, the
Saturday fallback researches through the API instead.

`.github/workflows/weekly-issue.yml` then:

1. `engine/collect.py` pulls closing prices (Yahoo Finance, Stooq fallback) and shares outstanding (SEC EDGAR).
2. `engine/research.py` has Claude search the week's coverage; only statements with citations are kept.
3. `engine/write.py` has Claude write the issue from that data and evidence; charts are built in code.
4. `engine/check.py` gates: every figure must match the data or a cited source's exact text, sources must be
   real, next week's dates must be next week, no advice or predictions, no machine-sounding phrasing, length
   limits, then a separate fact-check review. Failures go back for up to two rewrites.
5. Charts and emails render, the issue and its audit trail are committed (Vercel then serves the images), and the
   Kit emails are created. The Saturday brief is scheduled for 8am New York only when every check passed and
   automatic sending isn't switched off; otherwise it waits as a draft.
6. A GitHub issue reports the result.

Needs the `ANTHROPIC_API_KEY` and `KIT_API_KEY` secrets. The Saturday brief sends automatically when every check
passes; set the repository variable `AUTO_SEND` to `false` to review drafts in Kit instead. Run offline tests with `python3 -m unittest discover -s tests`.

## Daily reels on Instagram

The daily reel task (a scheduled Claude Code run after the New York close) queues `reels/<date>.mp4` and
`reels/<date>.json`. `.github/workflows/post-reel.yml` posts queued reels at 6:31pm New York time through the
Instagram API (`engine/instagram.py`), records the post link in the JSON, deletes videos older than a week,
and refreshes the Instagram token every Sunday. Setup: `docs/INSTAGRAM_SETUP.md`.
