// Updates for Pal: renders data/items.json. No libraries, no external calls.
(function () {
  const $ = (id) => document.getElementById(id);
  const state = { items: [], sector: "All", source: "All", major: false, q: "" };

  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmtDay = (iso) => new Date(iso + "T00:00:00").toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric" });

  function card(it, lead) {
    const badges = `<span class="badge ${esc(it.source)}">${esc(it.source)}</span>` + (it.major ? `<span class="badge major">MAJOR</span>` : "");
    const extra = (it.links || []).length > 1
      ? `<div class="more">Individual documents: ${it.links.map((l) => `<a href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.label)}</a>`).join("")}</div>` : "";
    const meta = `${badges}${esc(it.ministry)} &middot; ${esc(it.sector)}`;
    if (lead) {
      return `<div class="kicker">Lead story &middot; ${meta}</div>
        <h2><a href="${esc(it.url)}" target="_blank" rel="noopener">${esc(it.title)}</a></h2>
        <p>${esc(it.summary)}</p>${extra}
        <a class="read" href="${esc(it.url)}" target="_blank" rel="noopener">Read the original document &rarr;</a>`;
    }
    return `<article class="card"><div class="meta">${meta}</div>
      <h3><a href="${esc(it.url)}" target="_blank" rel="noopener">${esc(it.title)}</a></h3>
      <p>${esc(it.summary)}</p>${extra}
      <a class="read" href="${esc(it.url)}" target="_blank" rel="noopener">Read the original &rarr;</a></article>`;
  }

  function chips(el, values, key) {
    el.innerHTML = values.map((v) => `<button class="chip" type="button" aria-pressed="${state[key] === v}" data-v="${esc(v)}">${esc(v)}</button>`).join("");
    el.onclick = (e) => {
      const b = e.target.closest("button");
      if (!b) return;
      state[key] = b.dataset.v;
      chips(el, values, key);
      render();
    };
  }

  function visible() {
    const q = state.q.trim().toLowerCase();
    return state.items.filter((i) =>
      (state.sector === "All" || i.sector === state.sector) &&
      (state.source === "All" || i.source === state.source) &&
      (!state.major || i.major) &&
      (!q || `${i.title} ${i.summary} ${i.ministry} ${i.sector}`.toLowerCase().includes(q)));
  }

  function render() {
    const list = visible();
    $("count").textContent = `${list.length} of ${state.items.length} items`;
    $("empty").hidden = list.length > 0;
    let html = "", day = "";
    for (const it of list) {
      if (it.date !== day) { day = it.date; html += `<h2 class="day">${fmtDay(day)}</h2>`; }
      html += card(it, false);
    }
    $("feed").innerHTML = html;
  }

  function lead() {
    const top = state.items.find((i) => i.major) || state.items[0];
    if (!top) return;
    $("lead").innerHTML = card(top, true);
    $("lead").hidden = false;
  }

  fetch("data/items.json", { cache: "no-cache" })
    .then((r) => r.json())
    .then((d) => {
      state.items = d.items;
      $("today").textContent = new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
      $("edition").textContent = `Policy Desk · ${d.count} items on file`;
      $("updated").textContent = `Last refreshed ${d.updated}`;
      chips($("sectors"), ["All", ...[...new Set(d.items.map((i) => i.sector))].sort()], "sector");
      chips($("sources"), ["All", "PIB", "RBI", "SEBI"], "source");
      $("q").oninput = (e) => { state.q = e.target.value; render(); };
      $("majorOnly").onchange = (e) => { state.major = e.target.checked; render(); };
      lead();
      render();
    })
    .catch(() => { $("feed").innerHTML = '<p class="empty">Could not load data/items.json.</p>'; });
})();
