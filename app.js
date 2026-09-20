// Updates for Pal: renders data/*.json, one desk per data file. No libraries, no external calls.
(function () {
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const day = (iso) => new Date(iso + "T00:00:00").toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  const link = (u, t, cls) => `<a ${cls ? `class="${cls}" ` : ""}href="${esc(u)}" target="_blank" rel="noopener">${t}</a>`;
  const list = (a) => (a && a.length ? `<ul>${a.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : "");

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
        return shell(lead, meta, it, `<p>${esc(it.summary)}</p>${extra}`, "Read the original");
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
        const body = `<p>${esc(it.profile ? it.profile.tagline + ". " : "")}${esc(it.blurb)}</p>${dealHtml}${it.profile ? fileBox(it.profile) : autoBits(it)}${also}`;
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
      return shell(lead, meta, it, "", it.official ? "Read the official notice" : "Read the article");
    },
  };

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
    desk = DESKS[name] ? name : "policy";
    cfg = DESKS[desk];
    sub = cfg.subs ? (cfg.subs.find((s) => s.id === subId) || cfg.subs[0]) : null;
    document.querySelectorAll(".desk").forEach((a) => a.classList.toggle("active", a.dataset.desk === desk));
    $("feed").innerHTML = '<p class="empty">Loading...</p>';
    $("lead").hidden = true;
    try {
      const res = await fetch(cfg.file, { cache: "no-cache" });
      const data = await res.json();
      items = data.items;
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
