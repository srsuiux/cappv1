// Shared by every page: the token, the API helper, the status line, small DOM helpers.
const KEY = "cappv1.token";

export function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (v === true) el.setAttribute(k, "");
    else if (v !== false && v != null) el.setAttribute(k, v);
  }
  for (const kid of kids.flat()) if (kid != null) el.append(kid);
  return el;
}

// The address cappv1 prints ends in #t=<token>. Keep it for this tab and take it out of the address bar.
function token() {
  const m = location.hash.match(/t=([\w-]+)/);
  if (m) {
    try { sessionStorage.setItem(KEY, m[1]); } catch { /* private window: the token stays in memory below */ }
    memory = m[1];
    history.replaceState(null, "", location.pathname + location.search);
  }
  try { return sessionStorage.getItem(KEY) || memory; } catch { return memory; }
}
let memory = "";
token(); // pick the token out of the address as soon as any page loads

export class ApiError extends Error {
  constructor(e) { super(e.message); this.code = e.code; this.fix = e.fix || ""; }
}

export async function api(method, path, body, raw) {
  const headers = { "X-Cappv1-Token": token() || "" };
  if (body !== undefined && !raw) headers["Content-Type"] = "application/json";
  let res;
  try {
    res = await fetch("/api/v1" + path, { method, headers, body: raw ? body : body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new ApiError({ code: "offline", message: "Can't reach cappv1.", fix: "Is it still running? Start it again and open the address it prints." });
  }
  if (res.status === 401) throw new ApiError({ code: "unauthorized", message: "This page isn't linked to cappv1 yet.", fix: "Open the full address cappv1 printed, the one that ends in #t= and a code." });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new ApiError(data.error || { code: "error", message: "Something went wrong." });
  }
  return res;
}
export const getJson = async (path) => (await api("GET", path)).json();

export function problem(err) {
  return h("div", { class: "note error", role: "alert" }, h("b", {}, err.message), err.fix ? " " + err.fix : "");
}

export async function statusLine() {
  const box = document.getElementById("status");
  try {
    const s = await getJson("/settings");
    box.replaceChildren(...(s.configured
      ? [h("span", {}, h("b", {}, s.provider_label), " · " + s.model),
         h("span", { class: s.private ? "pill" : "pill shared" }, s.private ? "✔ Private: stays on this computer" : "Slides are sent to " + s.provider_label)]
      : [h("span", {}, "Not set up yet. "), h("a", { href: "/services" }, "Choose an AI service")]));
  } catch (err) {
    box.replaceChildren(problem(err));
  }
}

export function announce(text) {
  const live = document.getElementById("live");
  live.textContent = "";
  setTimeout(() => (live.textContent = text), 50);
}
export const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
