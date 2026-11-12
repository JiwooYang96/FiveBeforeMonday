# Instagram auto-posting: one-time setup (about 15 minutes)

Everything after this runs by itself. You need a computer for steps 2-4 (Meta's developer site).

1. **Make @tech_stocks_news a professional account.** In the Instagram app: Settings → Account type and tools →
   Switch to professional account → Creator (or Business). Free, and no Facebook Page needed.
2. **Create a Meta app.** At developers.facebook.com → My Apps → Create app → use case
   "Manage messaging & content on Instagram" → app type Business. Name it e.g. "Five Before Monday poster".
3. **Connect the account and get a token.** In the app: Instagram → API setup with Instagram business login →
   "Add account" and log in as @tech_stocks_news → "Generate token". Allow `instagram_business_basic` and
   `instagram_business_content_publish`. Copy the token (it's long-lived, 60 days; GitHub refreshes it weekly).
   The app can stay in development mode: it only posts to your own account, so no App Review is needed.
4. **Give the token to GitHub.** Repo FiveBeforeMonday → Settings → Secrets and variables → Actions:
   - Secret `IG_ACCESS_TOKEN` = the token.
   - Secret `SECRETS_PAT` = a fine-grained personal access token (github.com/settings/personal-access-tokens)
     for this repo only, with **Secrets: read and write**. It lets the Sunday job save the refreshed token.
5. **Test it.** Actions → "Post reel to Instagram" → Run workflow. With nothing queued it does nothing; after
   the first daily reel is queued it posts it and writes the link into `reels/<date>.json`.

If a post fails, GitHub opens an issue titled "Reel not posted <date>" with the run link.
