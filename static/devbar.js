// static/devbar.js
// Shows which backend the app is talking to, and lets a local developer switch.
// In production /api/dev-mode returns 404 and this script does nothing at all.

(async function () {
  let state;
  try {
    const res = await fetch("/api/dev-mode");
    if (!res.ok) return;            // production: no such endpoint
    state = await res.json();
  } catch (e) {
    return;                          // server down or offline: stay invisible
  }
  if (!state.dev_tools) return;

  // Who is signed in, so the switch can warn before signing them out.
  try {
    const who = await (await fetch("/api/bwf-status")).json();
    if (who.logged_in) state.signed_in_as = who.player_name || "the current account";
  } catch (e) {
    // Non-fatal: without this the switch just skips its confirmation.
  }

  const bar = document.createElement("div");
  bar.id = "devbar";
  const render = () => {
    const dev = state.mode === "dev";
    bar.style.cssText = [
      "position:sticky", "top:0", "z-index:9999",
      "padding:6px 12px", "font:600 13px system-ui,sans-serif",
      "display:flex", "gap:12px", "align-items:center",
      "color:#fff", `background:${dev ? "#c2410c" : "#15803d"}`,
    ].join(";");
    bar.innerHTML = "";
    const label = document.createElement("span");
    label.textContent = dev
      ? "DEV — fake data, nothing leaves this machine"
      : "LIVE — real Badminton Sweden";
    const button = document.createElement("button");
    button.textContent = dev ? "Switch to LIVE" : "Switch to DEV";
    button.style.cssText = "padding:2px 10px;cursor:pointer;border-radius:3px;border:1px solid #fff;background:transparent;color:#fff;font:inherit";
    button.onclick = async () => {
      // A session belongs to the backend that created it, so the server signs
      // you out on any real mode change. Say so before it happens.
      if (state.signed_in_as) {
        const target = dev ? "LIVE" : "DEV";
        const ok = confirm(
          `Switching to ${target} will sign you out of ${state.signed_in_as}.\n\n` +
          `Sessions cannot cross modes: a stub account has no meaning against the ` +
          `real site, and a real login has none against the stubs.`
        );
        if (!ok) return;
      }
      button.disabled = true;
      const res = await fetch("/api/dev-mode", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: dev ? "live" : "dev" }),
      });
      const body = await res.json();
      if (!res.ok) {
        alert(body.error || "Could not switch mode.");
        button.disabled = false;
        return;
      }
      state.mode = body.mode;
      window.location.href = body.signed_out ? "/login.html" : "/";
    };
    bar.append(label, button);
    if (dev) addPersonaPicker(bar);
  };
  render();
  document.body.prepend(bar);

  // Sign in as one of the stub accounts. Dev mode only: these usernames resolve
  // against the stub backend, so /api/dev-personas returns an empty list in live.
  async function addPersonaPicker(bar) {
    let personas;
    try {
      const res = await fetch("/api/dev-personas");
      if (!res.ok) return;
      personas = (await res.json()).personas;
    } catch (e) {
      return;
    }
    if (!personas || !personas.length) return;

    const select = document.createElement("select");
    select.style.cssText = "padding:2px 6px;border-radius:3px;border:1px solid #fff;background:#fff;color:#333;font:inherit;max-width:340px";
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "Sign in as…";
    select.appendChild(placeholder);
    personas.forEach(p => {
      const opt = document.createElement("option");
      opt.value = p.username;
      opt.textContent = `${p.player_name} — ${p.description || p.club}`;
      select.appendChild(opt);
    });
    select.onchange = async () => {
      if (!select.value) return;
      select.disabled = true;
      const res = await fetch("/api/bwf-login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ login: select.value, password: "dev" }),
      });
      const body = await res.json();
      if (!body.success) {
        alert(body.error || "Could not sign in as that account.");
        select.disabled = false;
        select.value = "";
        return;
      }
      window.location.href = "/";
    };
    bar.appendChild(select);
  }
})();
