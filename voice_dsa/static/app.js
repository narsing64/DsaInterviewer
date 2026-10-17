"use strict";
const $ = id => document.getElementById(id);
function el(tag, text, cls) { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; if (cls) e.className = cls; return e; }
const pretty = t => t.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
function store(k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } }

async function api(path, body, retry = true) {
  let code = ""; try { code = sessionStorage.getItem("code") || ""; } catch (e) {}
  const opts = { headers: { "X-Access-Code": code } };
  if (body) { opts.method = "POST"; opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
  const r = await fetch(path, opts);
  if (r.status === 401 && retry) {
    const c = prompt("Enter the access code to use this app:");
    if (c) { try { sessionStorage.setItem("code", c); } catch (e) {} return api(path, body, false); }
  }
  const d = await r.json(); if (d.error) throw new Error(d.error); return d;
}

/* ───────── theme + router ───────── */
document.documentElement.dataset.theme = store("theme") || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
$("themeBtn").onclick = () => { const t = document.documentElement.dataset.theme === "dark" ? "light" : "dark"; document.documentElement.dataset.theme = t; store("theme", t); };

const PAGES = ["interview", "learn", "quiz", "progress"];
function route() {
  const page = PAGES.includes(location.hash.slice(1)) ? location.hash.slice(1) : "interview";
  PAGES.forEach(p => $("page-" + p).classList.toggle("hidden", p !== page));
  document.querySelectorAll(".nav .tab").forEach(a => a.classList.toggle("on", a.dataset.page === page));
  if (page !== "interview") stopListening(false);
  if (page === "learn") renderLearn(); if (page === "quiz") renderQuizSetup(); if (page === "progress") renderProgress();
  window.scrollTo(0, 0);
}
addEventListener("hashchange", route);

/* ───────── interview setup ───────── */
let pickedTopic = "", pickedDiff = "", sid = null, busy = false, hands = true, timerId = null, t0 = 0, finished = false;
const AGENTS = [["🧭 Supervisor", "Routes every turn to the right specialist"], ["🔍 Analyst", "Tracks your approach, complexity and edge cases"],
  ["❓ Clarifier", "Answers your questions without leaking the solution"], ["🎯 Prober", "Follows up on what you actually said"],
  ["💡 Hinter", "Three levels of hints on request"], ["🧪 Code Reviewer", "Checks correctness, bugs and complexity"],
  ["📊 Evaluator", "Scores you on a clear rubric"], ["🎓 Coach", "Builds your study plan"]];
AGENTS.forEach(([t, d]) => { const a = el("div", undefined, "agent"); a.append(el("b", t), el("span", d, "mute")); $("agentList").append(a); });

function chipRow(container, items, get, set) {
  container.replaceChildren(); items.forEach(([val, label]) => { const c = el("button", label, "chip btn" + (get() === val ? " on" : ""));
    c.onclick = () => { set(val); chipRow(container, items, get, set); }; container.append(c); });
}
api("/api/topics").then(d => {
  $("pillCount").textContent = d.total + " problems · " + d.topics.length + " topics";
  const items = [["", "Any topic"], ...d.topics.map(t => [t, pretty(t) + " (" + d.counts[t] + ")"])];
  chipRow($("topicChips"), items, () => pickedTopic, v => pickedTopic = v);
}).catch(() => {});
(function () { const seg = $("diffSeg"); [["", "Any"], ["easy", "Easy"], ["medium", "Medium"], ["hard", "Hard"]].forEach(([v, l]) => {
  const b = el("button", l, v === "" ? "on" : ""); b.onclick = () => { pickedDiff = v; [...seg.children].forEach(x => x.classList.toggle("on", x === b)); }; seg.append(b); }); })();
$("handsFree").onchange = $("handsFree2").onchange = e => { hands = e.target.checked; $("handsFree").checked = $("handsFree2").checked = hands; };
$("handsFree2").checked = true;

$("startBtn").onclick = async () => {
  $("startBtn").disabled = true; $("setupMsg").textContent = "Setting up your interviewer…"; finished = false;
  try {
    const d = await api("/api/start", { topic: pickedTopic, difficulty: pickedDiff, voice: $("voice").value });
    sid = d.session_id; $("log").replaceChildren(); $("code").value = ""; $("review").textContent = ""; $("caption").textContent = "";
    $("botName").textContent = "Interviewer · " + $("voice").value.replace(/^./, c => c.toUpperCase());
    $("pTitle").textContent = d.problem.title; $("pDesc").textContent = d.problem.description; $("pCons").textContent = "Constraints: " + d.problem.constraints;
    $("pChips").replaceChildren(el("span", d.problem.difficulty, "chip"), el("span", pretty(d.problem.topic), "chip"));
    $("setup").classList.add("hidden"); $("room").classList.remove("hidden");
    t0 = Date.now(); clearInterval(timerId);
    timerId = setInterval(() => { const s = Math.floor((Date.now() - t0) / 1000); $("timer").textContent = String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0"); }, 1000);
    handleBot(d); $("setupMsg").textContent = "";
  } catch (e) { $("setupMsg").textContent = e.message; }
  $("startBtn").disabled = false;
};

/* ───────── room rendering ───────── */
const STEPS = [["clarify", "1 · Clarify"], ["probe", "2 · Follow-ups"], ["coding", "3 · Code"], ["done", "4 · Feedback"]];
function addMsg(who, text, label) {
  const m = el("div", undefined, "msg " + who); m.append(el("small", label || (who === "me" ? "You" : "")), document.createTextNode(text));
  $("log").append(m); $("log").scrollTop = $("log").scrollHeight;
}
function chips(container, list) { container.replaceChildren(...(list.length ? list : ["—"]).map(x => el("span", x, "chip"))); }
function update(s) {
  const idx = STEPS.findIndex(x => x[0] === s.stage);
  $("steps").replaceChildren(...STEPS.map((x, i) => el("div", x[1], "step" + (i === idx ? " on" : i < idx ? " past" : ""))));
  chips($("sAlgo"), s.algorithm ? [s.algorithm] : []); chips($("sCx"), s.complexity ? [s.complexity] : []); chips($("sEdge"), s.edge_cases);
  $("sProbe").textContent = s.probes; $("sHint").textContent = s.hints;
}

/* ───────── interviewer voice + phases ───────── */
const PHASE = { idle: ["Ready", ""], speaking: ["Speaking", "speaking"], listening: ["Listening", "listening"], thinking: ["Thinking…", "thinking"] };
function setPhase(p) {
  $("orb").className = "orb " + PHASE[p][1]; $("botState").textContent = PHASE[p][0];
  $("tileBot").classList.toggle("live", p === "speaking"); $("tileMe").classList.toggle("live", p === "listening");
  $("meState").textContent = p === "listening" ? "Listening" : "Mic off";
  $("meHint").textContent = p === "listening" ? "Speak naturally — I'll send when you pause" : p === "thinking" ? "Processing what you said…" :
    hands ? "I'll start listening when the interviewer finishes" : "Click Answer to speak";
}
function handleBot(d) {
  if (d.reply) { addMsg("bot", d.reply, d.agent); $("caption").textContent = d.reply; }
  if (d.state) update(d.state);
  const after = () => { setPhase("idle"); if (hands && !finished) startListening(); };
  if (d.audio && $("speakOn").checked) {
    const p = $("player"); p.src = "data:audio/wav;base64," + d.audio; setPhase("speaking");
    p.onended = after; p.onerror = after; p.play().catch(after);
  } else after();
}

/* ───────── listening (mic + silence detection) ───────── */
const SILENCE_MS = 2200, NOSPEECH_MS = 20000, MAX_MS = 150000;
let listening = false, rec = null, chunks = [], stream = null, actx = null, analyser = null, raf = 0, sendOnStop = false;
const bars = []; for (let i = 0; i < 14; i++) { const b = el("i"); bars.push(b); $("meter").append(b); }

async function startListening() {
  if (listening || busy || finished) return;
  try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
  catch (e) { $("status").textContent = "Microphone unavailable: " + e.message; setPhase("idle"); return; }
  $("player").pause();
  actx = new (window.AudioContext || window.webkitAudioContext)(); analyser = actx.createAnalyser(); analyser.fftSize = 512;
  actx.createMediaStreamSource(stream).connect(analyser);
  rec = new MediaRecorder(stream); chunks = [];
  rec.ondataavailable = e => chunks.push(e.data);
  rec.onstop = onRecStop;
  rec.start(); listening = true; sendOnStop = false; setPhase("listening"); $("mic").textContent = "■ Send answer"; $("meter").classList.add("on");
  const buf = new Uint8Array(analyser.fftSize), t = performance.now(); let spoke = false, lastSound = t, floor = 0, n = 0;
  (function loop() {
    if (!listening) return;
    analyser.getByteTimeDomainData(buf); let sum = 0; for (const v of buf) sum += ((v - 128) / 128) ** 2; const rms = Math.sqrt(sum / buf.length);
    const now = performance.now(); if (now - t < 500) { floor = (floor * n + rms) / (n + 1); n++; }
    const thresh = Math.max(0.02, floor * 2.5);
    if (rms > thresh) { spoke = true; lastSound = now; }
    bars.forEach((b, i) => b.style.height = Math.min(46, 4 + rms * 420 * (0.55 + 0.45 * Math.sin(now / 90 + i))) + "px");
    if (spoke && now - lastSound > SILENCE_MS) return stopListening(true);
    if (!spoke && now - t > NOSPEECH_MS) return stopListening(false);
    if (now - t > MAX_MS) return stopListening(spoke);
    raf = requestAnimationFrame(loop);
  })();
}
function stopListening(send) {
  if (!listening) return; listening = false; sendOnStop = send; cancelAnimationFrame(raf);
  if (rec && rec.state === "recording") rec.stop();
}
async function onRecStop() {
  stream.getTracks().forEach(t => t.stop()); if (actx) actx.close(); $("mic").textContent = "🎤 Answer"; $("meter").classList.remove("on"); bars.forEach(b => b.style.height = "4px");
  if (!sendOnStop || !chunks.length) { setPhase("idle"); $("meHint").textContent = "Didn't hear anything — click Answer when you're ready"; return; }
  const blob = new Blob(chunks, { type: rec.mimeType });
  const b64 = await new Promise(res => { const f = new FileReader(); f.onload = () => res(f.result.split(",")[1]); f.readAsDataURL(blob); });
  turn({ audio: b64, mime: blob.type.split(";")[0] }, "");
}
$("mic").onclick = () => { if (listening) stopListening(true); else if (!busy) startListening(); };

/* ───────── turns ───────── */
function setBusy(b) { busy = b; ["send", "hint", "end", "submitCode", "mic", "text"].forEach(i => $(i).disabled = b); }
async function turn(payload, shown) {
  if (busy) return; stopListening(false); setBusy(true); setPhase("thinking"); $("status").textContent = "";
  try {
    const d = await api("/api/turn", { session_id: sid, ...payload });
    const said = d.transcript || shown; if (said) addMsg("me", said);
    $("text").value = "";
    if (d.review) showReview(d.review);
    if (!d.reply) { setBusy(false); setPhase("idle"); $("status").textContent = "Didn't catch that — try again."; if (hands) startListening(); return; }
    if (d.result) { finished = true; clearInterval(timerId); handleBot(d); $("status").textContent = "Interview finished"; showScore(d.result); return; }
    setBusy(false); handleBot(d); return;
  } catch (e) { $("status").textContent = "Error: " + e.message; }
  setBusy(false); setPhase("idle");
}
function showReview(r) { $("review").textContent = (r.correct ? "✅ Looks correct. " : "⚠️ Issues found. ") + "Time " + r.time_complexity + ", space " + r.space_complexity + ". " + (r.bugs.length ? "Bugs: " + r.bugs.join("; ") : ""); }
$("send").onclick = () => { const t = $("text").value.trim(); if (t) turn({ text: t }, t); };
$("text").addEventListener("keydown", e => { if (e.key === "Enter") $("send").click(); });
$("hint").onclick = () => turn({ text: "Can I get a hint?" }, "Can I get a hint?");
$("end").onclick = () => { if (confirm("End the interview and get your feedback?")) turn({ text: "", end: true }, "(ended the interview)"); };
$("submitCode").onclick = () => { if ($("code").value.trim()) turn({ text: "", code: $("code").value }, "(submitted code)"); };
$("code").addEventListener("keydown", e => { if (e.key === "Tab") { e.preventDefault(); const t = e.target, s = t.selectionStart; t.value = t.value.slice(0, s) + "    " + t.value.slice(t.selectionEnd); t.selectionStart = t.selectionEnd = s + 4; } });

/* ───────── scorecard ───────── */
function showScore(r) {
  const ev = r.scores, rep = r.report, body = $("scoreBody"); body.replaceChildren();
  const color = ev.verdict === "Strong" ? "var(--good)" : ev.verdict === "Average" ? "var(--warn)" : "var(--bad)";
  const top = el("div", undefined, "row"); const v = el("span", ev.verdict, "verdict"); v.style.background = color;
  top.append(el("span", ev.total + "/10", "big"), v, el("span", r.problem + " · " + Math.max(1, Math.round(r.duration_sec / 60)) + " min · " + r.hints + " hint(s)", "mute")); body.append(top);
  body.append(el("h3", "Rubric")); body.lastChild.style.marginTop = "16px";
  const crit = { clarification: "Clarification", communication: "Communication", complexity: "Complexity", edge_cases: "Edge cases", adaptability: "Adaptability" };
  Object.entries(crit).forEach(([k, label]) => { const row = el("div", undefined, "row"); const l = el("span", label, "mute"); l.style.width = "110px"; row.append(l);
    const bar = el("div", undefined, "bar"), i = el("i"); i.style.width = (ev.scores[k] / 2 * 100) + "%"; bar.append(i); row.append(bar, el("b", ev.scores[k] + "/2")); body.append(row); });
  if (ev.code_quality !== null) body.append(el("p", "Code quality: " + ev.code_quality + "/2 (reported separately)", "mute"));
  if (ev.hint_penalty) body.append(el("p", "−1 point for using 3+ hints.", "mute"));
  const list = (title, items) => { body.append(el("h3", title)); const ul = el("ul"); items.forEach(x => ul.append(el("li", x))); body.append(ul); };
  list("Strengths", ev.strengths); list("To improve", ev.improvements); list("Study plan", rep.study_plan);
  body.append(el("h3", "Model approach"), el("p", rep.model_approach));
  if (rep.related && rep.related.length) list("Practice next", rep.related.map(x => x.title + " (" + x.difficulty + ")"));
  const row = el("div", undefined, "row"); const dl = el("button", "Download transcript");
  dl.onclick = async () => { const s = await api("/api/session/" + r.session_id); const txt = s.transcript.map(t => t.role.toUpperCase() + ": " + t.content).join("\n\n");
    const a = el("a"); a.href = URL.createObjectURL(new Blob([txt], { type: "text/plain" })); a.download = "interview-" + r.session_id.slice(0, 6) + ".txt"; a.click(); };
  const again = el("button", "New interview", "primary"); again.onclick = () => { $("score").classList.add("hidden"); $("room").classList.add("hidden"); $("setup").classList.remove("hidden"); location.hash = "#interview"; };
  const close = el("button", "Close"); close.onclick = () => $("score").classList.add("hidden");
  row.append(dl, again, close); body.append(row); $("score").classList.remove("hidden");
}

/* ───────── learn ───────── */
let catalog = null, learnSel = { subject: null, topic: null };
async function getCatalog() { if (!catalog) catalog = (await api("/api/learn/catalog")).subjects; return catalog; }
async function renderLearn() {
  const root = $("page-learn"); root.replaceChildren(el("p", "Loading…", "mute"));
  try {
    const subs = await getCatalog(); root.replaceChildren();
    root.append(el("h1", "Learn"), el("p", "Concise study notes for every SDE interview topic, with model answers to common questions.", "mute"));
    if (!learnSel.subject) {
      const g = el("div", undefined, "grid3"); g.style.marginTop = "16px";
      subs.forEach(s => { const c = el("div", undefined, "card subj"); c.append(el("div", s.icon, "ic"), el("h3", s.title), el("span", s.topics.length + " topics", "mute"));
        c.onclick = () => { learnSel = { subject: s.id, topic: null }; renderLearn(); }; g.append(c); });
      root.append(g); return;
    }
    const s = subs.find(x => x.id === learnSel.subject);
    const back = el("button", "← All subjects"); back.onclick = () => { learnSel = { subject: null, topic: null }; renderLearn(); }; root.append(back);
    root.append(el("h2", s.icon + " " + s.title)); root.lastChild.style.margin = "16px 0 10px";
    const layout = el("div", undefined, "room"); layout.style.gridTemplateColumns = "minmax(0,300px) minmax(0,1fr)";
    const list = el("div", undefined, "list"), pane = el("div", undefined, "card note");
    s.topics.forEach(t => { const a = el("a", t); a.href = "javascript:void 0"; if (t === learnSel.topic) a.style.borderColor = "var(--brand)";
      a.onclick = () => { learnSel.topic = t; renderLearn(); }; list.append(a); });
    layout.append(list, pane); root.append(layout);
    if (!learnSel.topic) { pane.append(el("p", "Pick a topic to read its study note.", "mute")); return; }
    pane.append(el("span", "", "spinner"), el("span", "  Preparing your note (first time can take ~15s)…", "mute"));
    const n = await api("/api/learn/note", { subject: learnSel.subject, topic: learnSel.topic }); pane.replaceChildren();
    pane.append(el("h2", n.topic), el("p", n.summary));
    const sec = (title, items) => { pane.append(el("h3", title)); const ul = el("ul"); items.forEach(x => ul.append(el("li", x))); pane.append(ul); };
    sec("Key points", n.key_points); sec("Cheat sheet", n.cheat_sheet || []); sec("Common pitfalls", n.pitfalls || []);
    pane.append(el("h3", "Interview questions"));
    n.interview_questions.forEach(q => { const d = el("details", undefined, "qa"); d.append(el("summary", q.q), el("p", q.a)); pane.append(d); });
    const row = el("div", undefined, "row"); row.style.marginTop = "16px";
    const qb = el("button", "Quiz me on this topic", "primary"); qb.onclick = () => { quizPick = { subject: learnSel.subject, topic: learnSel.topic }; location.hash = "#quiz"; };
    row.append(qb); pane.append(row);
  } catch (e) { root.append(el("p", e.message, "toast")); }
}

/* ───────── quiz ───────── */
let quizPick = null, quizDiff = "medium";
async function renderQuizSetup() {
  const root = $("page-quiz"); root.replaceChildren(el("p", "Loading…", "mute"));
  try {
    const subs = await getCatalog(); root.replaceChildren();
    root.append(el("h1", "Quiz"), el("p", "Quick multiple-choice questions with explanations. New questions are generated for every topic.", "mute"));
    const card = el("div", undefined, "card setup"); card.style.marginTop = "16px";
    const subj = el("select"), topic = el("select"), n = el("select");
    subs.forEach(s => { const o = el("option", s.icon + " " + s.title); o.value = s.id; subj.append(o); });
    const fill = () => { topic.replaceChildren(); subs.find(s => s.id === subj.value).topics.forEach(t => { const o = el("option", t); o.value = t; topic.append(o); }); };
    subj.onchange = fill; if (quizPick) subj.value = quizPick.subject; fill(); if (quizPick) topic.value = quizPick.topic;
    [5, 8, 10].forEach(x => { const o = el("option", x + " questions"); o.value = x; n.append(o); });
    const seg = el("div", undefined, "seg"); ["easy", "medium", "hard"].forEach(d => { const b = el("button", pretty(d), d === quizDiff ? "on" : ""); b.onclick = () => { quizDiff = d; [...seg.children].forEach(x => x.classList.toggle("on", x === b)); }; seg.append(b); });
    const go = el("button", "Start quiz", "primary lg"), msg = el("span", "", "toast");
    card.append(el("label", "Subject", "lbl"), subj, el("label", "Topic", "lbl"), topic, el("label", "Difficulty", "lbl"), seg, el("label", "Length", "lbl"), n);
    const row = el("div", undefined, "row"); row.style.marginTop = "18px"; row.append(go, msg); card.append(row); root.append(card);
    go.onclick = async () => {
      go.disabled = true; msg.textContent = "Writing your questions… (first time can take ~20s)";
      try { const q = await api("/api/quiz/generate", { subject: subj.value, topic: topic.value, difficulty: quizDiff, n: +n.value }); runQuiz(q); }
      catch (e) { msg.textContent = e.message; go.disabled = false; }
    };
  } catch (e) { root.append(el("p", e.message, "toast")); }
}
function runQuiz(q) {
  const root = $("page-quiz"); let i = 0, score = 0;
  const show = () => {
    root.replaceChildren(); const cur = q.questions[i], total = q.questions.length;
    root.append(el("p", q.topic + " · " + q.difficulty + " · question " + (i + 1) + " of " + total, "mute"));
    const pr = el("div", undefined, "progress"), bar = el("i"); bar.style.width = (i / total * 100) + "%"; pr.append(bar); root.append(pr);
    const card = el("div", undefined, "card"); card.append(el("h2", cur.q)); const box = el("div"); let answered = false;
    cur.options.forEach((o, k) => { const b = el("button", o, "opt"); b.onclick = () => {
      if (answered) return; answered = true; if (k === cur.answer) score++;
      [...box.children].forEach((x, j) => { x.classList.add(j === cur.answer ? "right" : j === k ? "wrong" : "x"); x.disabled = true; });
      card.append(el("div", (k === cur.answer ? "✅ Correct. " : "❌ Not quite. ") + cur.explanation, "expl"));
      const next = el("button", i + 1 < total ? "Next question" : "See results", "primary"); next.style.marginTop = "14px";
      next.onclick = () => { i++; if (i < total) show(); else finish(); }; card.append(next); }; box.append(b); });
    card.append(box); root.append(card);
  };
  const finish = async () => {
    root.replaceChildren(); const total = q.questions.length, pct = Math.round(score / total * 100);
    const card = el("div", undefined, "card"); card.style.textAlign = "center";
    card.append(el("div", score + " / " + total, "big"), el("p", pct >= 80 ? "Excellent work! 🎉" : pct >= 50 ? "Good effort — review the explanations and retry." : "Keep going — read the study note and try again.", "mute"));
    const row = el("div", undefined, "row"); row.style.justifyContent = "center";
    const retry = el("button", "Try again", "primary"), nb = el("button", "New quiz"), study = el("button", "Study this topic");
    retry.onclick = async () => { try { runQuiz(await api("/api/quiz/generate", { subject: q.subject, topic: q.topic, difficulty: q.difficulty, n: total })); } catch (e) { alert(e.message); } };
    nb.onclick = () => renderQuizSetup(); study.onclick = () => { learnSel = { subject: q.subject, topic: q.topic }; location.hash = "#learn"; };
    row.append(retry, nb, study); card.append(row); root.append(card);
    api("/api/quiz/result", { subject: q.subject, topic: q.topic, difficulty: q.difficulty, score, total }).catch(() => {});
  };
  show();
}

/* ───────── progress ───────── */
async function renderProgress() {
  const root = $("page-progress"); root.replaceChildren(el("p", "Loading…", "mute"));
  try {
    const d = await api("/api/history"), s = d.stats, qz = d.quizzes; root.replaceChildren();
    root.append(el("h1", "Your progress"));
    const st = el("div", undefined, "stats"); st.style.marginTop = "14px";
    [["Interviews", s.total], ["Avg score", s.total ? s.average + "/10" : "—"], ["Best", s.total ? s.best + "/10" : "—"], ["Quiz accuracy", qz.count ? qz.accuracy + "%" : "—"]]
      .forEach(([l, v]) => { const c = el("div", undefined, "card stat"); c.append(el("b", String(v)), el("span", l, "mute")); st.append(c); }); root.append(st);
    if (!s.total && !qz.count) { root.append(el("p", "Nothing here yet — complete an interview or a quiz to see your progress.", "mute")); return; }
    if (s.total) {
      const trend = el("div", undefined, "card"); trend.append(el("h3", "Interview score trend"));
      const NS = "http://www.w3.org/2000/svg", svg = document.createElementNS(NS, "svg"); svg.setAttribute("viewBox", "0 0 300 90"); svg.style.cssText = "width:100%;color:var(--brand)";
      const pts = s.recent.map((r, i) => [s.recent.length === 1 ? 150 : 12 + i * 276 / (s.recent.length - 1), 82 - r.total_score * 7.6]);
      const line = document.createElementNS(NS, "polyline"); line.setAttribute("points", pts.map(p => p.join(",")).join(" ")); line.setAttribute("fill", "none"); line.setAttribute("stroke", "currentColor"); line.setAttribute("stroke-width", "2.5"); svg.append(line);
      pts.forEach(p => { const c = document.createElementNS(NS, "circle"); c.setAttribute("cx", p[0]); c.setAttribute("cy", p[1]); c.setAttribute("r", 4); c.setAttribute("fill", "currentColor"); svg.append(c); });
      trend.append(svg); root.append(trend);
      const tp = el("div", undefined, "card"); tp.style.marginTop = "12px"; tp.append(el("h3", "By topic"));
      Object.entries(s.topics).forEach(([t, v]) => { const row = el("div", undefined, "row"); const l = el("span", pretty(t), "mute"); l.style.width = "170px"; row.append(l);
        const bar = el("div", undefined, "bar"), i = el("i"); i.style.width = v.average * 10 + "%"; bar.append(i); row.append(bar, el("b", v.average + "/10 · " + v.count)); tp.append(row); });
      root.append(tp);
      const ls = el("div", undefined, "card"); ls.style.marginTop = "12px"; ls.append(el("h3", "All interviews"));
      d.sessions.forEach(r => { const row = el("div", undefined, "row"); row.style.marginBottom = "6px"; const b = el("button", r.problem_title);
        b.onclick = async () => { const f = await api("/api/session/" + r.session_id); showScore({ scores: f.scores, report: f.report, problem: f.problem_title, duration_sec: f.duration_sec, hints: f.hints_used, session_id: f.session_id }); };
        row.append(b, el("span", r.total_score + "/10 · " + r.verdict + " · " + r.difficulty + " · " + r.created_at.replace("T", " "), "mute")); ls.append(row); });
      root.append(ls);
    }
    if (qz.count) {
      const q = el("div", undefined, "card"); q.style.marginTop = "12px"; q.append(el("h3", "Recent quizzes"));
      qz.recent.forEach(r => q.append(el("div", r.topic + " — " + r.score + "/" + r.total + " (" + r.difficulty + ")", "mute"))); root.append(q);
    }
  } catch (e) { root.append(el("p", e.message, "toast")); }
}

setPhase("idle"); route();
