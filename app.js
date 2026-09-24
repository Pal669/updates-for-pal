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

  // ---------------------------------------------------------------- Migration Desk (internal key: immigration)
  DESKS.immigration = {
    file: "data/immigration.json",
    title: "Migration Desk",
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

  // ---------------------------------------------------------------- My Area Desk (hyperlocal)
  DESKS.myarea = {
    file: "data/myarea.json",
    title: "My Area",
    sources: "Live web search: .gov.in portals (official priority), then credible news (48-hour window). Every story verified as VERIFIED (official or 2+ sources), LIKELY (1 credible source), or UNVERIFIED (social-only, not published).",
    subs: [],
    f1: { key: "category" },
    f2: { key: "tag", values: ["VERIFIED", "LIKELY", "UNVERIFIED"] },
    f3: null,
    flag: { label: "Verified only", test: (i) => i.tag === "VERIFIED" },
    search: (i) => `${i.pincode} ${i.locality} ${i.title} ${i.category} ${i.what_happened}`,
    lead: (items) => items[0],
    card(it, lead) {
      const tags = `<span class="badge ${esc(it.tag.toLowerCase())}">${esc(it.tag)}</span><span class="badge type">${esc(it.category)}</span>`;
      const meta = `${tags}${esc(it.pincode)} &middot; ${esc(it.locality)} &middot; ${esc(it.source)}`;
      const body = `<p><strong>${esc(it.what_happened)}</strong></p><div class="whybox"><h6>Why it matters</h6><p>${esc(it.why_matters)}</p></div><div class="more">Action: ${esc(it.action)}</div>`;
      return shell(lead, meta, it, body, "View source");
    },
  };

  // ---------------------------------------------------------------- Listed Market Universe Desk
  let companies = {}, notes = {};     // data/companies.json (live financials) and data/company_notes.json (hand-written business notes)
  // How a business of this Yahoo industry usually earns, used only when there is no hand-written note. Labelled as typical.
  const MODELS = [
    [/bank|credit services|mortgage finance|capital markets|financial conglomerates/i, "Lenders earn the gap between interest charged on loans and interest paid on deposits or borrowings, plus fees."],
    [/insurance/i, "Insurers collect premiums, invest them, and pay claims later; profit comes from underwriting margin and investment income."],
    [/asset management/i, "Asset managers earn a fee as a percentage of the money they manage."],
    [/software|information technology|it services/i, "Earns by billing clients for services or licences, usually per project, per hour or per subscription."],
    [/drug|pharma|biotech/i, "Earns by selling medicines and ingredients to hospitals, pharmacies, distributors and other drug companies."],
    [/auto|vehicle|motorcycle/i, "Earns by selling vehicles or parts to dealers and carmakers, at a margin over material and labour cost."],
    [/steel|aluminum|copper|metal|mining|coal|zinc/i, "Earns the gap between what it sells metal or mineral products for and the cost of raw material, energy and processing; profit swings with commodity prices."],
    [/oil|gas|refining|petro/i, "Earns from the price of oil and gas products minus the cost of getting and processing them."],
    [/utilities|power|electric/i, "Earns by selling electricity, often under long-term contracts or regulated tariffs."],
    [/real estate|realty|developer/i, "Earns by selling homes or offices it builds and by collecting rent."],
    [/cement|building materials|construction materials/i, "Earns the gap between the price of cement or building material and the cost of making and moving it."],
    [/engineering|construction|infrastructure|machinery|electrical equipment/i, "Earns by executing contracts and selling equipment; revenue follows the order book."],
    [/retail|stores|department|apparel|footwear|jewel/i, "Earns by selling goods to consumers at a margin over what it paid for them."],
    [/beverage|food|packaged|household|personal products|tobacco|consumer/i, "Earns by selling branded goods through distributors and shops at a margin over raw material cost."],
    [/chemical|fertili|agri/i, "Earns by selling chemicals or farm inputs; margins swing with raw material prices."],
    [/textile|garment/i, "Earns by making and selling fabric or garments, mostly to brands and exporters."],
    [/telecom|communication|media|broadcast/i, "Earns from subscriptions, advertising or connectivity fees."],
    [/airline|shipping|transport|logistics|marine|railroad/i, "Earns by charging for moving people or goods; profit swings with fuel cost and traffic."],
    [/hospital|healthcare|medical|diagnostic/i, "Earns from fees for treatment, tests or medical products."],
  ];
  const modelFor = (co) => { const m = MODELS.find(([rx]) => rx.test(`${co.industry || ""} ${co.sector || ""}`)); return m ? m[1] : ""; };
  const firstSentences = (t, n) => { const parts = (t || "").replace(/\s+/g, " ").match(/[^.]+\.(?:\s|$)/g) || [t || ""]; return trimText(parts.slice(0, 2).join(" ").trim(), n); };
  const cr = (v) => v == null ? "n/a" : (Math.abs(v) >= 100000 ? `₹${(v / 100000).toFixed(2)} lakh cr` : `₹${Math.round(v).toLocaleString("en-IN")} cr`);
  const fyOf = (d) => { const t = new Date(d + "T00:00:00"), m = t.getMonth() + 1, y = t.getFullYear(); return `FY${String(m <= 6 ? y : y + 1).slice(2)} (${t.toLocaleDateString("en-IN", { month: "short", year: "numeric" })})`; };
  const pctChange = (a, b) => (a != null && b != null && b > 0 ? ((a - b) / b) * 100 : null);

  // Company name -> its page on screener.in (NSE symbol or BSE scrip code both work in the URL). Click must not toggle the <details>.
  const scr = (it, nameHtml) => it.symbol
    ? `<a class="co-link" href="https://www.screener.in/company/${encodeURIComponent(it.symbol)}/" target="_blank" rel="noopener" onclick="event.stopPropagation()">${nameHtml}</a>` : nameHtml;

  function snapshotHtml(it, open) {
    const co = it.ckey ? companies[it.ckey] : null;
    const n = notes[it.symbol] || null;
    const has = !!(co && ((co.years && co.years.length) || co.summary));
    if (!has && !n) {
      return it.ckey ? `<div class="snap none"><b>Company snapshot:</b> no financial statements or business profile were found for ${esc(it.company)} on Yahoo Finance or Screener.in. This usually means a very new or small (SME) listing that has not published a full year yet. It is retried every week.</div>` : "";
    }
    const yrs = has ? (co.years || []) : [];
    const last = yrs[yrs.length - 1], prev = yrs[yrs.length - 2];
    const isLender = has && /bank|credit services|insurance|mortgage|capital markets|financial/i.test(`${co.industry} ${co.sector}`);
    const type = (n && n.type) || (has ? [co.industry, co.sector].filter(Boolean).join(" · ") : "");
    const does = (n && n.does) || (has && co.summary ? firstSentences(co.summary, 380) : "");
    const earns = (n && n.earns) || (has ? modelFor(co) : "");
    const earnsLabel = n && n.earns ? "How it makes money" : "How it makes money (typical for this kind of business)";
    let plain = "";
    if (last) {
      const g = prev ? pctChange(last.net_income, prev.net_income) : null;
      const pl = last.net_income == null ? "" : last.net_income >= 0
        ? `In ${fyOf(last.asof)} it made a net profit of ${cr(last.net_income)}${g != null && prev.net_income > 0 ? `, ${g >= 0 ? "up" : "down"} ${Math.abs(g).toFixed(0)}% from the year before` : ""}.`
        : `In ${fyOf(last.asof)} it made a net LOSS of ${cr(Math.abs(last.net_income))}${prev && prev.net_income != null ? (prev.net_income >= 0 ? ", after a profit the year before" : ", after a loss the year before") : ""}.`;
      const cf = last.ocf == null ? "" : ` Its operations brought in ${cr(last.ocf)} of cash${last.fcf == null ? "." : `; after spending on plant and equipment, free cash flow was ${last.fcf >= 0 ? cr(last.fcf) : "negative " + cr(Math.abs(last.fcf))} (${last.fcf >= 0 ? "it funds its growth from its own cash" : "it spent more than its operations earned, so it borrowed or used savings"}).`}`;
      plain = `<p class="plain">${esc(pl + (isLender ? " For banks and lenders the cash-flow lines are not a useful measure; look at profit and loan quality." : cf))}</p>`;
    }
    const hasTtm = has && co.ttm && co.ttm.asof;
    const colHead = yrs.map((y) => `<th>${esc(fyOf(y.asof))}</th>`).join("") + (hasTtm ? `<th>Last 12 months (to ${esc(co.ttm.asof)})</th>` : "");
    const row = (label, key) => {
      const cells = yrs.map((y) => y[key]);
      if (hasTtm) cells.push(co.ttm[key]);
      if (cells.every((v) => v == null)) return "";
      return `<tr><td>${label}</td>${cells.map((v) => `<td class="${v != null && v < 0 ? "neg" : ""}">${v == null ? "n/a" : v < 0 ? "(" + cr(Math.abs(v)) + ")" : cr(v)}</td>`).join("")}</tr>`;
    };
    const table = yrs.length
      ? `<div class="tablewrap"><table class="fin"><thead><tr><th></th>${colHead}</tr></thead><tbody>${row("Revenue", "revenue")}${row("Net profit / (loss)", "net_income")}${isLender ? "" : row("Cash from operations", "ocf")}${isLender ? "" : row("Free cash flow", "fcf")}${row("Total debt", "debt")}</tbody></table></div>` : "";
    const badge = last && last.net_income != null ? `<span class="badge ${last.net_income >= 0 ? "prof" : "loss"}">${last.net_income >= 0 ? "PROFITABLE" : "LOSS-MAKING"}</span>` : "";
    const head = `About ${scr(it, esc(has && co.name ? co.name.replace(/ Limited$/i, "") : it.company))}: ${esc(type || "business snapshot")}${last && last.revenue != null ? ` &middot; revenue ${esc(cr(last.revenue))}` : ""}`;
    const ratioBits = has ? [["P/E", co.pe, ""], ["ROCE", co.roce, "%"], ["ROE", co.roe, "%"], ["Book value", co.book_value, ""], ["Dividend yield", co.div_yield, "%"]]
      .filter((r) => r[1] != null).map((r) => `${r[0]} ${r[1]}${r[2]}`) : [];
    const ratios = ratioBits.length ? `<div class="kv2"><b>Key ratios</b><span>${esc(ratioBits.join(" · "))}</span></div>` : "";
    const mcap = has && co.mcap_cr ? `<div class="kv2"><b>Market value</b><span>${esc(cr(co.mcap_cr))}</span></div>` : "";
    const drivers = n && n.drivers ? `<div class="kv2"><b>What moves its profit</b><span>${esc(n.drivers)}</span></div>` : "";
    return `<details class="snap" open><summary>${badge}${head}</summary>
      ${does ? `<div class="kv2"><b>What it does</b><span>${esc(does)}</span></div>` : ""}
      ${earns ? `<div class="kv2"><b>${earnsLabel}</b><span>${esc(earns)}</span></div>` : ""}
      ${type ? `<div class="kv2"><b>Kind of business</b><span>${esc(type)}</span></div>` : ""}${drivers}${mcap}${ratios}
      ${plain}${table}${has && !yrs.length ? `<p class="fine">No yearly financial statements are published yet for this company (typically a recent or SME listing), so revenue, profit and cash flow cannot be shown.</p>` : ""}
      <p class="fine">${last ? `Financials: ${esc(co.source || "Yahoo Finance")}, fetched ${esc(co.fetched || "")}, in rupees, as reported; check the company's own results before relying on them.` : ""}${n ? " Business notes written by hand from general knowledge." : ""}${!n && does ? " Business description is the company's public profile." : ""}</p></details>`;
  }

  function impactHtml(it) {
    const im = it.impact;
    if (!im) return "";
    const label = { High: "High", Medium: "Medium", Low: "Low", "Not stated": "Not stated in the text", "Check numbers": "Depends on the numbers" }[im.level] || im.level;
    return `<div class="impact imp-${esc(im.level.replace(/\s+/g, ""))}"><h6>How much could this matter to the company? <b>${esc(label)}</b></h6>
      <ul>${im.basis.map((b) => `<li>${esc(b)}</li>`).join("")}</ul>
      <p class="fine">A size check against the company's own figures using fixed rules, not a forecast of the share price.</p></div>`;
  }

  DESKS.listed = {
    file: "data/listed.json",
    title: "India's Listed Market Universe",
    sources: "Sources: NSE and BSE corporate announcements (the company's own filing, with the exchange's one-line summary and a link to the PDF), Economic Times, Business Standard, Mint, BusinessLine, Moneycontrol and Google News headlines. Company financials: Yahoo Finance, with Screener.in for companies Yahoo does not cover. Business notes for the Nifty 100 are written by hand; other companies use their public profile. Routine filings (AGM notices, trading window, ESOP allotments, shareholding paperwork) are left out; nothing is rewritten by a model. Press headlines are matched to companies by name, so an occasional mismatch is possible. The impact line compares an amount in the event with the company's revenue, profit or market value by fixed rules. Not investment advice: open the filing before acting.",
    subs: [
      { id: "nifty100", label: "Nifty 100", test: (i) => i.universe === "nifty100" },
      { id: "other", label: "All Other Companies", test: (i) => i.universe !== "nifty100" },
    ],
    f1: { key: "category" }, f2: { key: "industry" }, f3: { key: "kind", values: ["Exchange filing", "Press"] },
    flag: { label: "High or medium impact only", test: (i) => i.impact && (i.impact.level === "High" || i.impact.level === "Medium") },
    search: (i) => `${i.title} ${i.summary} ${i.company} ${i.symbol} ${i.industry} ${i.category} ${i.source} ${(notes[i.symbol] || {}).type || ""}`,
    lead: (items) => items.find((i) => i.impact && i.impact.level === "High" && i.kind === "Exchange filing") || items.find((i) => i.major && i.kind === "Exchange filing") || items.find((i) => i.major) || items[0],
    card(it, lead) {
      const lvl = it.impact ? it.impact.level : "Not stated";
      const b = `<span class="badge ${it.kind === "Press" ? "src" : "major"}">${it.kind === "Press" ? "PRESS" : esc(it.source)}</span><span class="badge type">${esc(it.category)}</span>` +
        (lvl === "High" || lvl === "Medium" ? `<span class="badge imp-${lvl}">IMPACT: ${lvl.toUpperCase()}</span>` : "");
      const who = [it.company ? scr(it, esc(it.company)) : "", esc(it.symbol && it.source === "NSE" ? it.symbol : ""), esc(it.industry), esc(it.kind === "Press" ? it.source : "")].filter(Boolean).join(" &middot; ");
      const also = (it.also || []).length ? `<div class="more">Also mentioned: ${it.also.map(esc).join(", ")}</div>` : "";
      const body = (it.summary ? `<p>${esc(it.summary)}</p>` : "") + (it.time ? `<div class="fine">${esc(it.date)} ${esc(it.time)} IST</div>` : "") + also +
        impactHtml(it) + snapshotHtml(it, lead);
      return shell(lead, `${b}${who}`, it, body, it.kind === "Press" ? "Open the original" : "Open the filing");
    },
  };

  // ---------------------------------------------------------------- Investment Advisory Universe Desk
  // Numbers come from data/advisory_market.json, PMS/AIF strategies from data/pms_aif.json, official PMS AUM from
  // data/pms_aum_official.json, headlines from data/advisory.json. No commentary anywhere: figures and links only.
  let advMarket = null, advPms = null, advAum = null, advCat3 = null;
  const jget = (f) => fetch(f, { cache: "no-cache" }).then((r) => r.json()).catch(() => null);
  async function advisoryPrep() {
    [advMarket, advPms, advAum, advCat3] = await Promise.all([jget("data/advisory_market.json"), jget("data/pms_aif.json"), jget("data/pms_aum_official.json"), jget("data/aif_cat3.json")]);
  }
  const dp = (v, d) => (v == null || isNaN(v) ? "–" : Number(v).toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d }));
  const sgn = (v, d, suf) => (v == null || isNaN(v) ? '<span class="na">–</span>'
    : `<span class="${v > 0 ? "up" : v < 0 ? "dn" : "fl"}">${v > 0 ? "+" : ""}${dp(v, d)}${suf}</span>`);
  const heat = (v, s) => (v == null ? "" : ` style="background:rgba(${v >= 0 ? "31,122,63" : "179,38,30"},${(Math.min(Math.abs(v) / s, 1) * 0.34).toFixed(2)})"`);
  const PERIOD_KEYS = [["d1", "1D"], ["w1", "1W"], ["m1", "1M"], ["y1", "1Y"]];
  const srcOf = (rows) => [...new Set(rows.map((r) => r.source).filter(Boolean))].join(", ");
  const asofOf = (rows) => (rows.map((r) => r.asof).filter(Boolean).sort().slice(-1)[0] || "");

  function mkTable(title, rows, opts) {
    if (!rows || !rows.length) return "";
    opts = opts || {};
    const bp = (r) => r.unit === "bp";
    const body = rows.map((r) => `<tr><td>${esc(r.name)}${r.kind ? ` <small class="k">${esc(r.kind)}</small>` : ""}</td><td class="n">${dp(r.value, r.dp == null ? 2 : r.dp)}</td>` +
      PERIOD_KEYS.map(([k]) => `<td class="n">${sgn(r[k], bp(r) ? 1 : 2, bp(r) ? " bp" : "%")}</td>`).join("") +
      (opts.pe ? `<td class="n">${dp(r.pe, 1)}</td>` : "") + "</tr>").join("");
    return `<h3 class="nh">${esc(title)}</h3><div class="tablewrap"><table class="nt"><thead><tr><th>Name</th><th class="n">Level</th>${PERIOD_KEYS.map(([, l]) => `<th class="n">${l}</th>`).join("")}${opts.pe ? '<th class="n">P/E</th>' : ""}</tr></thead><tbody>${body}</tbody></table></div>
      <p class="fine">Source: ${esc(srcOf(rows))}${asofOf(rows) ? `; last price ${esc(asofOf(rows))}` : ""}.${opts.note ? " " + esc(opts.note) : ""}</p>`;
  }

  let secKey = "d1";
  function sectorBoard() {
    const m = advMarket;
    if (!m.sectors || !m.sectors.length) return "";
    const rows = m.sectors.slice().sort((a, b) => (b[secKey] == null ? -1e9 : b[secKey]) - (a[secKey] == null ? -1e9 : a[secKey]));
    const scale = { d1: 2, w1: 4, m1: 8, y1: 30 };
    const buttons = PERIOD_KEYS.map(([k, l]) => `<button type="button" class="chip" data-sec="${k}" aria-pressed="${secKey === k}">Rank by ${l}</button>`).join("");
    const body = rows.map((r) => `<tr><td>${esc(r.name)}</td><td class="n">${dp(r.value, 2)}</td>` +
      PERIOD_KEYS.map(([k]) => `<td class="n"${heat(r[k], scale[k])}>${sgn(r[k], 2, "%")}</td>`).join("") + `<td class="n">${dp(r.pe, 1)}</td></tr>`).join("");
    const lists = ["w1", "m1"].map((k) => {
      const ok = m.sectors.filter((r) => r[k] != null).sort((a, b) => b[k] - a[k]);
      const li = (r) => `<li>${esc(r.name)} ${sgn(r[k], 2, "%")}</li>`;
      return `<div class="hc"><h4>${k === "w1" ? "1 week" : "1 month"}: leading</h4><ol>${ok.slice(0, 3).map(li).join("")}</ol>
        <h4>${k === "w1" ? "1 week" : "1 month"}: lagging</h4><ol>${ok.slice(-3).reverse().map(li).join("")}</ol></div>`;
    }).join("");
    return `<h3 class="nh">Sector board: what is hot and what is not</h3><div class="chips secbtn">${buttons}</div>
      <div class="hotcold">${lists}</div>
      <div class="tablewrap"><table class="nt"><thead><tr><th>Sector index</th><th class="n">Level</th>${PERIOD_KEYS.map(([, l]) => `<th class="n">${l}</th>`).join("")}<th class="n">P/E</th></tr></thead><tbody>${body}</tbody></table></div>
      <p class="fine">Source: ${esc(srcOf(m.sectors))}. Colour depth shows the size of the move. Ranking is arithmetic on published index levels, not a view. P/E is the index's own published figure.</p>`;
  }

  function statStrip() {
    const m = advMarket;
    const stats = [];
    const nifty = (m.indices || []).find((r) => r.name === "Nifty 50"), n500 = (m.indices || []).find((r) => r.name === "Nifty 500"), vix = (m.indices || []).find((r) => r.name === "India VIX");
    if (m.flows && m.flows.fii) {
      const f = m.flows;
      stats.push(["FII/FPI net (cash, " + f.date + ")", `${sgn(f.fii.net, 0, "")} <small>Rs Cr</small>`], ["DII net (cash, " + f.date + ")", `${sgn(f.dii.net, 0, "")} <small>Rs Cr</small>`]);
    }
    if (nifty && nifty.adv != null) stats.push(["Nifty 50 breadth", `${nifty.adv} up / ${nifty.dec} down`]);
    if (n500 && n500.adv != null) stats.push(["Nifty 500 breadth", `${n500.adv} up / ${n500.dec} down`]);
    if (nifty && nifty.pe) stats.push(["Nifty 50 P/E", dp(nifty.pe, 2)]);
    if (vix) stats.push(["India VIX", `${dp(vix.value, 2)} ${sgn(vix.d1, 2, "%")}`]);
    if (m.gsec10y) stats.push(["India 10Y G-Sec", `${dp(m.gsec10y.value, 3)}%`]);
    if (m.gold_silver_ratio) stats.push(["Gold / silver ratio", dp(m.gold_silver_ratio, 2)]);
    return stats.length ? `<div class="statrow">${stats.map(([k, v]) => `<div class="stat"><span>${esc(k)}</span><b>${v}</b></div>`).join("")}</div>` : "";
  }

  function policyRates() {
    const r = advMarket.policy_rates || [];
    if (!r.length) return "";
    return `<h3 class="nh">RBI policy rates and reserve ratios</h3><div class="tablewrap"><table class="nt"><tbody>${r.map((x) => `<tr><td>${esc(x.name)}</td><td class="n">${dp(x.value, 2)}%</td></tr>`).join("")}</tbody></table></div>
      <p class="fine">Source: Reserve Bank of India homepage (official), read at ${esc(advMarket.updated)}.</p>`;
  }

  function marketBlock(id) {
    const m = advMarket;
    const stale = m.updated && (Date.now() - new Date(m.updated.replace(" IST", "").replace(" ", "T") + ":00+05:30").getTime()) / 36e5 > 36
      ? `<p class="stale">The numbers were last refreshed ${esc(m.updated)}. The daily run may have been missed, so the figures below may be out of date.</p>` : "";
    const head = `<p class="note">Numbers refreshed once a day after the market close (last: ${esc(m.updated)}). Green is up, red is down; for yields, VIX and crude that says nothing about good or bad. ${(m.notes || []).map(esc).join(" ")}</p>${stale}`;
    const commodityNote = "Gold, silver, crude and copper are continuous front-month futures on Yahoo Finance: a one-day change can include a contract roll.";
    const idx = mkTable("Indices", m.indices, { pe: true });
    const glob = mkTable("Global markets", m.global);
    const fx = mkTable("Rates and currencies", [...(m.gsec10y ? [{ ...m.gsec10y, d1: null, w1: null, m1: null, y1: null }] : []), ...(m.rates_fx || [])]);
    const com = mkTable("Gold, silver, crude and metals", m.commodities, { note: commodityNote });
    const reit = mkTable("REITs and InvITs (prices)", m.reits);
    switch (id) {
      case "pulse": return head + statStrip() + idx + sectorBoard() + glob;
      case "debt": return head + statStrip() + policyRates() + fx;
      case "real": return head + com + reit;
      case "reg": return head + policyRates();
      case "global": return head + glob + fx + com;
      default: return "";
    }
  }

  // ---- PMS / AIF strategy tables
  const pmsState = { sort: "1y", dir: -1, cat: "All", q: "", track: "any", limit: 40, open: null };
  const aifState = { sort: "1y", dir: -1, section: "All", basis: "All", track: "any", q: "", limit: 40, dq: "", dlimit: 25 };
  let aumState = { q: "", limit: 25 };
  const pv = (s, k) => (s.ret ? s.ret[k] : null);
  const excess = (s, k) => (pv(s, k) != null && s.bench_ret && s.bench_ret[k] != null ? +(pv(s, k) - s.bench_ret[k]).toFixed(2) : null);
  const stratLink = (s) => `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.name || s.title)}</a>`;
  const firm = (s) => (s.label ? "" : "");
  const RET_COLS = [["1m", "1M"], ["3m", "3M"], ["6m", "6M"], ["1y", "1Y"], ["3y", "3Y"], ["5y", "5Y"], ["si", "Since start"]];

  function pmsRows() {
    const all = Object.values((advPms && advPms.strategies) || {}).filter((s) => s.title && /^PMS/.test(s.kind || ""));
    return all;
  }
  function detailRow(s, cols) {
    const br = s.bench_ret || {};
    const ret = RET_COLS.map(([k, l]) => `<td class="n">${sgn(pv(s, k), 2, "%")}</td><td class="n dim">${sgn(br[k], 2, "%")}</td>`).join("");
    const head = RET_COLS.map(([, l]) => `<th colspan="2">${l}</th>`).join("");
    const sub = RET_COLS.map(() => "<th>Fund</th><th>Bench</th>").join("");
    const facts = [["Portfolio manager", s.manager], ["Manager experience", s.experience], ["Inception", s.inception_text], ["Age", s.age],
      ["Corpus (approx.)", s.corpus_cr != null ? `Rs ${dp(s.corpus_cr, 2)} Cr` : null], ["Benchmark", s.bench], ["Stocks held", s.stocks != null ? s.stocks : s.stocks_text],
      ["Std deviation (1Y)", s.sd_1y != null ? dp(s.sd_1y, 2) + "%" : null], ["Positive months", s.pos_months != null ? dp(s.pos_months, 2) + "%" : null],
      ["Minimum ticket", s.ticket], ["Structure", s.structure], ["Type", s.fund_type]].filter((x) => x[1]);
    return `<tr class="drow"><td colspan="${cols}"><div class="dbox">
      ${s.label_mismatch ? `<p class="warn">The source page is titled "${esc(s.title)}" but its returns table is labelled "${esc(s.label)}". The figures are shown under the returns table's name. Check the source before relying on them.</p>` : ""}
      ${(s.ret && Object.keys(s.ret).length) ? `<div class="tablewrap"><table class="nt sm"><thead><tr>${head}</tr><tr>${sub}</tr></thead><tbody><tr>${ret}</tr></tbody></table></div>` : `<p class="fine">No returns are published for this one.</p>`}
      <div class="facts">${facts.map(([k, v]) => `<div><b>${esc(k)}</b><span>${esc(v)}</span></div>`).join("")}</div>
      <p class="fine">Source: ${link(s.url, "PMS AIF World page")} (fetched ${esc(s.fetched || "")}, returns as of ${esc(s.as_of || "not stated")}). Up to 1 year absolute, beyond 1 year CAGR. Not audited here; not investment advice.</p></div></td></tr>`;
  }

  function pmsTable() {
    const st = pmsState;
    let rows = pmsRows();
    const q = st.q.trim().toLowerCase();
    const groups = {};
    rows.forEach((s) => { if (s.category && pv(s, "1y") != null) (groups[s.category] = groups[s.category] || []).push(s); });
    Object.values(groups).forEach((g) => g.sort((a, b) => pv(b, "1y") - pv(a, "1y")));
    const catRank = (s) => { const g = groups[s.category]; if (!g || g.length < 5 || pv(s, "1y") == null) return ""; return `${g.indexOf(s) + 1} of ${g.length}`; };
    rows = rows.filter((s) => (st.cat === "All" || s.category === st.cat) &&
      (st.track === "any" || pv(s, st.track) != null) &&
      (!q || `${s.name} ${s.title} ${s.manager || ""} ${s.category || ""}`.toLowerCase().includes(q)));
    const key = st.sort;
    const val = (s) => (key === "name" ? (s.name || "").toLowerCase() : key === "corpus" ? s.corpus_cr : key === "ex1y" ? excess(s, "1y") : key === "inception" ? s.inception : pv(s, key));
    rows.sort((a, b) => { const x = val(a), y = val(b); if (x == null && y == null) return 0; if (x == null) return 1; if (y == null) return -1; return (x > y ? 1 : x < y ? -1 : 0) * st.dir; });
    const shown = rows.slice(0, st.limit);
    const th = (k, l) => `<th><button type="button" data-psort="${k}">${l}${st.sort === k ? (st.dir > 0 ? " ▲" : " ▼") : ""}</button></th>`;
    const cols = 12;
    const body = shown.map((s, i) => `<tr class="prow" data-slug="${esc(s.slug)}"><td class="n dim">${i + 1}</td><td><a class="sname" href="#" data-open="${esc(s.slug)}">${esc(s.name || s.title)}</a>${s.label_mismatch ? ' <span class="tagw">check source</span>' : ""}<br><small class="k">${esc(s.manager || "manager not stated")}</small></td>
      <td>${esc(s.category || "–")}</td><td class="n">${s.corpus_cr != null ? dp(s.corpus_cr, 0) : "–"}</td>
      ${["1m", "3m", "1y", "3y", "5y", "si"].map((k) => `<td class="n"${heat(pv(s, k), k === "1m" ? 6 : k === "3m" ? 12 : 30)}>${sgn(pv(s, k), 1, "%")}</td>`).join("")}
      <td class="n">${sgn(excess(s, "1y"), 1, "")}</td><td class="n dim">${catRank(s)}</td></tr>${st.open === s.slug ? detailRow(s, cols) : ""}`).join("");
    return `<div class="tablewrap"><table class="nt pms"><thead><tr><th>#</th>${th("name", "Strategy and manager")}<th>Category</th>${th("corpus", "Corpus Rs Cr")}${th("1m", "1M")}${th("3m", "3M")}${th("1y", "1Y")}${th("3y", "3Y")}${th("5y", "5Y")}${th("si", "Since start")}${th("ex1y", "1Y vs bench (pts)")}<th>Rank in category (1Y)</th></tr></thead><tbody>${body || `<tr><td colspan="${cols}" class="empty">Nothing matches.</td></tr>`}</tbody></table></div>
      ${rows.length > shown.length ? `<p class="morewrap"><button type="button" class="chip" data-pmore="1">Show ${Math.min(40, rows.length - shown.length)} more (${rows.length - shown.length} not shown)</button></p>` : ""}
      <p class="fine">${rows.length} strategies match. Click a strategy for benchmark returns, manager background and the source link.</p>`;
  }

  function bazaarBox() {
    const b = (advPms && advPms.bazaar_top) || [];
    if (!b.length) return "";
    const lists = ["1M", "1Y", "3Y", "5Y"].map((p) => {
      const rows = b.filter((x) => x.period === p);
      return rows.length ? `<div class="hc"><h4>Top performers, ${p}</h4><ol>${rows.map((x) => `<li>${link(x.url, esc(x.name))} <small class="k">${esc(x.category || "")}</small> ${sgn(x.ret, 2, "%")}</li>`).join("")}</ol></div>` : "";
    }).join("");
    return `<h3 class="nh">Second source: PMS Bazaar's own top performers</h3><div class="hotcold wide">${lists}</div>
      <p class="fine">Source: PMS Bazaar public leaderboard, fetched ${esc(advPms.bazaar_fetched || "")}. The leaderboard states no as-of date, so treat it as the latest month PMS Bazaar has published. Small and new strategies can top a one-month list; use the 3Y and 5Y lists and the track-record filter below for a fairer read.</p>`;
  }

  function aumBox() {
    const a = advAum;
    if (!a) return "";
    const q = aumState.q.trim().toLowerCase();
    const clean = a.firms.filter((f) => !f.flag), flagged = a.firms.filter((f) => f.flag);
    const rows = clean.filter((f) => !q || f.name.toLowerCase().includes(q));
    const shown = rows.slice(0, aumState.limit);
    const totalClean = clean.reduce((s, f) => s + f.aum_cr, 0), clients = clean.reduce((s, f) => s + f.clients, 0);
    return `<h3 class="nh">Official PMS AUM by portfolio manager (as on ${esc(a.as_on)})</h3>
      <div class="statrow"><div class="stat"><span>Portfolio managers listed</span><b>${a.count}</b></div><div class="stat"><span>AUM, rows not flagged</span><b>Rs ${dp(totalClean / 100000, 2)} lakh Cr</b></div><div class="stat"><span>Clients, rows not flagged</span><b>${dp(clients, 0)}</b></div></div>
      <input id="aumq" class="tsearch" type="search" placeholder="Find a portfolio manager" value="${esc(aumState.q)}">
      <div class="tablewrap" id="aumTable"><table class="nt"><thead><tr><th>#</th><th>Portfolio manager</th><th>Clients</th><th>AUM Rs Cr</th><th>Avg per client Rs Cr</th></tr></thead><tbody>
      ${shown.map((f, i) => `<tr><td class="n dim">${clean.indexOf(f) + 1}</td><td>${esc(f.name)}</td><td class="n">${dp(f.clients, 0)}</td><td class="n">${dp(f.aum_cr, 2)}</td><td class="n dim">${f.clients ? dp(f.aum_cr / f.clients, 2) : "–"}</td></tr>`).join("")}</tbody></table></div>
      ${rows.length > shown.length ? `<p class="morewrap"><button type="button" class="chip" data-amore="1">Show 25 more (${rows.length - shown.length} not shown)</button></p>` : ""}
      ${flagged.length ? `<details class="snap"><summary>${flagged.length} rows set aside because the figures look unreliable or unusual</summary>
        <div class="tablewrap"><table class="nt"><thead><tr><th>Portfolio manager</th><th>Clients</th><th>AUM Rs Cr</th><th>Why set aside</th></tr></thead><tbody>${flagged.map((f) => `<tr><td>${esc(f.name)}</td><td class="n">${dp(f.clients, 0)}</td><td class="n">${dp(f.aum_cr, 2)}</td><td>${esc(f.flag)}</td></tr>`).join("")}</tbody></table></div></details>` : ""}
      <p class="fine">Source: APMI, compiled from SEBI's monthly report (${link(a.source_url, "official PDF")}), fetched ${esc(a.fetched)}. Official and firm-level, published with a lag. Some large managers hold institutional (EPFO / provident fund) mandates, which is why a few AUMs dwarf the rest. The PDF is read by scripts/apmi_aum.py, run monthly by hand.</p>`;
  }

  function pmsBlock() {
    const st = pmsState, rows = pmsRows();
    const cats = [...new Set(rows.map((s) => s.category).filter(Boolean))].sort();
    const asof = advPms && advPms.returns_as_of;
    const withRet = rows.filter((s) => pv(s, "1y") != null).length;
    return `<p class="note">Strategy data is copied from PMS AIF World's public pages (link on every strategy). PMS returns are published monthly, so this table changes once a month, not daily; the latest month on file is <b>${esc(asof || "unknown")}</b>. Up to 1 year the return is absolute, beyond 1 year it is a yearly compound rate (CAGR). ${rows.length} PMS strategies on file, ${withRet} with a 1-year return.</p>
      <div class="pmsctl"><input id="pq" class="tsearch" type="search" placeholder="Search strategy, manager or category" value="${esc(st.q)}">
        <label>Category <select id="pcat"><option>All</option>${cats.map((c) => `<option ${c === st.cat ? "selected" : ""}>${esc(c)}</option>`).join("")}</select></label>
        <label>Track record <select id="ptrack">${[["any", "Any"], ["1y", "At least 1 year"], ["3y", "At least 3 years"], ["5y", "At least 5 years"]].map(([v, l]) => `<option value="${v}" ${v === st.track ? "selected" : ""}>${l}</option>`).join("")}</select></label>
        <button type="button" class="chip" id="pdir">${st.dir < 0 ? "Best first" : "Weakest first"} (tap to flip)</button></div>
      <div id="pmsTable">${pmsTable()}</div>${bazaarBox()}${aumBox()}`;
  }

  const AIF_COLS = [["1m", "1M"], ["3m", "3M"], ["6m", "6M"], ["1y", "1Y"], ["3y", "3Y"], ["5y", "5Y"], ["si", "Since start"]];
  const cat3Rows = () => (advCat3 && advCat3.funds) || [];
  function aifTable() {
    const st = aifState, q = st.q.trim().toLowerCase();
    let rows = cat3Rows().filter((f) => (st.section === "All" || f.section === st.section) && (st.basis === "All" || f.basis === st.basis) &&
      (st.track === "any" || f.ret[st.track] != null) && (!q || f.name.toLowerCase().includes(q)));
    const val = (f) => (st.sort === "name" ? f.name.toLowerCase() : st.sort === "aum" ? f.aum_cr : st.sort === "inception" ? new Date("1 " + f.inception).getTime() : f.ret[st.sort]);
    rows.sort((a, b) => { const x = val(a), y = val(b); if (x == null && y == null) return 0; if (x == null) return 1; if (y == null) return -1; return (x > y ? 1 : x < y ? -1 : 0) * st.dir; });
    const shown = rows.slice(0, st.limit);
    const th = (k, l) => `<th><button type="button" data-asort="${k}">${l}${st.sort === k ? (st.dir > 0 ? " ▲" : " ▼") : ""}</button></th>`;
    const body = shown.map((f, i) => `<tr><td class="n dim">${i + 1}</td><td>${esc(f.name)} <b class="bm" title="Return basis (see legend above)">${esc(f.basis || "")}</b><br><small class="k">${esc(f.section)}</small></td><td class="n">${esc(f.inception)}</td><td class="n">${f.aum_cr != null ? dp(f.aum_cr, 1) : "–"}</td>
      ${AIF_COLS.map(([k]) => `<td class="n"${heat(f.ret[k], k === "1m" ? 6 : k === "3m" ? 12 : 30)}>${sgn(f.ret[k], 1, "%")}</td>`).join("")}<td class="n"><b>${esc(f.basis || "")}</b></td></tr>`).join("");
    return `<div class="tablewrap"><table class="nt pms"><thead><tr><th>#</th>${th("name", "Fund (firm name first)")}${th("inception", "Started")}${th("aum", "AUM Rs Cr")}${AIF_COLS.map(([k, l]) => th(k, l)).join("")}<th>Basis</th></tr></thead><tbody>${body || '<tr><td colspan="12" class="empty">Nothing matches.</td></tr>'}</tbody></table></div>
      ${rows.length > shown.length ? `<p class="morewrap"><button type="button" class="chip" data-amoreaif="1">Show ${Math.min(40, rows.length - shown.length)} more (${rows.length - shown.length} not shown)</button></p>` : ""}
      <p class="fine">${rows.length} funds match.</p>`;
  }
  function aifDirRows() { return Object.values((advPms && advPms.strategies) || {}).filter((s) => s.title && /^AIF/.test(s.kind || "")); }
  function aifDirTable() {
    const q = aifState.dq.trim().toLowerCase();
    const rows = aifDirRows().filter((s) => !q || `${s.name} ${s.title} ${s.manager || ""} ${s.kind}`.toLowerCase().includes(q)).sort((a, b) => (a.name || "").localeCompare(b.name || ""));
    const shown = rows.slice(0, aifState.dlimit);
    return `<div class="tablewrap"><table class="nt"><thead><tr><th>Fund</th><th>Manager</th><th>Category</th><th>Structure and type</th><th>Min. ticket</th></tr></thead><tbody>
      ${shown.map((s) => `<tr><td>${stratLink(s)}${s.label_mismatch ? ' <span class="tagw">check source</span>' : ""}</td><td>${esc(s.manager || "not stated")}</td><td>${esc(s.kind)}</td><td>${esc([s.structure, s.fund_type].filter(Boolean).join(" · ") || "–")}</td><td>${esc(s.ticket || "–")}</td></tr>`).join("")}</tbody></table></div>
      ${rows.length > shown.length ? `<p class="morewrap"><button type="button" class="chip" data-adirmore="1">Show 25 more (${rows.length - shown.length} not shown)</button></p>` : ""}<p class="fine">${rows.length} funds listed.</p>`;
  }
  function aifBlock() {
    const st = aifState, c = advCat3;
    const dir = aifDirRows();
    const bases = [...new Set(cat3Rows().map((f) => f.basis).filter(Boolean))].sort();
    const board = c ? `<p class="note">Category III AIF performance is copied from PMS AIF World's monthly Cat III newsletter (${link(c.pdf_url, "PDF")}, ${link(c.page_url, "page")}), returns as of <b>${esc(c.as_of)}</b> (${esc(c.edition)} edition). ${cat3Rows().length} funds. <b>Read the Basis column:</b> each fund reports returns on a different basis, so the funds are not strictly comparable. Legend from the source: ${esc(c.legend)}. ${esc(c.basis_note)} Category III funds can use leverage and shorting; Long Only ones behave like a concentrated equity portfolio, Long Short ones aim at steadier returns.</p>
      <div class="pmsctl"><input id="aq" class="tsearch" type="search" placeholder="Search fund or firm" value="${esc(st.q)}">
        <label>Style <select id="asec">${["All", "Long Only", "Long Short"].map((x) => `<option ${x === st.section ? "selected" : ""}>${x}</option>`).join("")}</select></label>
        <label>Basis <select id="abasis"><option>All</option>${bases.map((x) => `<option ${x === st.basis ? "selected" : ""}>${esc(x)}</option>`).join("")}</select></label>
        <label>Track record <select id="atrack">${[["any", "Any"], ["1y", "At least 1 year"], ["3y", "At least 3 years"], ["5y", "At least 5 years"]].map(([v, l]) => `<option value="${v}" ${v === st.track ? "selected" : ""}>${l}</option>`).join("")}</select></label>
        <button type="button" class="chip" id="adir">${st.dir < 0 ? "Best first" : "Weakest first"} (tap to flip)</button></div>
      <div id="aifTable">${aifTable()}</div>` : `<p class="note">The Cat III AIF performance file could not be loaded.</p>`;
    return `<h3 class="nh">Category III AIF performance</h3>${board}
      <h3 class="nh">AIF directory: managers, categories and structures (${dir.length} funds)</h3>
      <p class="note">AIFs of Category I and II (private equity, venture, infrastructure, real estate, credit) are unlisted and disclose returns rarely; their pages carry the manager, structure and minimum ticket only. Category I invests in socially or economically useful areas (start-ups, infrastructure); Category II is mostly private equity and debt funds. Source: PMS AIF World public pages, each linked.</p>
      <input id="dq" class="tsearch" type="search" placeholder="Search the directory by fund, manager or category" value="${esc(st.dq)}">
      <div id="aifDir">${aifDirTable()}</div>`;
  }

  function bindAdvisory(id) {
    const nb = $("numbers");
    nb.onclick = (e) => {
      const sb = e.target.closest("[data-sec]");
      if (sb) { secKey = sb.dataset.sec; nb.innerHTML = cfg.numbers(id); return; }
      const ps = e.target.closest("[data-psort]");
      if (ps) { const k = ps.dataset.psort; if (pmsState.sort === k) pmsState.dir = -pmsState.dir; else { pmsState.sort = k; pmsState.dir = k === "name" ? 1 : -1; } $("pmsTable").innerHTML = pmsTable(); return; }
      const op = e.target.closest("[data-open]");
      if (op) { e.preventDefault(); pmsState.open = pmsState.open === op.dataset.open ? null : op.dataset.open; $("pmsTable").innerHTML = pmsTable(); return; }
      if (e.target.closest("[data-pmore]")) { pmsState.limit += 40; $("pmsTable").innerHTML = pmsTable(); return; }
      const as = e.target.closest("[data-asort]");
      if (as) { const k = as.dataset.asort; if (aifState.sort === k) aifState.dir = -aifState.dir; else { aifState.sort = k; aifState.dir = k === "name" ? 1 : -1; } $("aifTable").innerHTML = aifTable(); return; }
      if (e.target.closest("[data-amoreaif]")) { aifState.limit += 40; $("aifTable").innerHTML = aifTable(); return; }
      if (e.target.closest("[data-adirmore]")) { aifState.dlimit += 25; $("aifDir").innerHTML = aifDirTable(); return; }
      if (e.target.closest("[data-amore]")) { aumState.limit += 25; nb.innerHTML = cfg.numbers(id); return; }
      if (e.target.id === "pdir") { pmsState.dir = -pmsState.dir; e.target.textContent = `${pmsState.dir < 0 ? "Best first" : "Weakest first"} (tap to flip)`; $("pmsTable").innerHTML = pmsTable(); }
      if (e.target.id === "adir") { aifState.dir = -aifState.dir; e.target.textContent = `${aifState.dir < 0 ? "Best first" : "Weakest first"} (tap to flip)`; $("aifTable").innerHTML = aifTable(); }
    };
    nb.oninput = (e) => {
      if (e.target.id === "pq") { pmsState.q = e.target.value; pmsState.limit = 40; $("pmsTable").innerHTML = pmsTable(); }
      if (e.target.id === "aq") { aifState.q = e.target.value; aifState.limit = 40; $("aifTable").innerHTML = aifTable(); }
      if (e.target.id === "dq") { aifState.dq = e.target.value; aifState.dlimit = 25; $("aifDir").innerHTML = aifDirTable(); }
      if (e.target.id === "aumq") { aumState.q = e.target.value; const pos = e.target.selectionStart; nb.innerHTML = cfg.numbers(id); const el = $("aumq"); el.focus(); el.setSelectionRange(pos, pos); }
    };
    nb.onchange = (e) => {
      if (e.target.id === "pcat") { pmsState.cat = e.target.value; pmsState.limit = 40; $("pmsTable").innerHTML = pmsTable(); }
      if (e.target.id === "ptrack") { pmsState.track = e.target.value; pmsState.limit = 40; $("pmsTable").innerHTML = pmsTable(); }
      if (e.target.id === "asec") { aifState.section = e.target.value; aifState.limit = 40; $("aifTable").innerHTML = aifTable(); }
      if (e.target.id === "abasis") { aifState.basis = e.target.value; aifState.limit = 40; $("aifTable").innerHTML = aifTable(); }
      if (e.target.id === "atrack") { aifState.track = e.target.value; aifState.limit = 40; $("aifTable").innerHTML = aifTable(); }
    };
  }

  DESKS.advisory = {
    file: "data/advisory.json",
    title: "Investment Advisory Universe",
    sources: "Numbers: NSE (indices, sector indices, index P/E, breadth, FII/DII), Yahoo Finance (global markets, US yields, dollar, gold, silver, crude, USD/INR, REIT and InvIT prices), Reserve Bank of India (policy rates), TradingView (India 10-year yield, best effort). PMS and AIF strategy data: PMS AIF World public pages and PMS Bazaar's public leaderboard, each strategy linked to its source page. Official PMS AUM: APMI, compiled from SEBI's monthly report. News: Economic Times, Mint, Business Standard, BusinessLine, CNBC-TV18, CNBC, BBC, MarketWatch and Google News headlines, SEBI, RBI and finance-ministry releases. There is no commentary in this desk: figures, headlines and links only. Aggregator figures are as reported by the aggregator and not audited here. Not investment advice: open the source before acting.",
    subs: [
      { id: "pulse", label: "Market Pulse", nums: "pulse", test: (i) => i.category === "Equity Markets" },
      { id: "pms", label: "PMS", nums: "pms", test: (i) => i.category === "PMS" },
      { id: "aif", label: "AIF", nums: "aif", test: (i) => i.category === "AIF" },
      { id: "debt", label: "Debt & Bonds", nums: "debt", test: (i) => i.category === "Debt & Bonds" },
      { id: "real", label: "Gold, Silver & REITs", nums: "real", test: (i) => i.category === "Gold & Silver" || i.category === "REITs & InvITs" },
      { id: "mf", label: "Mutual Funds", test: (i) => i.category === "Mutual Funds" },
      { id: "reg", label: "Regulatory", nums: "reg", test: (i) => i.category === "Regulatory" },
      { id: "global", label: "Global", nums: "global", test: (i) => i.category === "Global" },
      { id: "news", label: "All News", test: () => true },
    ],
    f1: { key: "category" }, f2: { key: "sector" }, f3: { key: "kind", values: ["News", "Official"] },
    flag: { label: "Official notices only", test: (i) => i.kind === "Official" },
    search: (i) => `${i.title} ${i.summary} ${i.source} ${i.category} ${i.sector || ""}`,
    lead: () => null,
    numbers(id) {
      if (id === "pms") return pmsBlock();
      if (id === "aif") return aifBlock();
      return advMarket ? marketBlock(id) : `<p class="note">The numbers file could not be loaded.</p>`;
    },
    card(it) {
      const official = it.kind === "Official";
      const b = `<span class="badge ${official ? "major" : "src"}">${official ? esc(it.source) : "NEWS"}</span><span class="badge type">${esc(it.category)}</span>`;
      const meta = `${b}${official ? esc(it.ministry || "") : esc(it.source)}${it.sector ? " &middot; " + esc(it.sector) : ""}${it.time ? ` &middot; ${esc(it.time)} IST` : ""}`;
      const also = (it.also || []).length ? `<div class="more">Also covered by: ${it.also.map((a) => link(a.url, esc(a.source))).join("")}</div>` : "";
      return shell(false, meta, it, `${bodyOf(it, it.summary, "compact")}${also}`, "Open the original");
    },
  };

  // ---------------------------------------------------------------- Front Page (top stories across all desks)
  DESKS.top = {
    file: "data/front.json",
    title: "Front Page",
    front: true,
    sources: "Front Page ranks stories from the Policy, Startup, Migration and Investment Advisory desks with a transparent point system (see scripts/build_front_page.py): Cabinet and regulator decisions, deal size, official immigration notices, coverage by many outlets, plus recency. The line under each headline lists the rules that put it here. Rebuilt every morning.",
    flag: { label: "", test: () => true },
  };

  const deskName = (d) => (d === "Immigration" ? "Migration" : d);
  const DESK_LINK = { Policy: "#policy", Startups: "#startups", Immigration: "#immigration", Advisory: "#advisory" };
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
    const big = it.desk === "Immigration" || it.desk === "Advisory" ? it.label : it.source;
    const small = it.desk === "Policy" ? it.label : it.desk === "Startups" ? it.label.split("·").pop().trim() : it.source;
    return `<a class="ph ${esc(it.desk)} ${cls || ""}" href="${esc(it.url)}" target="_blank" rel="noopener" tabindex="-1" aria-hidden="true">
      <span class="tile"><b>${esc(big)}</b><i>${esc(small)}</i></span>${it.image ? `<img src="${esc(it.image)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">` : ""}</a>`;
  };
  const deskBadge = (it) => `<span class="badge desk ${esc(it.desk)}">${esc(deskName(it.desk))}</span>${it.must_read ? '<span class="badge major">MUST READ</span>' : ""}`;
  const metaLine = (it) => `${deskBadge(it)}${esc(it.label)} &middot; ${esc(it.source)} &middot; ${esc(it.date)}`;
  const whyLine = (it) => `<div class="why">Why it is here: ${it.why.map(esc).join(" &middot; ")}</div>`;

  function heroCard(it) {
    return `<section class="hero">${pic(it, "big")}<div class="htext">
      <div class="meta">${metaLine(it)}</div>
      <h2>${link(it.url, esc(it.title))}</h2>
      ${briefHtml(it, "full") || `<p class="snip">${esc(best(it, 520, true))}</p>`}${whyLine(it)}
      ${link(it.url, "Read the full story &rarr;", "read")} <a class="more" href="${DESK_LINK[it.desk]}">More from the ${esc(deskName(it.desk))} Desk</a></div></section>`;
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
    return `<section class="dcol"><h3><a href="${DESK_LINK[desk]}">${esc(deskName(desk))} Desk</a></h3>
      <div class="dstat">${d.total} on file &middot; ${d.new_today} new today</div>${d.items.map(miniCard).join("")}
      <a class="read" href="${DESK_LINK[desk]}">Open the ${esc(deskName(desk))} Desk &rarr;</a></section>`;
  }

  let frontData = null, interest = "All";
  function frontView(data) {
    frontData = data;
    const built = new Date(data.built.replace(" IST", "").replace(" ", "T") + ":00+05:30");
    const hours = (Date.now() - built.getTime()) / 36e5;
    const stale = hours > 30
      ? `<p class="stale">The last refresh was ${Math.round(hours)} hours ago (${esc(data.built)}). The scheduled run may have been missed; the stories below may be out of date.</p>` : "";
    const counts = Object.entries(data.by_desk).map(([d, n]) => `${n} ${deskName(d)}`).join(" &middot; ");
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
    const opts = ["All", "Policy", "Startups", "Immigration", "Advisory", ...tags];
    $("interest").innerHTML = opts.map((o) => `<button class="chip" type="button" aria-pressed="${interest === o}" data-v="${esc(o)}">${esc(deskName(o))}</button>`).join("");
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
        `<h2 class="sect">Snapshots from the desks</h2><div class="dcols">${["Policy", "Startups", "Immigration", "Advisory"].map((k) => deskColumn(k, d.desks[k])).join("")}</div>`;
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
      state.limit = 150;
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
    const shown = rows.slice(0, state.limit);      // long desks (Listed Universe) draw in pages of 150
    for (const it of shown) {
      if (plain && it === leadItem) continue; // already shown as the lead story
      if (it.date !== d) { d = it.date; html += `<h2 class="day">${day(d)}</h2>`; }
      html += cfg.card(it, false);
    }
    if (rows.length > shown.length) html += `<p class="morewrap"><button type="button" id="showmore" class="chip">Show ${Math.min(150, rows.length - shown.length)} more (${rows.length - shown.length} not shown)</button></p>`;
    $("feed").innerHTML = html;
    const more = $("showmore");
    if (more) more.onclick = () => { state.limit += 150; render(); };
  }

  async function load(hash) {
    const [name, subId] = hash.split("/");
    desk = DESKS[name] ? name : "top";
    cfg = DESKS[desk];
    sub = cfg.subs ? (cfg.subs.find((s) => s.id === subId) || cfg.subs[0]) : null;
    document.querySelectorAll(".desk").forEach((a) => a.classList.toggle("active", a.dataset.desk === desk));
    $("feed").innerHTML = '<p class="empty">Loading...</p>';
    $("lead").hidden = true;
    $("numbers").hidden = true;
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
        state = { q: "", f1: "All", f2: "All", f3: "All", flag: false, limit: 150 };
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
      if (desk === "listed") {
        const [cj, nj] = await Promise.all([
          fetch("data/companies.json", { cache: "no-cache" }).then((r) => r.json()).catch(() => ({ companies: {} })),
          fetch("data/company_notes.json", { cache: "no-cache" }).then((r) => r.json()).catch(() => ({})),
        ]);
        companies = cj.companies || {}; notes = nj || {};
      }
      if (desk === "advisory") await advisoryPrep();
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
      state = { q: "", f1: "All", f2: "All", f3: "All", flag: false, limit: 150 };
      const nb = $("numbers");
      if (desk === "advisory" && sub && sub.nums) { nb.innerHTML = cfg.numbers(sub.nums); nb.hidden = false; bindAdvisory(sub.nums); } else { nb.hidden = true; nb.innerHTML = ""; }
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
  $("q").oninput = (e) => { state.q = e.target.value; state.limit = 150; if (sub && sub.view) { window.__paint(); } else { render(); } };
  $("flag").onchange = (e) => { state.flag = e.target.checked; state.limit = 150; render(); };
  window.addEventListener("hashchange", () => load(location.hash.slice(1)));
  load(location.hash.slice(1));
})();
