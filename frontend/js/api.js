// Shared helpers used by every page.
// When the page is served by Flask (locally on :5000 or on Render) the API is on
// the same origin. When opened with VS Code Live Server (:5500) or as a file,
// it talks to the local Flask server instead.
const API_BASE = window.SKILLSWAP_API_BASE ||
  ((location.protocol === "file:" || /^55\d\d$/.test(location.port))
    ? "http://127.0.0.1:5000/api"
    : `${location.origin}/api`);

function getToken(){ try { return localStorage.getItem("skillswap_token"); } catch { return null; } }
function getUser(){ try { return JSON.parse(localStorage.getItem("skillswap_user") || "{}"); } catch { return {}; } }
function saveLogin(data){
  localStorage.setItem("skillswap_token", data.token);
  localStorage.setItem("skillswap_user", JSON.stringify(data.user));
}
function logout(reason){
  try { localStorage.removeItem("skillswap_token"); localStorage.removeItem("skillswap_user"); } catch {}
  window.location.href = "login.html" + (reason ? `?reason=${reason}` : "");
}

async function api(path, options = {}) {
  const headers = {"Content-Type": "application/json", ...(options.headers || {})};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {...options, headers});
  } catch {
    throw new Error("Cannot reach the SkillSwap server. Check that the backend is running.");
  }
  const data = await response.json().catch(() => ({}));
  if (response.status === 401 && token && String(data.code || "").startsWith("token")) {
    logout("expired");
    throw new Error(data.error || "Please log in again.");
  }
  if (!response.ok) throw new Error(data.error || "Something went wrong.");
  return data;
}

function requireLogin(){
  if (!getToken()) { window.location.href = "login.html"; return false; }
  return true;
}

// ---------- tiny DOM helpers (safe: text is never parsed as HTML) ----------
function el(tag, attrs = {}, ...children){
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}
const $ = id => document.getElementById(id);

function toast(message, kind = "info"){
  let box = $("toastBox");
  if (!box) { box = el("div", {id: "toastBox", class: "toast-box", "aria-live": "polite"}); document.body.append(box); }
  const t = el("div", {class: `toast toast-${kind}`, text: message});
  box.append(t);
  setTimeout(() => t.classList.add("hide"), 3200);
  setTimeout(() => t.remove(), 3700);
}

function initials(name){
  return (name || "?").split(/\s+/).filter(Boolean).slice(0, 2).map(p => p[0].toUpperCase()).join("");
}
function avatar(person, size = ""){
  const box = el("div", {class: `avatar ${size}`});
  if (person.photo) {
    const img = el("img", {src: person.photo, alt: "", referrerpolicy: "no-referrer"});
    img.addEventListener("error", () => { img.remove(); box.textContent = initials(person.name); });
    box.append(img);
  } else box.textContent = initials(person.name);
  return box;
}
function verifiedBadge(person){
  if (person.linkedin_verified || person.linkedin_status === "verified")
    return el("span", {class: "badge badge-verified", title: "Name cross-checked with LinkedIn"}, "✓ LinkedIn verified");
  return null;
}
function ratingText(person){
  if (!person.review_count) return null;
  return el("span", {class: "rating"}, `★ ${person.avg_rating} (${person.review_count})`);
}
function formatDate(value, withTime = true){
  if (!value) return "Date not set";
  const d = new Date(value);
  return d.toLocaleString(undefined, withTime
    ? {weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit"}
    : {day: "numeric", month: "short", year: "numeric"});
}
function profileLink(id){ return `user.html?id=${id}`; }

// ---------- shared navigation ----------
const NAV = [
  ["dashboard", "dashboard.html", "Dashboard"],
  ["profile", "profile.html", "My profile"],
  ["matches", "matches.html", "Find matches"],
  ["requests", "requests.html", "Requests"],
  ["chat", "chat.html", "Messages"],
  ["sessions", "sessions.html", "Sessions"],
  ["roadmap", "roadmap.html", "AI roadmap"],
];
function renderNav(){
  const header = $("appHeader");
  if (!header) return;
  const page = document.body.dataset.page;
  const loggedIn = !!getToken();
  const nav = el("nav", {id: "mainNav"});
  if (loggedIn) {
    NAV.forEach(([key, href, label]) => nav.append(
      el("a", {href, class: key === page ? "active" : null, id: `nav-${key}`}, label)));
    nav.append(el("button", {class: "btn btn-small", id: "logoutBtn", onclick: () => logout()}, "Logout"));
  } else {
    nav.append(el("a", {href: "login.html"}, "Login"),
               el("a", {class: "btn btn-small", href: "register.html"}, "Get started"));
  }
  const toggle = el("button", {class: "nav-toggle", "aria-label": "Menu", "aria-expanded": "false",
    onclick: () => { const open = header.classList.toggle("open"); toggle.setAttribute("aria-expanded", open); }}, "☰");
  header.replaceChildren(
    el("a", {class: "brand", href: loggedIn ? "dashboard.html" : "index.html"}, "Skill", el("span", {}, "Swap")),
    toggle, nav);
  if (loggedIn) {
    api("/requests").then(d => {
      const pending = d.incoming.filter(r => r.status === "pending").length;
      if (pending) $("nav-requests")?.append(el("span", {class: "nav-count"}, pending));
    }).catch(() => {});
  }
}
document.addEventListener("DOMContentLoaded", renderNav);
