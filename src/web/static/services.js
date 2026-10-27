import { api, getJson, h, problem, statusLine, announce } from "/app.js";

const $ = (id) => document.getElementById(id);
const OTHER = "__other";
let services = [], current = null, loadId = 0;

const label = (m) => [m.id, m.note, m.price_text].filter(Boolean).join(" · ");
const option = (m) => h("option", { value: m.id }, label(m));

function modelOptions(id, data) {
  if (data.free || data.cheapest) {
    const groups = [["Free (shared servers, may log your slides)", data.free], ["Cheapest paid", data.cheapest],
      ...Object.entries(data.makers || {}).map(([maker, items]) => [maker, items])];
    return groups.filter(([, items]) => items && items.length).map(([name, items]) => h("optgroup", { label: name }, ...items.map(option)));
  }
  return (data.models || []).map(option);
}

async function loadModels(id) {
  const mine = ++loadId, select = $("model");
  select.replaceChildren(h("option", { value: "" }, "Loading models…"));
  $("save").disabled = true;
  let opts = [];
  try {
    $("problem").replaceChildren();
    opts = modelOptions(id, await getJson(`/services/${id}/models`));
  } catch (err) {
    if (mine === loadId) $("problem").replaceChildren(problem(err));
  }
  if (mine !== loadId) return;
  select.replaceChildren(...opts, h("option", { value: OTHER }, "Another model (type its name)"));
  const svc = services.find((s) => s.id === id);
  const want = svc.model || (current && current.provider === id ? current.model : "");
  const known = [...select.querySelectorAll("option")].some((o) => o.value === want);
  select.value = want && known ? want : opts.length ? select.querySelector("option").value : OTHER;
  if (want && !known) { select.value = OTHER; $("othername").value = want; }
  syncOther();
  $("save").disabled = false;
}

function syncOther() { $("other").hidden = $("model").value !== OTHER; }

function chosenService() { return document.querySelector("input[name=service]:checked").value; }

function syncKey() {
  const svc = services.find((s) => s.id === chosenService());
  $("keybox").hidden = !svc.needs_key;
  $("keyhelp").textContent = svc.key_saved
    ? "A key is saved. Leave this empty to keep using it, or paste a new one to replace it."
    : `Get a key at ${svc.key_help}. It is saved on this computer only and never shown again.`;
  $("key").value = "";
}

function renderServices() {
  $("services").replaceChildren(...services.map((s) => h("div", { class: "opt-row" },
    h("label", { class: "opt" },
      h("input", { type: "radio", name: "service", value: s.id, checked: s.id === (current.provider || services[0].id) }),
      h("span", {}, h("b", {}, s.label), h("small", {}, s.note + (s.needs_key ? (s.key_saved ? ", key saved" : ", no key yet") : "")), h("small", {}, s.handling))),
    h("div", { class: "side-actions" },
      s.policy_url ? h("a", { href: s.policy_url, target: "_blank", rel: "noopener noreferrer" }, "Their privacy policy", h("span", { class: "sr" }, " (opens in a new tab)")) : null,
      s.key_saved ? h("button", { type: "button", class: "quiet small", onclick: () => forget(s) }, "Remove saved key", h("span", { class: "sr" }, " for " + s.label)) : null))));
  for (const r of document.querySelectorAll("input[name=service]")) r.addEventListener("change", () => { syncKey(); loadModels(r.value); });
}

async function forget(svc) {
  $("result").replaceChildren();
  try {
    await api("DELETE", `/settings/keys/${svc.id}`);
    services = (await getJson("/services")).services;
    current = await getJson("/settings");
    renderServices();
    syncKey();
    announce(`${svc.label} key removed`);
    $("result").replaceChildren(h("div", { class: "note good", role: "status" }, h("b", {}, `${svc.label} key removed from this computer.`)));
    statusLine();
  } catch (err) { $("result").replaceChildren(problem(err)); }
}

async function save(anyway = false) {
  const provider = chosenService();
  const model = $("model").value === OTHER ? $("othername").value.trim() : $("model").value;
  const key = $("key").value.trim();
  const result = $("result");
  result.replaceChildren();
  if (!model) { result.replaceChildren(problem({ message: "Pick a model first.", fix: "" })); return; }
  $("save").disabled = true;
  try {
    if (key && !anyway) {
      const check = await (await api("POST", "/settings/test", { provider, api_key: key })).json();
      if (!check.ok) {
        result.replaceChildren(h("div", { class: "note error", role: "alert" }, h("b", {}, "That key wasn't accepted. "), check.detail || "",
          h("div", { class: "actions" },
            h("button", { type: "button", class: "quiet", onclick: () => save(true) }, "Save it anyway"),
            h("button", { type: "button", class: "quiet", onclick: () => $("key").focus() }, "Try another key"))));
        return;
      }
    }
    const saved = await (await api("PUT", "/settings", { provider, model, api_key: key || undefined })).json();
    current = saved;
    services = (await getJson("/services")).services;
    syncKey();
    const msg = `Now using ${saved.provider_label} · ${saved.model}`;
    result.replaceChildren(h("div", { class: "note good", role: "status" }, h("b", {}, msg + ". "), h("a", { href: "/files" }, "Go to Files")));
    announce(msg);
    statusLine();
  } catch (err) {
    result.replaceChildren(problem(err));
  } finally {
    $("save").disabled = false;
  }
}

try {
  [services, current] = [(await getJson("/services")).services, await getJson("/settings")];
  renderServices();
  syncKey();
  await loadModels(chosenService());
} catch (err) {
  $("problem").replaceChildren(problem(err));
}
$("model").addEventListener("change", syncOther);
$("form").addEventListener("submit", (e) => { e.preventDefault(); save(); });
