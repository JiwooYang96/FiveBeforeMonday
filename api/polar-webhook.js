// Polar -> Kit: keeps the "paid" tag in Kit in step with Polar subscriptions.
// Polar calls this URL (https://fivebeforemonday.com/api/polar-webhook) on every subscription change.
// Paid tag on: subscription.active / subscription.uncanceled. Paid tag off: subscription.revoked (access ended).
// A cancellation (subscription.canceled) keeps access until the period ends, so nothing changes then.
//
// Vercel environment variables: POLAR_WEBHOOK_SECRET, KIT_API_KEY, optional KIT_PAID_TAG (default "paid").
const crypto = require("crypto");

const KIT = "https://api.kit.com/v4";

// Polar signs with Standard Webhooks: base64(HMAC-SHA256(key, `${id}.${timestamp}.${body}`)).
// Newer secrets (whsec_...) are Standard Webhooks keys (base64 after the prefix); older Polar secrets use the
// whole string as the key. Try both, so either kind of secret works.
function verify(body, headers, secret) {
  const id = headers["webhook-id"], ts = headers["webhook-timestamp"], sig = headers["webhook-signature"] || "";
  if (!id || !ts || !secret) return false;
  if (Math.abs(Date.now() / 1000 - Number(ts)) > 300) return false; // replay window: 5 minutes
  const keys = [Buffer.from(secret, "utf8")];
  if (secret.startsWith("whsec_")) keys.push(Buffer.from(secret.slice(6), "base64"));
  const sent = sig.split(" ").map((s) => s.split(",")[1]).filter(Boolean);
  return keys.some((key) => {
    const expected = crypto.createHmac("sha256", key).update(`${id}.${ts}.${body}`).digest("base64");
    return sent.some((s) => s.length === expected.length && crypto.timingSafeEqual(Buffer.from(s), Buffer.from(expected)));
  });
}

async function kit(path, method = "GET", data) {
  const res = await fetch(KIT + path, {
    method,
    headers: { "X-Kit-Api-Key": process.env.KIT_API_KEY, "Content-Type": "application/json", Accept: "application/json" },
    body: data ? JSON.stringify(data) : undefined,
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`Kit ${method} ${path} -> ${res.status}: ${text.slice(0, 300)}`);
  return text ? JSON.parse(text) : {};
}

async function paidTagId() {
  const name = process.env.KIT_PAID_TAG || "paid";
  const { tags = [] } = await kit("/tags?per_page=1000");
  const found = tags.find((t) => t.name.toLowerCase() === name.toLowerCase());
  if (found) return found.id;
  return (await kit("/tags", "POST", { name })).tag.id;
}

async function setPaid(email, firstName, paid) {
  const tag = await paidTagId();
  if (paid) {
    await kit("/subscribers", "POST", { email_address: email, first_name: firstName || undefined }); // create or update
    await kit(`/tags/${tag}/subscribers`, "POST", { email_address: email });
    return;
  }
  const { subscribers = [] } = await kit(`/subscribers?email_address=${encodeURIComponent(email)}&status=all`);
  for (const s of subscribers) await kit(`/tags/${tag}/subscribers/${s.id}`, "DELETE");
}

async function readBody(req) {
  const chunks = [];
  for await (const c of req) chunks.push(typeof c === "string" ? Buffer.from(c) : c);
  return Buffer.concat(chunks).toString("utf8");
}

const handler = async (req, res) => {
  if (req.method !== "POST") return res.status(405).send("POST only");
  const body = await readBody(req);
  if (!verify(body, req.headers, process.env.POLAR_WEBHOOK_SECRET || "")) return res.status(403).send("bad signature");
  const event = JSON.parse(body);
  const d = event.data || {};
  const email = (d.customer && d.customer.email) || (d.user && d.user.email) || d.customer_email;
  const name = d.customer && d.customer.name ? String(d.customer.name).split(" ")[0] : "";
  const on = ["subscription.active", "subscription.uncanceled"].includes(event.type);
  const off = event.type === "subscription.revoked";
  if (!email || (!on && !off)) return res.status(202).send("ignored");
  try {
    await setPaid(email, name, on);
    return res.status(200).send(on ? "tagged" : "untagged");
  } catch (err) {
    console.error(err.message); // Polar retries non-2xx deliveries
    return res.status(500).send("kit error");
  }
};

module.exports = handler;
module.exports.config = { api: { bodyParser: false } };
module.exports.verify = verify;
