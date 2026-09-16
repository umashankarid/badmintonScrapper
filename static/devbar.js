// static/devbar.js
// Shows which backend the app is talking to, and lets a local developer switch.
// In production /api/dev-mode returns 404 and this script does nothing at all.

(async function () {
  const state = await getJSON("/api/dev-mode");
  if (!state || !state.dev_tools) return;

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
      // Asked now rather than at page load: index.html signs in and out with
      // fetch and no navigation, so a value captured earlier would be stale
      // exactly when this matters.
      const who = await getJSON("/api/bwf-status");
      if (who && who.logged_in) {
        const target = dev ? "LIVE" : "DEV";
        if (!confirm(`Switching to ${target} signs you out of ${who.player_name}.`)) return;
      }
      button.disabled = true;
      const body = await postJSON("/api/dev-mode", { mode: dev ? "live" : "dev" });
      if (!body || !body.success) {
        alert((body && body.error) || "Could not switch mode.");
        button.disabled = false;
        return;
      }
      if (body.signed_out) window.location.href = "/login.html";
      else location.reload();
    };
    bar.append(label, button);
    if (dev) addPersonaPicker(bar);
  };
  render();
  document.body.prepend(bar);

  // Sign in as one of the stub accounts. Dev mode only: these usernames resolve
  // against the stub backend, so /api/dev-personas returns an empty list in live.
  async function addPersonaPicker(bar) {
    const listing = await getJSON("/api/dev-personas");
    const personas = listing && listing.personas;
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
      // The mode is process-wide, so it may have moved to live in another tab
      // or across a restart since this dropdown was built. Posting a stub
      // username then would forward it to the real site as a failed login.
      const now = await getJSON("/api/dev-mode");
      if (!now || now.mode !== "dev") {
        alert("The server is no longer in DEV mode. Reload before using this.");
        select.disabled = false;
        select.value = "";
        return;
      }
      const body = await postJSON("/api/bwf-login", { login: select.value, password: "dev" });
      if (!body || !body.success) {
        alert((body && body.error) || "Could not sign in as that account.");
        select.disabled = false;
        select.value = "";
        return;
      }
      window.location.href = "/";
    };
    bar.appendChild(select);
  }

  // Both return null on any failure — a 404, a network error, or an HTML error
  // page from the debugger. Callers handle null, so nothing throws out of an
  // event handler and leaves its control disabled forever.
  async function getJSON(url) {
    try {
      const res = await fetch(url);
      return res.ok ? await res.json() : null;
    } catch (e) {
      return null;
    }
  }

  async function postJSON(url, payload) {
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      return await res.json();
    } catch (e) {
      return null;
    }
  }
})();
