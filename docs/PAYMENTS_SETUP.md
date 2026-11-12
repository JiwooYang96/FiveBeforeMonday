# Paid members: Polar + Kit (one-time setup)

How it works: a reader pays on Polar → Polar calls `https://fivebeforemonday.com/api/polar-webhook` →
the reader gets the Kit tag `paid` → the Sunday report (scheduled for Sunday 12:00 New York) goes only to
that tag. When a subscription ends (`subscription.revoked`), the tag is removed. A cancellation keeps access
until the paid period ends.

1. **Checkout links.** Polar → Products → Checkout links → create one link for each product
   (Founding Yearly, Founding Monthly). Put them in `config.js` (`polarYearlyUrl`, `polarMonthlyUrl`); the
   site then shows "Join" buttons instead of the waitlist form.
2. **Webhook.** Polar → Settings → Webhooks → Add endpoint:
   - URL: `https://fivebeforemonday.com/api/polar-webhook`, format **Raw**
   - Events: `subscription.active`, `subscription.uncanceled`, `subscription.revoked`
   - Copy the secret it shows.
3. **Vercel environment variables.** Vercel → project → Settings → Environment Variables (Production):
   - `POLAR_WEBHOOK_SECRET` = the secret from step 2
   - `KIT_API_KEY` = the same Kit v4 key as the GitHub secret
   Then redeploy (Deployments → ⋯ → Redeploy) so the function picks them up.
4. **Test.** Polar → Webhooks → your endpoint → send a test event, or buy with a 100% discount code. The
   buyer should appear in Kit with the tag `paid`.
