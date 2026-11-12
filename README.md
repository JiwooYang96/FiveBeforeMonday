# Five Before Monday

Website for the Five Before Monday newsletter.

- `index.html`, `sample.html`, legal pages, `styles.css`, `app.js`: the static site (deploys to Vercel as-is).
- `config.js`: Kit form IDs and contact email. Fill in before launch.
- `engine/charts.py`: renders email-safe chart PNGs from an issue JSON.
  `python3 engine/charts.py engine/data/sample-2026-11-06.json img/`

- `engine/emails.py`: renders the Saturday brief and Sunday report as email-safe HTML.
  `python3 engine/emails.py engine/data/sample-2026-11-06.json emails/out/`
  Rendered samples are served at `/emails/out/` on the site.
