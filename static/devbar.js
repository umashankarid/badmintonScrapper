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
      button.disabled = true;
      const res = await fetch("/api/dev-mode", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: dev ? "live" : "dev" }),
      });
      const body = await res.json();
      if (!res.ok) {
        alert(body.error || "Could not switch mode. Are you logged in as admin?");
        button.disabled = false;
        return;
      }
      state.mode = body.mode;
      location.reload();
    };
    bar.append(label, button);
  };
  render();
  document.body.prepend(bar);
})();
