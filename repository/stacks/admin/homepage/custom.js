/* Official LoL Esports data, fetched through Homepage's configured read-only proxy. */
(() => {
  "use strict";
  const LEAGUES = new Set([
    "98767991299243165", // LCS
    "98767991332355509", // CBLOL
    "98767991302996019", // LEC
    "98767991310872058", // LCK
    "98767991314006698", // LPL
    "113476371197627891", // LCP
    "98767975604431411", // Worlds
    "98767991325878492", // MSI
    "113464388705111224", // First Stand
  ]);
  const FEED = "/api/services/proxy?group=Streaming&service=LoL%20Esports&index=0";
  const OFFICIAL = "https://lolesports.com/en-US/";
  const PREFERENCE = "homepage.lol.collapsed";
  const REFRESH_MS = 5 * 60 * 1000;

  function matchesFrom(payload, now = Date.now()) {
    if (payload?.errors?.length || payload?.error || !Array.isArray(payload?.data?.esports?.events)) {
      throw new Error("Schedule feed unavailable");
    }
    const seen = new Set();
    return payload.data.esports.events.filter((event) => {
      const start = Date.parse(event.startTime);
      const keep = event.type === "match" && LEAGUES.has(event.league?.id) &&
        ["unstarted", "inProgress"].includes(event.state) && Number.isFinite(start) &&
        (event.state === "inProgress" || start >= now - 2 * 60 * 60 * 1000) && !seen.has(event.id);
      if (keep) seen.add(event.id);
      return keep;
    }).sort((a, b) => {
      const live = Number(b.state === "inProgress") - Number(a.state === "inProgress");
      return live || Date.parse(a.startTime) - Date.parse(b.startTime);
    }).slice(0, 10);
  }

  // The parser is also used by the local regression checks; no browser globals are exported.
  if (typeof module !== "undefined" && module.exports) module.exports = { matchesFrom };
  if (typeof document === "undefined") return;

  function mount() {
    if (document.getElementById("lol-esports-widget")) return;
    const create = (tag, className, text) => {
      const node = document.createElement(tag);
      if (className) node.className = className;
      if (text !== undefined) node.textContent = text;
      return node;
    };
    const root = create("section");
    root.id = "lol-esports-widget";
    root.setAttribute("aria-label", "League of Legends esports schedule");
    const toggle = create("button", "lol-toggle", "LoL Esports · Schedule");
    toggle.type = "button";
    toggle.setAttribute("aria-controls", "lol-esports-panel");
    const panel = create("div", "lol-panel");
    panel.id = "lol-esports-panel";
    const header = create("div", "lol-header");
    header.append(create("h2", null, "LoL Esports"));
    const close = create("button", "lol-close", "×");
    close.type = "button";
    close.setAttribute("aria-label", "Collapse League of Legends schedule");
    header.append(close);
    const note = create("p", "lol-status lol-note", "Major leagues + internationals · Warsaw time");
    const status = create("p", "lol-status", "Loading upcoming matches…");
    status.setAttribute("role", "status");
    const list = create("ul", "lol-list");
    const footer = create("div", "lol-footer");
    const updated = create("span", "lol-note");
    const link = create("a", null, "Full schedule ↗");
    link.href = OFFICIAL;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    footer.append(updated, link);
    panel.append(header, note, status, list, footer);
    root.append(toggle, panel);
    document.body.append(root);

    const matchTime = new Intl.DateTimeFormat("en-GB", {
      timeZone: "Europe/Warsaw", weekday: "short", day: "numeric", month: "short",
      hour: "2-digit", minute: "2-digit", hourCycle: "h23",
    });
    const clock = new Intl.DateTimeFormat("en-GB", {
      timeZone: "Europe/Warsaw", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
    });
    let collapsed = window.matchMedia("(max-width: 600px)").matches;
    try {
      const saved = localStorage.getItem(PREFERENCE);
      if (saved !== null) collapsed = saved === "true";
    } catch (_) { /* Storage may be disabled in private browsing. */ }
    let loading = false;
    let lastPayload = null;
    let lastSuccess = 0;

    function render(payload) {
      const matches = matchesFrom(payload);
      list.replaceChildren();
      for (const event of matches) {
        const item = create("li", "lol-match");
        const time = create("time", event.state === "inProgress" ? "lol-meta lol-live" : "lol-meta");
        time.dateTime = event.startTime;
        time.textContent = (event.state === "inProgress" ? "LIVE · " : "") + matchTime.format(new Date(event.startTime));
        const teams = (event.matchTeams || []).map((team) => team.code || team.name || "TBD");
        const names = (event.matchTeams || []).map((team) => team.name || "TBD");
        const matchup = create("div", "lol-teams", teams.length >= 2 ? teams.join(" vs ") : "Teams to be announced");
        matchup.title = names.join(" vs ");
        const bestOf = event.match?.strategy?.count;
        const details = [event.league.name, event.blockName, bestOf ? `Bo${bestOf}` : null].filter(Boolean);
        item.append(time, matchup, create("div", "lol-meta", details.join(" · ")));
        list.append(item);
      }
      status.hidden = matches.length > 0;
      status.textContent = "Upcoming matches have not been published for these leagues. Check the full schedule.";
    }

    async function refresh() {
      if (loading || collapsed || document.hidden) return;
      loading = true;
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 15000);
      try {
        const response = await fetch(FEED, { signal: controller.signal, credentials: "same-origin" });
        if (!response.ok) throw new Error("Schedule request failed");
        const payload = await response.json();
        render(payload);
        lastPayload = payload;
        lastSuccess = Date.now();
        updated.textContent = "Updated " + clock.format(new Date(lastSuccess));
      } catch (_) {
        if (lastPayload) render(lastPayload);
        status.hidden = false;
        status.textContent = lastPayload
          ? "Update failed; showing the last schedule. Use Full schedule for the latest."
          : "Schedule temporarily unavailable. Open Full schedule below.";
      } finally {
        clearTimeout(timeout);
        loading = false;
      }
    }

    function setCollapsed(value, save = true) {
      collapsed = value;
      panel.hidden = value;
      toggle.hidden = !value;
      toggle.setAttribute("aria-expanded", String(!value));
      if (save) {
        try { localStorage.setItem(PREFERENCE, String(value)); } catch (_) { /* Optional preference. */ }
      }
      if (!value && Date.now() - lastSuccess >= REFRESH_MS) refresh();
      if (value && save) toggle.focus();
    }
    toggle.addEventListener("click", () => { setCollapsed(false); close.focus(); });
    close.addEventListener("click", () => setCollapsed(true));
    root.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !collapsed) { event.preventDefault(); setCollapsed(true); }
    });
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden && Date.now() - lastSuccess >= REFRESH_MS) refresh();
    });
    setInterval(refresh, REFRESH_MS);
    setCollapsed(collapsed, false);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount, { once: true });
  else mount();
})();
