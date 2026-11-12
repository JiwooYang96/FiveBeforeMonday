(function () {
  var cfg = window.FBM_CONFIG || {};

  // Countdown to the next regular US market open (9:30 am New York time, Monday to Friday).
  // Exchange holidays are not handled; the label says "regular open".
  function nyParts(date) {
    var f = new Intl.DateTimeFormat("en-US", {
      timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23", weekday: "short",
    });
    var out = {};
    f.formatToParts(date).forEach(function (p) { out[p.type] = p.value; });
    return out;
  }
  function secondsToNextOpen(now) {
    var p = nyParts(now);
    var days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    var dow = days.indexOf(p.weekday);
    var secOfDay = (+p.hour) * 3600 + (+p.minute) * 60 + (+p.second);
    var open = 9.5 * 3600;
    for (var add = 0; add < 8; add++) {
      var d = (dow + add) % 7;
      if (d === 0 || d === 6) continue;
      var diff = add * 86400 + open - secOfDay;
      if (diff > 0) return diff;
    }
    return 0;
  }
  function pad(n) { return String(n).padStart(2, "0"); }
  var clock = document.getElementById("clock");
  function tick() {
    if (!clock) return;
    var s = secondsToNextOpen(new Date());
    var d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    clock.textContent = (d ? d + "d " : "") + pad(h) + "h " + pad(m) + "m " + pad(sec) + "s";
  }
  tick();
  setInterval(tick, 1000);

  // Signup forms post straight to Kit once a form ID is configured.
  document.querySelectorAll("form[data-kit]").forEach(function (form) {
    var id = cfg[form.getAttribute("data-kit")];
    var status = form.parentElement.querySelector(".status");
    if (id) {
      form.action = "https://app.kit.com/forms/" + id + "/subscriptions";
      form.method = "post";
      var sent = false;
      form.addEventListener("submit", function (e) {
        if (sent) return; // fallback path: let the browser post the form to Kit
        e.preventDefault();
        var button = form.querySelector("button");
        if (button) button.disabled = true;
        if (status) status.textContent = "Signing you up…";
        fetch(form.action, { method: "POST", body: new FormData(form), headers: { Accept: "application/json" } })
          .then(function (res) {
            if (!res.ok) throw new Error("HTTP " + res.status);
            if (status) status.textContent = "Almost done: check your inbox and tap the link to confirm.";
            form.reset();
          })
          .catch(function () {
            // If the background request is blocked, post the form normally (Kit shows its own confirmation page).
            sent = true;
            form.submit();
          })
          .finally(function () { if (button) button.disabled = false; });
      });
      return;
    }
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      if (status) status.textContent = "Signups open this week. This preview isn't connected to the mailing list yet.";
    });
  });

  // Fill in shared settings.
  document.querySelectorAll("[data-contact]").forEach(function (el) {
    el.textContent = cfg.contactEmail || "";
  });
})();
