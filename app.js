// Updates for Pal: renders data/*.json, one desk per data file. No libraries, no external calls.
(function () {
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const day = (iso) => new Date(iso + "T00:00:00").toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  const link = (u, t, cls) => `<a ${cls ? `class="${cls}" ` : ""}href="${esc(u)}" target="_blank" rel="noopener">${t}</a>`;
  const list = (a) => (a && a.length ? `<ul>${a.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : "");

  const trimText = (s, n) => { s = (s || "").trim(); return s.length > n ? s.slice(0, n).replace(/\s+\S*$/, "") + " ..." : s; };
  // ---------------------------------------------------------------- briefs (data/briefs.json, built by scripts/brief.py)
  let briefs = {};
  const briefsReady = fetch("data/briefs.json", { cache: "no-cache" }).then((r) => r.json()).then((j) => { briefs = j; }).catch(() => {});
  const LEVEL = { skip: "You can skip the link", worth: "Worth opening", open: "Open the original" };
  function briefHtml(it, mode) {
    const b = briefs[it.url];
    if (!b) return "";
    const full = mode === "full";
    const whys = full ? b.why : b.why.slice(0, 2);
    const facts = b.facts.length ? `<h6>Key facts</h6><ul>${b.facts.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : "";
    const watch = b.watch.length ? `<h6>Watch next</h6><ul>${b.watch.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : "";
    const rest = b.why.length > whys.length ? `<h6>More on why it matters</h6><ul>${b.why.slice(whys.length).map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : "";
    return `<div class="brief"><p class="what">${esc(full ? b.what : trimText(b.what, 420))}</p>
      <div class="whybox"><h6>Why it affects you</h6><ul>${whys.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>
      <details class="fullbrief" ${full ? "open" : ""}><summary>Key facts, what to watch, and whether to open the link</summary>${rest}${facts}${watch}
        <div class="verdict lvl-${esc(b.level)}">${esc(b.verdict)}${b.partial ? " (The article could not be read in full, so this brief is thin.)" : ""}</div></details></div>`;
  }
  // The brief when there is one, otherwise the old one-line text.
  const bodyOf = (it, fallback, mode) => briefHtml(it, mode || "compact") || (fallback ? `<p>${esc(fallback)}</p>` : "");

  // ---------------------------------------------------------------- desks
  const DESKS = {
    policy: {
      file: "data/items.json",
      title: "Policy Desk",
      sources: "Sources: Press Information Bureau, Reserve Bank of India, SEBI. Summaries are the government's own opening lines, trimmed, never rewritten. Always open the original before acting on anything.",
      f1: { key: "sector" }, f2: null, f3: { key: "source", values: ["PIB", "RBI", "SEBI"] },
      flag: { label: "Major decisions only", test: (i) => i.major },
      search: (i) => `${i.title} ${i.summary} ${i.ministry} ${i.sector}`,
      lead: (items) => items.find((i) => i.major) || items[0],
      card(it, lead) {
        const b = `<span class="badge ${esc(it.source)}">${esc(it.source)}</span>` + (it.major ? `<span class="badge major">MAJOR</span>` : "");
        const extra = (it.links || []).length > 1
          ? `<div class="more">Individual documents: ${it.links.map((l) => link(l.url, esc(l.label))).join("")}</div>` : "";
        const meta = `${b}${esc(it.ministry)} &middot; ${esc(it.sector)}`;
        return shell(lead, meta, it, `${bodyOf(it, it.summary, lead ? "full" : "compact")}${extra}`, "Open the original");
      },
    },
    startups: {
      file: "data/startups.json",
      title: "Startup Desk",
      sources: "Sources: Inc42, YourStory, Startup Story, Economic Times Startups, MediaNama (India); TechCrunch, Sifted (Global). Feed cards are headline-level and machine-collected. A Startup File is written by hand from the linked article only; lines marked Inferred are reasoning, not reported fact.",
      subs: [
        { id: "india", label: "Indian Startups", test: (i) => i.region === "India" },
        { id: "global", label: "Global Startups", test: (i) => i.region !== "India" },
      ],
      f1: { key: "sector" }, f2: { key: "type" }, f3: { key: "source" },
      flag: { label: "With Startup File only", test: (i) => !!i.profile },
      search: (i) => `${i.title} ${i.blurb} ${i.company || ""} ${i.sector} ${i.type} ${i.profile ? i.profile.company + " " + i.profile.what : ""}`,
      lead: (items) => items.find((i) => i.profile) || items[0],
      card(it, lead) {
        const b = `<span class="badge ${esc(it.source.replace(/\s+/g, ""))} src">${esc(it.source)}</span><span class="badge type">${esc(it.type)}</span>`;
        const deal = [it.amount && `Figure in headline: ${it.amount}`, it.stage && `Stage: ${it.stage}`, it.investors && `Investors: ${it.investors}`].filter(Boolean);
        const dealHtml = deal.length ? `<div class="deal">${deal.map((d) => `<span>${esc(d)}</span>`).join("")}</div>` : "";
        const also = (it.also || []).length ? `<div class="more">Also covered by: ${it.also.map((a) => link(a.url, esc(a.source))).join("")}</div>` : "";
        const body = `${it.profile ? `<p>${esc(it.profile.tagline)}</p>` : ""}${bodyOf(it, it.blurb, lead ? "full" : "compact")}${dealHtml}${it.profile ? fileBox(it.profile) : briefs[it.url] ? "" : autoBits(it)}${also}`;
        return shell(lead, `${b}${esc(it.sector)} &middot; ${esc(it.region)}`, it, body, "Read the full story", lead);
      },
    },
  };

  // ---------------------------------------------------------------- Immigration Desk
  DESKS.immigration = {
    file: "data/immigration.json",
    title: "Immigration Desk",
    sources: "Rule Changes: GOV.UK and IRCC official feeds where available, otherwise press headlines found via Google News (agency marketing sites filtered out). Country Files and India-Side are hand-written from web research on the date shown; items marked (general knowledge) were not re-verified. Not legal advice: confirm on the official immigration site.",
    subs: [
      { id: "news", label: "Rule Changes" },
      { id: "files", label: "Country Files", view: "files" },
      { id: "india", label: "India-Side", view: "india" },
    ],
    f1: { key: "countryLabel" }, f2: { key: "topic" }, f3: null,
    flag: { label: "Official sources only", test: (i) => i.official },
    search: (i) => `${i.title} ${i.source} ${i.countryLabel} ${i.topic}`,
    lead: (items) => items.find((i) => ["Salary threshold", "PR / Settlement", "Citizenship", "Quota / Caps", "Work visa"].includes(i.topic)) || items[0],
    card(it, lead) {
      const b = `<span class="badge ${it.official ? "major" : "src"}">${it.official ? "OFFICIAL" : "PRESS"}</span><span class="badge type">${esc(it.topic)}</span>`;
      const meta = `${b}${esc(it.countryLabel)} &middot; ${esc(it.source)}`;
      return shell(lead, meta, it, bodyOf(it, "", lead ? "full" : "compact"), it.official ? "Open the official notice" : "Open the original");
    },
  };

  // ---------------------------------------------------------------- Front Page (top stories across all desks)
  DESKS.top = {
    file: "data/front.json",
    title: "Front Page",
    front: true,
    sources: "Front Page ranks stories from the three desks with a transparent point system (see scripts/build_front_page.py): Cabinet and regulator decisions, deal size, official immigration notices, coverage by many outlets, plus recency. The line under each headline lists the rules that put it here. Rebuilt every morning.",
    flag: { label: "", test: () => true },
  };

  const DESK_LINK = { Policy: "#policy", Startups: "#startups", Immigration: "#immigration" };
  const trimTo = (s, n) => {
    s = (s || "").trim();
    return s.length > n ? s.slice(0, n).replace(/\s+\S*$/, "") + " ..." : s;
  };
  const best = (it, n, hero) => {
    const a = it.snippet || "", b = it.lead || "";
    const pick = hero ? (b.length > a.length ? b : a) : (a.length >= 110 ? a : b.length > a.length ? b : a);
    return trimTo(pick, n);
  };
  // A picture when the story has one, otherwise a coloured tile (the tile also shows if the picture fails to load).
  const pic = (it, cls) => {
    const big = it.desk === "Immigration" ? it.label : it.desk === "Startups" ? it.source : it.source;
    const small = it.desk === "Policy" ? it.label : it.desk === "Startups" ? it.label.split("·").pop().trim() : it.source;
    return `<a class="ph ${esc(it.desk)} ${cls || ""}" href="${esc(it.url)}" target="_blank" rel="noopener" tabindex="-1" aria-hidden="true">
      <span class="tile"><b>${esc(big)}</b><i>${esc(small)}</i></span>${it.image ? `<img src="${esc(it.image)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">` : ""}</a>`;
  };
  const deskBadge = (it) => `<span class="badge desk ${esc(it.desk)}">${esc(it.desk)}</span>${it.must_read ? '<span class="badge major">MUST READ</span>' : ""}`;
  const metaLine = (it) => `${deskBadge(it)}${esc(it.label)} &middot; ${esc(it.source)} &middot; ${esc(it.date)}`;
  const whyLine = (it) => `<div class="why">Why it is here: ${it.why.map(esc).join(" &middot; ")}</div>`;

  function heroCard(it) {
    return `<section class="hero">${pic(it, "big")}<div class="htext">
      <div class="meta">${metaLine(it)}</div>
      <h2>${link(it.url, esc(it.title))}</h2>
      ${briefHtml(it, "full") || `<p class="snip">${esc(best(it, 520, true))}</p>`}${whyLine(it)}
      ${link(it.url, "Read the full story &rarr;", "read")} <a class="more" href="${DESK_LINK[it.desk]}">More from the ${esc(it.desk)} Desk</a></div></section>`;
  }
  function gridCard(it) {
    return `<article class="gcard">${pic(it)}<div class="meta">${metaLine(it)}</div>
      <h3>${link(it.url, esc(it.title))}</h3>${briefHtml(it, "compact") || `<p>${esc(best(it, 240))}</p>`}${whyLine(it)}${link(it.url, "Open the original &rarr;", "read")}</article>`;
  }
  function rowCard(it, n) {
    return `<article class="row-card">${pic(it, "sm")}<div><div class="meta">${n ? `<span class="rank">${n}</span>` : ""}${metaLine(it)}</div>
      <h4>${link(it.url, esc(it.title))}</h4>${briefHtml(it, "compact") || `<p>${esc(best(it, 200))}</p>`}</div></article>`;
  }
  function miniCard(it) {
    return `<article class="mini">${pic(it, "xs")}<div><h5>${link(it.url, esc(trimTo(it.title, 110)))}</h5>
      <div class="meta">${esc(it.label)} &middot; ${esc(it.source)} &middot; ${esc(it.date)}</div></div></article>`;
  }

  const fmtNum = (v, dp) => v.toLocaleString("en-IN", { minimumFractionDigits: dp || 0, maximumFractionDigits: dp || 0 });
  function marketStrip(ms) {
    if (!ms || !ms.length) return "";
    return `<div class="markets" aria-label="Market snapshot">${ms.map((m) => `<div class="mk"><span class="mn">${esc(m.name)}</span>
      <b>${fmtNum(m.value, m.dp)}</b><span class="${m.change_pct >= 0 ? "up" : "dn"}">${m.change_pct >= 0 ? "▲" : "▼"} ${Math.abs(m.change_pct).toFixed(2)}%</span></div>`).join("")}
      <div class="mnote">Last close vs the close before it. Source: Yahoo Finance. Times are the last trade, IST.</div></div>`;
  }

  function startupFileBox(f) {
    if (!f) return "";
    const region = f.region === "Global" ? "global" : "india";
    return `<section class="feat"><div class="fk">Startup File of the day</div><h3>${esc(f.company)}</h3><p class="tag">${esc(f.tagline)}</p>
      <h6>What they do</h6><p>${esc(trimTo(f.what, 300))}</p><h6>How they make money</h6><p>${esc(trimTo(f.how[0] || "", 260))}</p>
      <p><a class="read" href="#startups/${region}">Open the Startup Desk &rarr;</a> <a class="more" href="${esc(f.url)}" target="_blank" rel="noopener">Source article</a></p></section>`;
  }
  function countryBox(c) {
    if (!c) return "";
    return `<section class="feat"><div class="fk">Country spotlight</div><h3>${esc(c.name)}</h3><p class="tag">Direction: ${esc(c.trend)}</p>
      <h6>Permanent residence</h6><p>${esc(trimTo(c.pr, 210))}</p><h6>Citizenship</h6><p>${esc(trimTo(c.citizenship, 210))}</p>
      <div class="pc"><div class="pos"><h6>A positive</h6><p>${esc(trimTo(c.pro, 150))}</p></div><div class="neg"><h6>A negative</h6><p>${esc(trimTo(c.con, 150))}</p></div></div>
      <p><a class="read" href="#immigration/files">Open all 19 Country Files &rarr;</a></p></section>`;
  }

  function deskColumn(desk, d) {
    if (!d || !d.items.length) return "";
    return `<section class="dcol"><h3><a href="${DESK_LINK[desk]}">${esc(desk)} Desk</a></h3>
      <div class="dstat">${d.total} on file &middot; ${d.new_today} new today</div>${d.items.map(miniCard).join("")}
      <a class="read" href="${DESK_LINK[desk]}">Open the ${esc(desk)} Desk &rarr;</a></section>`;
  }

  let frontData = null, interest = "All";
  function frontView(data) {
    frontData = data;
    const built = new Date(data.built.replace(" IST", "").replace(" ", "T") + ":00+05:30");
    const hours = (Date.now() - built.getTime()) / 36e5;
    const stale = hours > 30
      ? `<p class="stale">The last refresh was ${Math.round(hours)} hours ago (${esc(data.built)}). The scheduled run may have been missed; the stories below may be out of date.</p>` : "";
    const counts = Object.entries(data.by_desk).map(([d, n]) => `${n} ${d}`).join(" &middot; ");
    return `<div class="frontnote"><b>${data.count} stories to read today</b> &middot; ${counts} &middot; Edition of ${esc(data.edition)}, built ${esc(data.built)}</div>${stale}
      ${marketStrip(data.markets)}<div class="choose"><span class="cl">Choose your interest</span><div id="interest" class="chips"></div></div><div id="frontbody"></div>`;
  }

  function paintFront() {
    const d = frontData;
    const extra = Object.values(d.desks).flatMap((x) => x.items);
    const all = [...d.items, ...extra];
    const tagCount = {};
    all.forEach((i) => (i.tags || []).forEach((t) => (tagCount[t] = (tagCount[t] || 0) + 1)));
    const tags = Object.entries(tagCount).filter(([t, n]) => n >= 2 && !DESK_LINK[t]).sort((a, b) => b[1] - a[1]).slice(0, 9).map(([t]) => t);
    const opts = ["All", "Policy", "Startups", "Immigration", ...tags];
    $("interest").innerHTML = opts.map((o) => `<button class="chip" type="button" aria-pressed="${interest === o}" data-v="${esc(o)}">${esc(o)}</button>`).join("");
    $("interest").onclick = (e) => {
      const b = e.target.closest("button");
      if (b) { interest = b.dataset.v; paintFront(); }
    };
    let html;
    if (interest === "All") {
      const [hero, ...rest] = d.items;
      html = heroCard(hero) + `<div class="gridcards">${rest.slice(0, 4).map(gridCard).join("")}</div>` +
        `<div class="feats">${startupFileBox(d.features.startup_file)}${countryBox(d.features.country)}</div>` +
        `<h2 class="sect">More headlines</h2>${rest.slice(4).map((it, i) => rowCard(it, i + 6)).join("")}` +
        `<h2 class="sect">Snapshots from the desks</h2><div class="dcols">${["Policy", "Startups", "Immigration"].map((k) => deskColumn(k, d.desks[k])).join("")}</div>`;
    } else {
      const sel = all.filter((i) => i.desk === interest || (i.tags || []).includes(interest))
        .sort((a, b) => b.priority - a.priority);
      const [hero, ...rest] = sel;
      html = hero
        ? `<p class="frontnote"><b>${sel.length} stories</b> for "${esc(interest)}"</p>` + heroCard(hero) +
          `<div class="gridcards">${rest.slice(0, 4).map(gridCard).join("")}</div>` +
          (rest.length > 4 ? `<h2 class="sect">More on ${esc(interest)}</h2>${rest.slice(4).map((it) => rowCard(it)).join("")}` : "")
        : '<p class="empty">Nothing on the front page for that interest today.</p>';
    }
    $("frontbody").innerHTML = html;
  }

  const srcLinks = (a) => (a && a.length ? `<p class="fine">Sources: ${a.map((s) => link(s.url, esc(s.label))).join(" &middot; ")}</p>` : "");

  function countryCard(c) {
    const row = (k, v) => `<div class="kv"><b>${k}</b><span>${esc(v)}</span></div>`;
    return `<details class="cfile" data-name="${esc(c.name.toLowerCase())}"><summary><span class="cname">${esc(c.name)}</span>
      <span class="trend">${esc(c.trend)}</span></summary>
      ${row("Work route", c.route)}${row("Permanent residence", c.pr)}${row("Citizenship", c.citizenship)}
      ${row("Language", c.language)}${row("Finance career", c.finance)}
      <div class="pc"><div class="pos"><h4>Positives</h4>${list(c.pros)}</div><div class="neg"><h4>Negatives</h4>${list(c.cons)}</div></div>
      <h4>Watch</h4>${list(c.watch)}${srcLinks(c.sources)}</details>`;
  }

  let sortKey = "name", sortDir = 1;
  function filesView(files, q) {
    q = (q || "").toLowerCase();
    let cs = files.countries.filter((c) => !q || c.name.toLowerCase().includes(q) || c.trend.toLowerCase().includes(q));
    const val = (c) => (sortKey === "name" ? c.name : c[sortKey] == null ? 999 : c[sortKey]);
    cs = cs.slice().sort((a, b) => (val(a) > val(b) ? 1 : val(a) < val(b) ? -1 : 0) * sortDir);
    const fmt = (n, dflt) => (n == null ? dflt : n === 0 ? "on arrival" : (n === 1 ? "1 yr" : `${n} yrs`));
    const head = (k, t) => `<th><button type="button" data-sort="${k}">${t}${sortKey === k ? (sortDir > 0 ? " ▲" : " ▼") : ""}</button></th>`;
    return `<p class="note">${esc(files.note)} <b>Checked ${esc(files.checked)}.</b></p>
      <p class="note">Table columns are the fastest realistic route for a skilled worker with an employer (or points) as reported. Click a header to sort. No ranking is implied: read the negatives alongside the positives.</p>
      <div class="tablewrap"><table class="cmp"><thead><tr>${head("name", "Country")}${head("prSort", "Fastest PR")}${head("citSort", "Citizenship")}<th>Direction</th></tr></thead><tbody>
      ${cs.map((c) => `<tr><td><a href="#immigration/files" data-open="${esc(c.id)}">${esc(c.name)}</a></td><td>${esc(fmt(c.prSort, "see file"))}</td><td>${esc(fmt(c.citSort, "see file"))}</td><td>${esc(c.trend)}</td></tr>`).join("")}
      </tbody></table></div>
      ${cs.map(countryCard).join("")}`;
  }

  function indiaView(files, q) {
    q = (q || "").toLowerCase();
    return files.india_side.filter((s) => !q || (s.title + s.points.join(" ")).toLowerCase().includes(q)).map((s) =>
      `<article class="card"><div class="meta"><span class="badge ${s.verified ? "src" : "major"}">${s.verified ? "RESEARCHED" : "TO RESEARCH"}</span></div>
        <h3>${esc(s.title)}</h3>${list(s.points)}${srcLinks(s.sources)}</article>`).join("");
  }

  function autoBits(it) {
    const bits = [];
    if (it.what) bits.push(`<div class="auto"><b>What it does (from the article):</b> ${esc(it.what)}</div>`);
    if ((it.financials || []).length) bits.push(`<div class="auto"><b>Numbers mentioned:</b>${list(it.financials)}</div>`);
    return bits.join("");
  }

  function fileBox(p) {
    return `<details class="file" open><summary>Startup File: ${esc(p.company)}</summary>
      <h4>What they do</h4><p>${esc(p.what)}</p>
      <h4>How they make money</h4>${list(p.how)}
      <h4>Numbers</h4>${list(p.numbers)}
      <h4>Watch</h4><p>${esc(p.watch)}</p>
      <h4>Takeaway</h4><p>${esc(p.lesson)}</p>
      <p class="fine">Written ${esc(p.written)} from: ${(p.sources || []).map((u, n) => link(u, `source ${n + 1}`)).join(", ")}</p></details>`;
  }

  function shell(lead, meta, it, body, cta) {
    if (lead) {
      return `<div class="kicker">Lead story &middot; ${meta}</div>
        <h2>${link(it.url, esc(it.title))}</h2>${body}${link(it.url, cta + " &rarr;", "read")}`;
    }
    return `<article class="card"><div class="meta">${meta}</div><h3>${link(it.url, esc(it.title))}</h3>${body}${link(it.url, cta + " &rarr;", "read")}</article>`;
  }

  // ---------------------------------------------------------------- state / render
  let desk, sub, cfg, items, state, leadItem;

  function chips(el, values, key) {
    el.innerHTML = values.length ? ["All", ...values].map((v) => `<button class="chip" type="button" aria-pressed="${state[key] === v}" data-v="${esc(v)}">${esc(v)}</button>`).join("") : "";
    el.onclick = (e) => {
      const b = e.target.closest("button");
      if (!b) return;
      state[key] = b.dataset.v;
      chips(el, values, key);
      render();
    };
  }
  const uniq = (key) => [...new Set(items.map((i) => i[key]))].filter(Boolean).sort();

  function visible() {
    const q = state.q.trim().toLowerCase();
    return items.filter((i) =>
      (state.f1 === "All" || i[cfg.f1.key] === state.f1) &&
      (!cfg.f2 || state.f2 === "All" || i[cfg.f2.key] === state.f2) &&
      (!cfg.f3 || state.f3 === "All" || i[cfg.f3.key] === state.f3) &&
      (!state.flag || cfg.flag.test(i)) &&
      (!q || cfg.search(i).toLowerCase().includes(q)));
  }

  function render() {
    const rows = visible();
    $("count").textContent = `${rows.length} of ${items.length} items`;
    $("empty").hidden = rows.length > 0;
    let html = "", d = "";
    const plain = !state.q && state.f1 === "All" && state.f2 === "All" && state.f3 === "All" && !state.flag;
    for (const it of rows) {
      if (plain && it === leadItem) continue; // already shown as the lead story
      if (it.date !== d) { d = it.date; html += `<h2 class="day">${day(d)}</h2>`; }
      html += cfg.card(it, false);
    }
    $("feed").innerHTML = html;
  }

  async function load(hash) {
    const [name, subId] = hash.split("/");
    desk = DESKS[name] ? name : "top";
    cfg = DESKS[desk];
    sub = cfg.subs ? (cfg.subs.find((s) => s.id === subId) || cfg.subs[0]) : null;
    document.querySelectorAll(".desk").forEach((a) => a.classList.toggle("active", a.dataset.desk === desk));
    $("feed").innerHTML = '<p class="empty">Loading...</p>';
    $("lead").hidden = true;
    try {
      await briefsReady;
      const res = await fetch(cfg.file, { cache: "no-cache" });
      const data = await res.json();
      items = data.items;
      const controls = document.querySelector(".controls");
      controls.hidden = !!cfg.front;
      if (cfg.front) {
        $("subs").hidden = true;
        $("lead").hidden = true;
        $("empty").hidden = true;
        $("edition").textContent = `Front Page · ${data.count} stories`;
        $("updated").textContent = `Last refreshed ${data.built}`;
        $("sources").textContent = cfg.sources;
        $("feed").innerHTML = frontView(data);
        interest = subId ? decodeURIComponent(subId) : "All";   // #top/Startups opens the page on that interest
        paintFront();
        state = { q: "", f1: "All", f2: "All", f3: "All", flag: false };
        return;
      }
      if (desk === "startups") {
        const pr = await fetch("data/profiles.json", { cache: "no-cache" }).then((r) => r.json()).catch(() => ({ profiles: [] }));
        const byKey = Object.fromEntries(pr.profiles.map((p) => [p.key, p]));
        items.forEach((i) => { i.profile = byKey[i.url] || null; });
        // A Startup File whose story has aged out of the feed still appears, so nothing written is lost.
        pr.profiles.filter((p) => !items.some((i) => i.url === p.key)).forEach((p) =>
          items.push({ id: p.key, source: "Startup File", region: "", title: p.company, date: p.written, url: p.sources[0], company: p.company,
            type: "Startup File", sector: p.sector, blurb: p.tagline, profile: p, region: p.region || "India" }));
        items.sort((a, b) => (a.date < b.date ? 1 : -1));
      }
      let files = null;
      if (desk === "immigration") {
        files = await fetch("data/immigration_files.json", { cache: "no-cache" }).then((r) => r.json());
        const nm = Object.fromEntries(files.countries.map((c) => [c.id, c.name]));
        items.forEach((i) => { i.countryLabel = nm[i.country] || i.country; });
      }
      const subNav = $("subs");
      if (desk === "immigration") {
        const counts = { news: items.length, files: files.countries.length, india: files.india_side.length };
        subNav.innerHTML = cfg.subs.map((s) => `<a href="#${desk}/${s.id}" class="${s.id === sub.id ? "active" : ""}">${esc(s.label)}<small>${counts[s.id]}</small></a>`).join("");
        subNav.hidden = false;
      } else if (sub) {
        const all = items;
        subNav.innerHTML = cfg.subs.map((s) => `<a href="#${desk}/${s.id}" class="${s.id === sub.id ? "active" : ""}">${esc(s.label)}<small>${all.filter(s.test).length}</small></a>`).join("");
        subNav.hidden = false;
        items = all.filter(sub.test);
      } else { subNav.hidden = true; }
      state = { q: "", f1: "All", f2: "All", f3: "All", flag: false };
      const special = !!(sub && sub.view);
      document.querySelector(".controls").classList.toggle("bare", special);
      if (special) {
        $("lead").hidden = true;
        $("count").textContent = "";
        $("empty").hidden = true;
        $("edition").textContent = `${cfg.title} · ${sub.label}`;
        $("updated").textContent = `Research date ${files.checked}`;
        $("sources").textContent = cfg.sources;
        $("q").value = "";
        const paint = () => {
          $("feed").innerHTML = sub.view === "files" ? filesView(files, state.q) : indiaView(files, state.q);
          $("feed").querySelectorAll("[data-sort]").forEach((b) => (b.onclick = () => {
            const k = b.dataset.sort; sortDir = sortKey === k ? -sortDir : 1; sortKey = k; paint();
          }));
          $("feed").querySelectorAll("[data-open]").forEach((a) => (a.onclick = (e) => {
            e.preventDefault();
            const c = files.countries.find((x) => x.id === a.dataset.open);
            const d = [...document.querySelectorAll(".cfile")].find((x) => x.dataset.name === c.name.toLowerCase());
            if (d) { d.open = true; d.scrollIntoView({ behavior: "smooth", block: "start" }); }
          }));
        };
        window.__paint = paint;
        paint();
        return;
      }
      $("q").value = ""; $("flag").checked = false; $("flagLabel").textContent = cfg.flag.label;
      chips($("f1"), uniq(cfg.f1.key), "f1");
      chips($("f2"), cfg.f2 ? uniq(cfg.f2.key) : [], "f2");
      chips($("f3"), cfg.f3 ? (cfg.f3.values || uniq(cfg.f3.key)) : [], "f3");
      $("edition").textContent = `${sub ? sub.label : cfg.title} · ${items.length} items on file`;
      $("updated").textContent = `Last refreshed ${data.updated}`;
      $("sources").textContent = cfg.sources;
      const top = leadItem = cfg.lead(items);
      if (top) { $("lead").innerHTML = cfg.card(top, true); $("lead").hidden = false; }
      render();
    } catch (e) {
      $("feed").innerHTML = `<p class="empty">Could not load ${esc(cfg.file)}.</p>`;
    }
  }

  $("today").textContent = new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  $("q").oninput = (e) => { state.q = e.target.value; if (sub && sub.view) { window.__paint(); } else { render(); } };
  $("flag").onchange = (e) => { state.flag = e.target.checked; render(); };
  window.addEventListener("hashchange", () => load(location.hash.slice(1)));
  load(location.hash.slice(1));
})();
