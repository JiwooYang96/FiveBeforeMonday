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
`KIT_API_SECRET` repository secret. Run it from GitHub: Actions → **Send issue
email** → Run workflow. `draft` (default) leaves an unsent draft in Kit to
review; `schedule` sends the Saturday brief at the next Saturday 8:00 am New
York time unless a UTC time is given. Kit's v3 API sends to every subscriber,
so the Sunday report is draft-only until paid members exist.
