# Daily reel notes

One file per trading day, `YYYY-MM-DD.json`, written by the daily reel task after the New York close:

```json
{
  "date": "2026-11-09",
  "lead": "One sentence: what moved most today and the reason outlets give.",
  "ticker": "NVDA",
  "move": "-4.3%",
  "why": ["One sentence per cause, most important first"],
  "sources": [{"url": "https://...", "title": "...", "published": "Nov 9, 2026"}],
  "reel": "plans/<id>.json in reels_generator"
}
```

The weekly researcher reads these first, so the week's lead story is never missed.
