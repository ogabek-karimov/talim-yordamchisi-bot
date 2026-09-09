/* Ta'lim yordamchisi — Telegram Mini App */
(() => {
  "use strict";

  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  const qs = new URLSearchParams(location.search);
  const API = "";

  const state = {
    token: null,
    me: null,
    i18n: {},
    languages: [],
    tab: qs.get("view") === "admin" ? "admin" : "test",
    // test flow
    subjects: [], sets: [], set: null, answers: {}, qIndex: 0, timer: null, deadline: 0,
    // homework
    chat: [], pendingImage: null,
    // admin
    adminTab: "apps",
  };

  // ---- helpers -----------------------------------------------------
  const $ = (sel, root = document) => root.querySelector(sel);
  const el = (tag, props = {}, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (k === "class") n.className = v;
      else if (k === "html") n.innerHTML = v;
      else if (k === "text") n.textContent = v;
      else if (k.startsWith("on") && typeof v === "function") n.addEventListener(k.slice(2), v);
      else if (v !== null && v !== undefined) n.setAttribute(k, v);
    }
    for (const kid of kids) if (kid != null) n.append(kid.nodeType ? kid : document.createTextNode(kid));
    return n;
  };
  const T = (key, params) => {
    let s = state.i18n[key] || key;
    if (params) for (const [k, v] of Object.entries(params)) s = s.replaceAll("{" + k + "}", v);
    return s;
  };
  const screen = () => $("#screen");
  const clear = (node) => { while (node.firstChild) node.removeChild(node.firstChild); };

  // AI replies sometimes arrive with LaTeX / Markdown; the chat shows plain text,
  // so convert to readable Unicode + minimal safe HTML.
  const SUP = { "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹", "+": "⁺", "-": "⁻", "n": "ⁿ", "i": "ⁱ" };
  const SUB = { "0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄", "5": "₅", "6": "₆", "7": "₇", "8": "₈", "9": "₉" };
  function formatAi(raw) {
    let s = String(raw == null ? "" : raw);
    s = s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    s = s.replace(/\$\$?/g, "").replace(/\\\[|\\\]|\\\(|\\\)/g, "");
    const rep = [
      [/\\cdot/g, "·"], [/\\times/g, "×"], [/\\div/g, "÷"], [/\\approx/g, "≈"],
      [/\\neq?/g, "≠"], [/\\leq?/g, "≤"], [/\\geq?/g, "≥"], [/\\pm/g, "±"],
      [/\\infty/g, "∞"], [/\\pi/g, "π"], [/\\degree|\\deg/g, "°"],
      [/\\left|\\right/g, ""], [/\\,|\\;|\\!|\\:|\\quad|\\qquad/g, " "],
    ];
    for (const [re, v] of rep) s = s.replace(re, v);
    s = s.replace(/\\sqrt\s*\{([^{}]*)\}/g, "√($1)");
    s = s.replace(/\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}/g, "($1)/($2)");
    s = s.replace(/\\(?:text|mathrm|mathbf|mathit|mathsf|boxed|operatorname)\s*\{([^{}]*)\}/g, "$1");
    s = s.replace(/\\[a-zA-Z]+\s?/g, "");
    s = s.replace(/\^\{([^{}]+)\}/g, (_, g) => [...g].map((c) => SUP[c] || c).join(""));
    s = s.replace(/\^([0-9niN+\-])/g, (_, g) => SUP[g] || "^" + g);
    s = s.replace(/_\{([0-9]+)\}/g, (_, g) => [...g].map((c) => SUB[c] || c).join(""));
    s = s.replace(/([A-Za-z])_([0-9])\b/g, (_, a, d) => a + (SUB[d] || "_" + d));
    s = s.replace(/_\{([^{}]+)\}/g, "_$1");
    s = s.replace(/[{}]/g, "");
    s = s.replace(/^\s{0,3}#{1,6}\s*(.+?)\s*#*\s*$/gm, (_, t) => "<b>" + t.replace(/\*\*|__/g, "") + "</b>");
    s = s.replace(/\*\*([^*\n]+)\*\*/g, "<b>$1</b>").replace(/__([^_\n]+)__/g, "<b>$1</b>");
    s = s.replace(/(^|[\s(])\*([^*\n]+)\*(?=$|[\s).,:;])/g, "$1$2");
    s = s.replace(/^\s*[*\-]\s+/gm, "• ");
    s = s.replace(/^\s*([-*_]\s?){3,}\s*$/gm, "");
    return s.replace(/\n{3,}/g, "\n\n").trim();
  }
  const haptic = (type = "light") => { try { tg && tg.HapticFeedback.impactOccurred(type); } catch {} };

  let toastTimer = null;
  function toast(msg) {
    const old = $(".toast"); if (old) old.remove();
    const t = el("div", { class: "toast", text: msg });
    document.body.append(t);
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.remove(), 2600);
  }

  async function api(path, { method = "GET", body, form, auth = true } = {}) {
    const headers = {};
    if (auth && state.token) headers["Authorization"] = "Bearer " + state.token;
    let payload;
    if (form) { payload = form; }
    else if (body !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
    const resp = await fetch(API + path, { method, headers, body: payload });
    let data = null;
    const ct = resp.headers.get("content-type") || "";
    if (ct.includes("application/json")) { try { data = await resp.json(); } catch {} }
    if (!resp.ok) {
      const errText = (data && (data.detail || data.message)) || ("HTTP " + resp.status);
      const e = new Error(typeof errText === "string" ? errText : JSON.stringify(errText));
      e.status = resp.status; e.data = data;
      throw e;
    }
    return data;
  }

  // ---- boot ------------------------------------------------------
  async function boot() {
    if (tg) { try { tg.ready(); tg.expand(); } catch {} }
    const initData = (tg && tg.initData) || qs.get("dev_init") || "";
    setLoading(T("app.loading") || "Loading…");
    try {
      const res = await api("/api/auth", { method: "POST", auth: false, body: { init_data: initData } });
      state.token = res.token;
      state.me = res.me;
      state.i18n = res.i18n || {};
      state.languages = res.languages || [];
      renderShell();
      if (!state.me.is_staff && state.tab === "admin") state.tab = "test";
      renderTab();
    } catch (e) {
      renderFatal(e.status === 401 ? T("app.auth_failed") : (e.message || "Error"));
    }
  }

  function setLoading(text) {
    clear(screen());
    screen().append(el("div", { class: "center" },
      el("div", { class: "spinner" }),
      el("p", { text: text })));
  }

  function renderFatal(msg) {
    clear(screen());
    screen().append(el("div", { class: "center pad" },
      el("p", { class: "err-msg", text: msg }),
      el("button", { class: "btn primary", text: T("app.retry"), onclick: boot })));
  }

  // ---- shell (topbar, language, tabs, sub banner) --------------
  function renderShell() {
    const bar = $("#topbar");
    bar.hidden = false;
    $("#brandTitle").textContent = T("app.title");

    const sel = $("#langSelect");
    clear(sel);
    for (const l of state.languages) {
      sel.append(el("option", { value: l.code, text: l.name, ...(l.code === state.me.language ? { selected: "selected" } : {}) }));
    }
    sel.onchange = async () => {
      try {
        await api("/api/student/language", { method: "POST", body: { language: sel.value } });
        const cat = await api("/api/i18n/" + sel.value, { auth: false });
        state.i18n = cat; state.me.language = sel.value;
        renderShell(); renderTab();
        toast(T("lang.updated"));
      } catch (e) { toast(e.message); }
    };

    renderSubBanner();
    renderTabbar();
  }

  function renderSubBanner() {
    const b = $("#subBanner");
    const s = state.me.subscription;
    if (!s.feature_enabled) { b.hidden = true; return; }
    b.hidden = false;
    b.className = "sub-banner" + (s.active ? " ok" : "");
    clear(b);
    if (s.active) {
      b.append(document.createTextNode(T("app.sub.banner_active", { until: fmtDate(s.until) })));
    } else {
      b.append(document.createTextNode(T("app.sub.banner_inactive")));
      b.append(el("button", { text: T("app.sub.extend"), onclick: openPlans }));
    }
  }

  function renderTabbar() {
    const nav = $("#tabbar");
    nav.hidden = false;
    clear(nav);
    const tabs = [
      { key: "test", ico: "📚", label: T("app.tab_test") },
      { key: "homework", ico: "✍️", label: T("app.tab_homework") },
    ];
    if (state.me.is_staff) tabs.push({ key: "admin", ico: "🛠", label: T("app.tab_admin") });
    for (const tb of tabs) {
      nav.append(el("button", {
        class: state.tab === tb.key ? "active" : "",
        onclick: () => { state.tab = tb.key; renderTabbar(); renderTab(); haptic(); },
      }, el("span", { class: "tab-ico", text: tb.ico }), el("span", { text: tb.label })));
    }
  }

  function renderTab() {
    removeComposer();
    if (state.tab === "test") return renderTestHome();
    if (state.tab === "homework") return renderHomework();
    if (state.tab === "admin") return renderAdmin();
  }

  const fmtDate = (iso) => {
    if (!iso) return "—";
    const d = new Date(iso);
    return isNaN(d) ? iso : d.toISOString().slice(0, 16).replace("T", " ") + " UTC";
  };

  // ================= TEST MODE ==================================
  async function renderTestHome() {
    setLoading(T("app.loading"));
    try {
      state.subjects = await api("/api/student/subjects");
    } catch (e) { return renderFatal(e.message); }
    clear(screen());
    const wrap = screen();
    wrap.append(el("div", { class: "section-title", text: T("app.test.pick_subject") }));
    if (!state.subjects.length) {
      wrap.append(el("div", { class: "empty", text: T("app.test.no_subjects") }));
      return;
    }
    for (const s of state.subjects) {
      wrap.append(el("div", { class: "card tap", onclick: () => renderSets(s) },
        el("div", {}, el("h3", { text: s.name || s.slug })),
        el("span", { text: "›" })));
    }
  }

  async function renderSets(subject) {
    setLoading(T("app.loading"));
    let sets;
    try { sets = await api(`/api/student/subjects/${subject.id}/sets`); }
    catch (e) { return renderFatal(e.message); }
    state.sets = sets;
    clear(screen());
    const wrap = screen();
    wrap.append(el("button", { class: "btn ghost sm", text: T("common.back"), onclick: renderTestHome }));
    wrap.append(el("div", { class: "section-title", text: subject.name || subject.slug }));
    if (!sets.length) { wrap.append(el("div", { class: "empty", text: T("app.test.no_sets") })); return; }
    for (const st of sets) {
      wrap.append(el("div", { class: "card tap", onclick: () => startTest(st.id) },
        el("div", { class: "grow" },
          el("h3", { text: st.title || ("#" + st.id) }),
          el("div", { class: "muted", text: `${st.question_count} • ${st.time_limit_sec ? Math.round(st.time_limit_sec / 60) + " min" : "∞"}` }),
          st.description ? el("div", { class: "muted", text: st.description }) : null),
        el("span", { text: "›" })));
    }
  }

  async function startTest(setId) {
    setLoading(T("app.loading"));
    let set;
    try { set = await api(`/api/student/sets/${setId}`); }
    catch (e) { return renderFatal(e.message); }
    state.set = set; state.answers = {}; state.qIndex = 0;
    if (state.timer) { clearInterval(state.timer); state.timer = null; }
    if (set.time_limit_sec > 0) {
      state.deadline = Date.now() + set.time_limit_sec * 1000;
      state.timer = setInterval(tickTimer, 1000);
    } else {
      state.deadline = 0;
    }
    renderQuestion();
  }

  function tickTimer() {
    const left = Math.max(0, Math.round((state.deadline - Date.now()) / 1000));
    const t = $("#timer");
    if (t) {
      const m = String(Math.floor(left / 60)).padStart(2, "0");
      const s = String(left % 60).padStart(2, "0");
      t.textContent = `${m}:${s}`;
      t.classList.toggle("low", left <= 30);
    }
    if (left <= 0) {
      clearInterval(state.timer); state.timer = null;
      toast(T("app.test.time_up"));
      submitTest();
    }
  }

  function renderQuestion() {
    const set = state.set;
    const q = set.questions[state.qIndex];
    clear(screen());
    const wrap = screen();

    const head = el("div", { class: "row" },
      el("div", { class: "grow muted", text: T("app.test.question_of", { n: state.qIndex + 1, total: set.questions.length }) }));
    if (state.deadline) head.append(el("span", { class: "timer", id: "timer", text: "--:--" }));
    wrap.append(head);
    wrap.append(el("div", { class: "progress" }, el("i", { style: `width:${((state.qIndex + 1) / set.questions.length) * 100}%` })));

    wrap.append(el("div", { class: "card" },
      el("div", { class: "q-body", text: q.body }),
      q.image_url ? el("img", { src: q.image_url, alt: "" }) : null,
      ...q.options.map((opt, i) => {
        const chosen = state.answers[q.id] === i;
        return el("div", {
          class: "opt" + (chosen ? " selected" : ""),
          onclick: () => { state.answers[q.id] = i; haptic(); renderQuestion(); },
        }, el("span", { class: "mark", text: String.fromCharCode(65 + i) }), el("span", { class: "grow", text: opt }));
      })));

    const foot = el("div", { class: "runner-foot" });
    if (state.qIndex > 0)
      foot.append(el("button", { class: "btn", text: T("app.test.prev"), onclick: () => { state.qIndex--; renderQuestion(); } }));
    if (state.qIndex < set.questions.length - 1)
      foot.append(el("button", { class: "btn primary grow", text: T("app.test.next"), onclick: () => { state.qIndex++; renderQuestion(); } }));
    else
      foot.append(el("button", { class: "btn primary grow", text: T("app.test.finish"), onclick: confirmFinish }));
    wrap.append(foot);
    if (state.deadline) tickTimer();
  }

  function confirmFinish() {
    if (tg && tg.showConfirm) tg.showConfirm(T("app.test.finish_confirm"), (ok) => ok && submitTest());
    else if (confirm(T("app.test.finish_confirm"))) submitTest();
  }

  async function submitTest() {
    if (state.timer) { clearInterval(state.timer); state.timer = null; }
    setLoading(T("app.loading"));
    let res;
    try {
      res = await api(`/api/student/sets/${state.set.id}/submit`, { method: "POST", body: { answers: state.answers } });
    } catch (e) {
      if (e.status === 402) return renderPaywall(() => renderQuestion());
      return renderFatal(e.message);
    }
    renderResult(res);
  }

  function renderResult(res) {
    clear(screen());
    const wrap = screen();
    wrap.append(el("div", { class: "card" },
      el("h3", { text: T("app.test.result_title") }),
      el("div", { style: "font-size:28px;font-weight:700;margin:6px 0", text: T("app.test.score", { score: res.score, total: res.total }) })));

    wrap.append(el("div", { class: "section-title", text: T("app.test.review") }));
    res.review.forEach((r, idx) => {
      const card = el("div", { class: "card" }, el("div", { class: "q-body", text: r.body }));
      r.options.forEach((opt, i) => {
        let cls = "opt";
        if (i === r.correct_index) cls += " correct";
        else if (i === r.chosen_index) cls += " wrong";
        card.append(el("div", { class: cls },
          el("span", { class: "mark", text: String.fromCharCode(65 + i) }),
          el("span", { class: "grow", text: opt }),
          i === r.correct_index ? el("span", { text: "✓" }) : (i === r.chosen_index ? el("span", { text: "✗" }) : null)));
      });
      if (r.explanation) card.append(el("div", { class: "muted", style: "margin-top:8px;white-space:pre-wrap", text: r.explanation }));
      const explainBtn = el("button", { class: "btn ghost sm", text: T("app.test.explain"),
        onclick: () => explainQuestion(r, explainBtn, card) });
      card.append(explainBtn);
      wrap.append(card);
    });

    const foot = el("div", { class: "runner-foot" });
    foot.append(el("button", { class: "btn grow", text: T("app.test.back_to_sets"), onclick: renderTestHome }));
    foot.append(el("button", { class: "btn primary grow", text: T("app.test.retry"), onclick: () => startTest(state.set.id) }));
    wrap.append(foot);
  }

  async function explainQuestion(r, btn, card) {
    btn.disabled = true; btn.textContent = T("app.test.explaining");
    try {
      const res = await api("/api/ai/explain", { method: "POST", body: {
        body: r.body, options: r.options, correct_index: r.correct_index, chosen_index: r.chosen_index,
      }});
      card.append(el("div", { class: "msg bot", style: "max-width:100%;margin-top:8px", html: formatAi(res.reply) }));
      btn.remove();
    } catch (e) {
      btn.disabled = false; btn.textContent = T("app.test.explain");
      toast(e.status === 402 ? T("app.sub.locked") : (e.status === 429 ? T("app.hw.rate_limited") : (e.status === 503 ? T("app.hw.disabled") : e.message)));
    }
  }

  // ================= HOMEWORK MODE =============================
  function renderHomework() {
    clear(screen());
    const wrap = screen();
    if (!state.chat.length) {
      wrap.append(el("div", { class: "empty", text: T("app.hw.intro") }));
    }
    const chat = el("div", { class: "chat", id: "chat" });
    for (const m of state.chat) chat.append(renderMsg(m));
    wrap.append(chat);
    wrap.append(el("button", { class: "btn ghost sm", text: T("app.hw.clear"),
      onclick: () => { state.chat = []; renderHomework(); } }));
    mountComposer();
    scrollChat();
  }

  function renderMsg(m) {
    const isUser = m.role === "user";
    const node = isUser
      ? el("div", { class: "msg user", text: m.content || "" })
      : el("div", { class: "msg bot", html: formatAi(m.content || "") });
    if (m.image) node.append(el("img", { src: m.image, alt: "", style: "max-width:200px" }));
    return node;
  }

  function scrollChat() {
    const c = $("#chat");
    if (c) window.scrollTo(0, document.body.scrollHeight);
  }

  function removeComposer() { const c = $("#composer"); if (c) c.remove(); }

  function mountComposer() {
    removeComposer();
    const box = el("div", { class: "composer", id: "composer" });
    const file = el("input", { type: "file", accept: "image/*", style: "display:none" });
    file.addEventListener("change", () => {
      const f = file.files[0];
      if (!f) return;
      const rd = new FileReader();
      rd.onload = () => { state.pendingImage = { dataUrl: rd.result, file: f }; toast("📎 1"); };
      rd.readAsDataURL(f);
    });
    const ta = el("textarea", { placeholder: T("app.hw.placeholder"), rows: "1", id: "hwInput" });
    ta.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
    });
    const attachBtn = el("button", { class: "btn sm", text: "📎", onclick: () => file.click() });
    const sendBtn = el("button", { class: "btn primary sm", text: "➤", id: "hwSend", onclick: send });
    box.append(file, attachBtn, ta, sendBtn);
    document.body.append(box);
  }

  async function send() {
    const ta = $("#hwInput");
    const text = (ta.value || "").trim();
    if (!text && !state.pendingImage) return;
    const img = state.pendingImage;
    state.pendingImage = null;
    ta.value = "";

    state.chat.push({ role: "user", content: text, image: img ? img.dataUrl : null });
    const historyForApi = state.chat.filter(m => m.content).slice(-8).map(m => ({ role: m.role, content: m.content }));
    renderHomework();

    const thinking = { role: "assistant", content: T("app.hw.thinking") };
    state.chat.push(thinking); renderHomework();

    try {
      const form = new FormData();
      form.append("message", text);
      form.append("history", JSON.stringify(historyForApi.slice(0, -1)));
      if (img) form.append("image", img.file, img.file.name || "photo.jpg");
      const res = await api("/api/ai/homework", { method: "POST", form });
      thinking.content = res.reply;
    } catch (e) {
      thinking.content = e.status === 402 ? T("app.sub.locked")
        : e.status === 429 ? T("app.hw.rate_limited")
        : e.status === 503 ? T("app.hw.disabled")
        : e.status === 413 ? T("app.hw.image_too_big")
        : T("app.hw.error");
    }
    renderHomework();
  }

  // ================= PAYWALL / PLANS ==========================
  function renderPaywall(back) {
    clear(screen());
    screen().append(el("div", { class: "center pad" },
      el("p", { text: T("app.sub.locked") }),
      el("button", { class: "btn primary", text: T("app.sub.extend"), onclick: openPlans }),
      back ? el("button", { class: "btn ghost", text: T("common.back"), onclick: back }) : null));
  }

  async function openPlans() {
    let info;
    try { info = await api("/api/pay/plans"); } catch (e) { return toast(e.message); }
    if (!info.enabled) { toast(T("app.sub.banner_disabled")); return; }
    clear(screen());
    const wrap = screen();
    wrap.append(el("div", { class: "section-title", text: T("app.sub.choose_plan") }));
    for (const p of info.plans) {
      wrap.append(el("div", { class: "card tap", onclick: () => buy(p) },
        el("div", { class: "grow" }, el("h3", { text: p.title }),
          el("div", { class: "muted", text: T("sub.plan_line", { title: p.title, days: p.days, stars: p.stars }) })),
        el("span", { class: "btn primary sm", text: "⭐ " + p.stars })));
    }
    wrap.append(el("button", { class: "btn ghost", text: T("common.back"), onclick: () => renderTab() }));
  }

  async function buy(plan) {
    let link;
    try {
      const res = await api("/api/pay/invoice", { method: "POST", body: { plan_key: plan.key } });
      link = res.link;
    } catch (e) { return toast(e.message); }
    if (tg && tg.openInvoice) {
      tg.openInvoice(link, async (status) => {
        if (status === "paid") {
          toast(T("app.sub.pay_success"));
          try { state.me = await api("/api/me"); } catch {}
          renderShell(); renderTab();
        } else if (status === "cancelled") {
          toast(T("app.sub.pay_cancelled"));
        }
      });
    } else {
      window.open(link, "_blank");
    }
  }

  // ================= ADMIN ====================================
  function renderAdmin() {
    if (!state.me.is_staff) { state.tab = "test"; return renderTab(); }
    clear(screen());
    const wrap = screen();
    const tabs = [
      ["apps", T("app.admin.tab_apps")],
      ["users", T("app.admin.tab_users")],
      ["admins", T("app.admin.tab_admins")],
      ["sub", T("app.admin.tab_sub")],
      ["content", T("app.admin.tab_content")],
      ["broadcast", T("app.admin.tab_broadcast")],
      ["stats", T("app.admin.tab_stats")],
    ];
    const bar = el("div", { class: "subtabs" });
    for (const [k, label] of tabs) {
      bar.append(el("button", { class: state.adminTab === k ? "active" : "",
        onclick: () => { state.adminTab = k; renderAdmin(); } }, label));
    }
    wrap.append(bar);
    const body = el("div", { id: "adminBody" });
    wrap.append(body);
    const fn = {
      apps: adminApps, users: adminUsers, admins: adminAdmins, sub: adminSub,
      content: adminContent, broadcast: adminBroadcast, stats: adminStats,
    }[state.adminTab];
    fn(body);
  }

  async function adminApps(root) {
    root.append(el("p", { class: "muted", text: "…" }));
    let apps;
    try { apps = await api("/api/admin/applications"); } catch (e) { clear(root); return root.append(errBox(e)); }
    clear(root);
    if (!apps.length) return root.append(el("div", { class: "empty", text: T("app.admin.apps_empty") }));
    for (const a of apps) {
      const card = el("div", { class: "card" },
        el("h3", { text: a.full_name }),
        el("div", { class: "muted", text: `📞 ${a.phone}` }),
        el("div", { class: "muted", text: `🆔 ${a.tg_id}  ${a.username ? "@" + a.username : ""}  🌐 ${a.language}` }));
      const rowBtns = el("div", { class: "row", style: "margin-top:8px" });
      rowBtns.append(el("button", { class: "btn primary sm grow", text: T("app.admin.approve"),
        onclick: async () => { await guard(() => api(`/api/admin/applications/${a.id}/approve`, { method: "POST" })); renderAdmin(); } }));
      rowBtns.append(el("button", { class: "btn danger sm grow", text: T("app.admin.reject"),
        onclick: async () => {
          const reason = prompt(T("app.admin.reject_reason")) || null;
          await guard(() => api(`/api/admin/applications/${a.id}/reject`, { method: "POST", body: { reason } }));
          renderAdmin();
        } }));
      card.append(rowBtns);
      root.append(card);
    }
  }

  async function adminUsers(root) {
    const search = el("input", { type: "text", placeholder: "🔍 " + T("app.admin.add_user_ph") + " / @username" });
    const addWrap = el("div", { class: "card" },
      el("div", { class: "section-title", text: T("app.admin.add_user") }));
    const idIn = el("input", { type: "text", placeholder: T("app.admin.add_user_ph") });
    const nameIn = el("input", { type: "text", placeholder: T("app.admin.add_user_name_ph") });
    addWrap.append(el("label", { class: "field" }, idIn), el("label", { class: "field" }, nameIn),
      el("button", { class: "btn primary block", text: T("app.common.add"), onclick: async () => {
        const tg_id = parseInt(idIn.value, 10);
        if (!tg_id) return toast("ID");
        await guard(() => api("/api/admin/users", { method: "POST", body: { tg_id, name: nameIn.value || null } }));
        idIn.value = nameIn.value = ""; load();
      } }));
    root.append(el("label", { class: "field" }, search), addWrap);
    const list = el("div", { id: "userList" });
    root.append(list);

    async function load() {
      clear(list); list.append(el("p", { class: "muted", text: "…" }));
      let users;
      try { users = await api("/api/admin/users?q=" + encodeURIComponent(search.value || "")); }
      catch (e) { clear(list); return list.append(errBox(e)); }
      clear(list);
      if (!users.length) return list.append(el("div", { class: "empty", text: T("app.admin.users_empty") }));
      for (const u of users) list.append(userCard(u, load));
    }
    let deb;
    search.addEventListener("input", () => { clearTimeout(deb); deb = setTimeout(load, 300); });
    load();
  }

  function userCard(u, reload) {
    const card = el("div", { class: "card" },
      el("div", { class: "row" },
        el("h3", { class: "grow", text: u.name || String(u.tg_id) }),
        rolePill(u)));
    card.append(el("div", { class: "muted", text: `🆔 ${u.tg_id}  ${u.username ? "@" + u.username : ""}` }));
    if (u.phone) card.append(el("div", { class: "muted", text: "📞 " + u.phone }));
    if (u.subscription_until) card.append(el("div", { class: "muted", text: "⭐ " + fmtDate(u.subscription_until) }));
    if (u.role !== "owner") {
      const row = el("div", { class: "row wrap", style: "margin-top:8px" });
      if (u.status === "blocked")
        row.append(el("button", { class: "btn sm", text: T("app.admin.unblock"), onclick: () => act(`/api/admin/users/${u.tg_id}/unblock`) }));
      else
        row.append(el("button", { class: "btn sm", text: T("app.admin.block"), onclick: () => act(`/api/admin/users/${u.tg_id}/block`) }));
      row.append(el("button", { class: "btn danger sm", text: T("app.admin.remove"), onclick: () => act(`/api/admin/users/${u.tg_id}/remove`) }));
      if (state.me.is_owner && u.role === "user")
        row.append(el("button", { class: "btn sm", text: T("app.admin.make_admin"), onclick: () => act("/api/admin/admins", "POST", { tg_id: u.tg_id }) }));
      card.append(row);
    }
    async function act(path, method = "POST", body) {
      await guard(() => api(path, { method, body }));
      reload();
    }
    return card;
  }

  function rolePill(u) {
    if (u.role === "owner") return el("span", { class: "pill owner", text: "OWNER" });
    if (u.role === "admin") return el("span", { class: "pill admin", text: "ADMIN" });
    if (u.status === "blocked") return el("span", { class: "pill blocked", text: "BLOCKED" });
    return el("span", { class: "pill", text: u.status });
  }

  async function adminAdmins(root) {
    let admins;
    try { admins = await api("/api/admin/admins"); } catch (e) { return root.append(errBox(e)); }
    if (!state.me.is_owner)
      root.append(el("div", { class: "sub-banner", text: T("app.admin.owner_only_note") }));
    for (const u of admins) {
      const card = el("div", { class: "card" },
        el("div", { class: "row" }, el("h3", { class: "grow", text: u.name || String(u.tg_id) }), rolePill(u)),
        el("div", { class: "muted", text: `🆔 ${u.tg_id} ${u.username ? "@" + u.username : ""}` }));
      if (state.me.is_owner && u.role === "admin") {
        card.append(el("div", { class: "row wrap", style: "margin-top:8px" },
          el("button", { class: "btn danger sm", text: T("app.admin.remove_admin"),
            onclick: async () => { await guard(() => api(`/api/admin/admins/${u.tg_id}`, { method: "DELETE" })); renderAdmin(); } }),
          el("button", { class: "btn sm", text: T("app.admin.transfer"),
            onclick: () => confirmTransfer(u) })));
      }
      root.append(card);
    }
    if (state.me.is_owner) {
      const idIn = el("input", { type: "text", placeholder: T("app.admin.add_user_ph") });
      root.append(el("div", { class: "card" },
        el("div", { class: "section-title", text: T("app.admin.make_admin") }),
        el("label", { class: "field" }, idIn),
        el("button", { class: "btn primary block", text: T("app.common.add"), onclick: async () => {
          const tg_id = parseInt(idIn.value, 10); if (!tg_id) return toast("ID");
          await guard(() => api("/api/admin/admins", { method: "POST", body: { tg_id } }));
          renderAdmin();
        } })));
    }
  }

  function confirmTransfer(u) {
    const msg = T("app.admin.transfer_confirm", { name: u.name || u.tg_id });
    const go = async () => {
      await guard(() => api("/api/admin/transfer-ownership", { method: "POST", body: { tg_id: u.tg_id } }));
      toast(T("app.admin.transfer_done"));
      try { state.me = await api("/api/me"); } catch {}
      renderShell(); renderAdmin();
    };
    if (tg && tg.showConfirm) tg.showConfirm(msg, (ok) => ok && go());
    else if (confirm(msg)) go();
  }

  async function adminSub(root) {
    let info;
    try { info = await api("/api/admin/subscription"); } catch (e) { return root.append(errBox(e)); }
    const toggle = el("input", { type: "checkbox", ...(info.enabled ? { checked: "checked" } : {}) });
    toggle.addEventListener("change", async () => {
      await guard(() => api("/api/admin/subscription", { method: "PUT", body: { enabled: toggle.checked } }));
      state.me = await api("/api/me"); renderShell();
      toast(T("app.admin.saved"));
    });
    root.append(el("div", { class: "card" },
      el("label", { class: "row" }, toggle, el("span", { class: "grow", text: T("app.admin.sub_enabled") }))));

    root.append(el("div", { class: "section-title", text: T("app.admin.plans") }));
    const plansWrap = el("div");
    const rows = JSON.parse(JSON.stringify(info.plans || []));
    function drawPlans() {
      clear(plansWrap);
      rows.forEach((p, i) => {
        const key = el("input", { type: "text", value: p.key || "" });
        const days = el("input", { type: "number", value: p.days || 30 });
        const stars = el("input", { type: "number", value: p.stars || 100 });
        const title = el("input", { type: "text", value: (p.title_i18n && (p.title_i18n[state.me.language] || p.title_i18n.uz)) || "" });
        key.oninput = () => p.key = key.value;
        days.oninput = () => p.days = parseInt(days.value, 10) || 1;
        stars.oninput = () => p.stars = parseInt(stars.value, 10) || 1;
        title.oninput = () => { p.title_i18n = p.title_i18n || {}; p.title_i18n[state.me.language] = title.value; };
        plansWrap.append(el("div", { class: "card" },
          el("label", { class: "field" }, el("span", { text: T("app.admin.plan_key") }), key),
          el("label", { class: "field" }, el("span", { text: T("app.admin.plan_title") }), title),
          el("div", { class: "row" },
            el("label", { class: "field grow" }, el("span", { text: T("app.admin.plan_days") }), days),
            el("label", { class: "field grow" }, el("span", { text: T("app.admin.plan_stars") }), stars)),
          el("button", { class: "btn danger sm", text: T("app.common.delete"), onclick: () => { rows.splice(i, 1); drawPlans(); } })));
      });
    }
    drawPlans();
    root.append(plansWrap);
    root.append(el("button", { class: "btn sm", text: T("app.admin.add_plan"),
      onclick: () => { rows.push({ key: "p" + (rows.length + 1), days: 30, stars: 100, title_i18n: {} }); drawPlans(); } }));
    root.append(el("button", { class: "btn primary block", style: "margin-top:10px", text: T("app.admin.save"),
      onclick: async () => { await guard(() => api("/api/admin/subscription", { method: "PUT", body: { plans: rows } })); toast(T("app.admin.saved")); } }));
  }

  async function adminContent(root) {
    let subjects;
    try { subjects = await api("/api/admin/content/subjects"); } catch (e) { return root.append(errBox(e)); }
    root.append(el("div", { class: "section-title", text: T("app.admin.content_subjects") }));
    for (const s of subjects) {
      root.append(el("div", { class: "card tap", onclick: () => contentSets(s) },
        el("div", { class: "grow" }, el("h3", { text: (s.name_i18n && (s.name_i18n[state.me.language] || s.name_i18n.uz)) || s.slug }),
          el("div", { class: "muted", text: s.slug + (s.active ? "" : " • ✖") })),
        el("span", { text: "›" })));
    }
    root.append(subjectForm(null, () => renderAdmin()));
  }

  function subjectForm(existing, done) {
    const slug = el("input", { type: "text", value: existing ? existing.slug : "", placeholder: "algebra" });
    const names = {};
    const box = el("div", { class: "card" },
      el("div", { class: "section-title", text: existing ? T("app.common.edit") : T("app.admin.new_subject") }),
      el("label", { class: "field" }, el("span", { text: "slug" }), slug));
    for (const lng of ["uz", "ru", "en", "kaa"]) {
      const inp = el("input", { type: "text", value: existing && existing.name_i18n ? (existing.name_i18n[lng] || "") : "" });
      names[lng] = inp;
      box.append(el("label", { class: "field" }, el("span", { text: T("app.admin.name_" + lng) }), inp));
    }
    box.append(el("button", { class: "btn primary block", text: T("app.common.save"), onclick: async () => {
      const body = { slug: slug.value.trim(), name_i18n: {}, active: true, order: existing ? existing.order : 0 };
      for (const lng of ["uz", "ru", "en", "kaa"]) if (names[lng].value.trim()) body.name_i18n[lng] = names[lng].value.trim();
      if (!body.slug) return toast("slug");
      await guard(() => existing
        ? api(`/api/admin/content/subjects/${existing.id}`, { method: "PUT", body })
        : api("/api/admin/content/subjects", { method: "POST", body }));
      done();
    } }));
    if (existing) box.append(el("button", { class: "btn danger sm", text: T("app.common.delete"), onclick: async () => {
      if (!confirm(T("app.admin.delete_confirm"))) return;
      await guard(() => api(`/api/admin/content/subjects/${existing.id}`, { method: "DELETE" })); done();
    } }));
    return box;
  }

  async function contentSets(subject) {
    clear($("#adminBody"));
    const root = $("#adminBody");
    root.append(el("button", { class: "btn ghost sm", text: T("common.back"), onclick: renderAdmin }));
    root.append(el("div", { class: "section-title", text: (subject.name_i18n && (subject.name_i18n[state.me.language] || subject.name_i18n.uz)) || subject.slug }));
    root.append(subjectForm(subject, () => renderAdmin()));
    let sets;
    try { sets = await api(`/api/admin/content/subjects/${subject.id}/sets`); } catch (e) { return root.append(errBox(e)); }
    root.append(el("div", { class: "section-title", text: T("app.admin.content_sets") }));
    for (const st of sets) {
      root.append(el("div", { class: "card tap", onclick: () => contentQuestions(subject, st) },
        el("div", { class: "grow" }, el("h3", { text: (st.title_i18n && (st.title_i18n[state.me.language] || st.title_i18n.uz)) || ("#" + st.id) }),
          el("div", { class: "muted", text: `${st.question_count} • ${st.time_limit_sec}s${st.active ? "" : " • ✖"}` })),
        el("span", { text: "›" })));
    }
    root.append(setForm(subject, null, () => contentSets(subject)));
  }

  function setForm(subject, existing, done) {
    const titles = {};
    const box = el("div", { class: "card" },
      el("div", { class: "section-title", text: existing ? T("app.common.edit") : T("app.admin.new_set") }));
    for (const lng of ["uz", "ru", "en", "kaa"]) {
      const inp = el("input", { type: "text", value: existing && existing.title_i18n ? (existing.title_i18n[lng] || "") : "" });
      titles[lng] = inp;
      box.append(el("label", { class: "field" }, el("span", { text: T("app.admin.name_" + lng) }), inp));
    }
    const time = el("input", { type: "number", value: existing ? existing.time_limit_sec : 0 });
    box.append(el("label", { class: "field" }, el("span", { text: T("app.admin.time_limit") }), time));
    box.append(el("button", { class: "btn primary block", text: T("app.common.save"), onclick: async () => {
      const body = { subject_id: subject.id, title_i18n: {}, description_i18n: {}, time_limit_sec: parseInt(time.value, 10) || 0, active: true, order: existing ? existing.order : 0 };
      for (const lng of ["uz", "ru", "en", "kaa"]) if (titles[lng].value.trim()) body.title_i18n[lng] = titles[lng].value.trim();
      await guard(() => existing
        ? api(`/api/admin/content/sets/${existing.id}`, { method: "PUT", body })
        : api("/api/admin/content/sets", { method: "POST", body }));
      done();
    } }));
    if (existing) box.append(el("button", { class: "btn danger sm", text: T("app.common.delete"), onclick: async () => {
      if (!confirm(T("app.admin.delete_confirm"))) return;
      await guard(() => api(`/api/admin/content/sets/${existing.id}`, { method: "DELETE" })); done();
    } }));
    return box;
  }

  async function contentQuestions(subject, set) {
    clear($("#adminBody"));
    const root = $("#adminBody");
    root.append(el("button", { class: "btn ghost sm", text: T("common.back"), onclick: () => contentSets(subject) }));
    root.append(setForm(subject, set, () => contentSets(subject)));
    root.append(el("div", { class: "section-title", text: T("app.admin.content_questions") }));
    let qs2;
    try { qs2 = await api(`/api/admin/content/sets/${set.id}/questions`); } catch (e) { return root.append(errBox(e)); }
    for (const q of qs2) root.append(questionForm(set, q, () => contentQuestions(subject, set)));
    root.append(questionForm(set, null, () => contentQuestions(subject, set)));
  }

  function questionForm(set, existing, done) {
    const lng = state.me.language;
    const body = el("textarea", { placeholder: T("app.admin.q_body") });
    if (existing && existing.body_i18n) body.value = existing.body_i18n[lng] || existing.body_i18n.uz || "";
    const opts = el("textarea", { placeholder: T("app.admin.q_options") });
    if (existing && existing.options_i18n) opts.value = (existing.options_i18n[lng] || existing.options_i18n.uz || []).join("\n");
    const correct = el("input", { type: "number", min: "1", value: existing ? existing.correct_index + 1 : 1 });
    const expl = el("textarea", { placeholder: T("app.admin.q_explanation") });
    if (existing && existing.explanation_i18n) expl.value = existing.explanation_i18n[lng] || existing.explanation_i18n.uz || "";

    const box = el("div", { class: "card" },
      el("div", { class: "section-title", text: existing ? "#" + existing.id : T("app.admin.new_question") }),
      el("label", { class: "field" }, el("span", { text: T("app.admin.q_body") + " (" + lng + ")" }), body),
      el("label", { class: "field" }, el("span", { text: T("app.admin.q_options") }), opts),
      el("label", { class: "field" }, el("span", { text: T("app.admin.q_correct") }), correct),
      el("label", { class: "field" }, el("span", { text: T("app.admin.q_explanation") }), expl));
    box.append(el("button", { class: "btn primary block", text: T("app.common.save"), onclick: async () => {
      const optionList = opts.value.split("\n").map(s => s.trim()).filter(Boolean);
      if (!body.value.trim() || optionList.length < 2) return toast("?");
      const payload = {
        test_set_id: set.id,
        order: existing ? existing.order : 0,
        body_i18n: mergeI18n(existing && existing.body_i18n, lng, body.value.trim()),
        options_i18n: mergeI18n(existing && existing.options_i18n, lng, optionList),
        correct_index: Math.max(0, (parseInt(correct.value, 10) || 1) - 1),
        explanation_i18n: mergeI18n(existing && existing.explanation_i18n, lng, expl.value.trim()),
      };
      await guard(() => existing
        ? api(`/api/admin/content/questions/${existing.id}`, { method: "PUT", body: payload })
        : api("/api/admin/content/questions", { method: "POST", body: payload }));
      done();
    } }));
    if (existing) box.append(el("button", { class: "btn danger sm", text: T("app.common.delete"), onclick: async () => {
      if (!confirm(T("app.admin.delete_confirm"))) return;
      await guard(() => api(`/api/admin/content/questions/${existing.id}`, { method: "DELETE" })); done();
    } }));
    return box;
  }

  function mergeI18n(existing, lng, value) {
    const out = existing ? JSON.parse(JSON.stringify(existing)) : {};
    out[lng] = value;
    return out;
  }

  async function adminBroadcast(root) {
    const ta = el("textarea", { placeholder: T("app.admin.broadcast_ph"), rows: "5" });
    root.append(el("label", { class: "field" }, ta));
    root.append(el("button", { class: "btn primary block", text: T("app.admin.broadcast_send"), onclick: async () => {
      if (!ta.value.trim()) return;
      const res = await guard(() => api("/api/admin/broadcast", { method: "POST", body: { text: ta.value.trim() } }));
      if (res) toast(T("app.admin.broadcast_sent", { ok: res.ok, total: res.total }));
      ta.value = "";
    } }));
  }

  async function adminStats(root) {
    let info;
    try { info = await api("/api/admin/overview"); } catch (e) { return root.append(errBox(e)); }
    const c = info.counts;
    const rows = [
      [T("app.admin.stats_users"), c.users],
      [T("app.admin.stats_approved"), c.approved],
      [T("app.admin.stats_pending"), c.pending],
      [T("app.admin.stats_active_subs"), c.active_subs],
      [T("app.admin.stats_attempts"), c.attempts],
    ];
    for (const [label, val] of rows) {
      root.append(el("div", { class: "card row" }, el("span", { class: "grow", text: label }),
        el("strong", { text: String(val) })));
    }
  }

  function errBox(e) {
    return el("div", { class: "empty", text: (e && e.message) || "Error" });
  }

  async function guard(fn) {
    try { return await fn(); }
    catch (e) {
      toast(e.status === 403 ? T("err.owner_only") : (e.message || "Error"));
      return null;
    }
  }

  // ---- go --------------------------------------------------------
  boot();
})();
