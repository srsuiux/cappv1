import { getJson, h, problem, plural } from "/app.js";

const $ = (id) => document.getElementById(id);
const fact = (box, label, value) => box.append(h("dt", {}, label), h("dd", {}, value));

async function load() {
  const [settings, services, files, run] = await Promise.all([
    getJson("/settings"), getJson("/services"), getJson("/files"), getJson("/runs/current")]);
  const list = files.files;
  const count = (state) => list.filter((f) => f.state === state).length;
  const waiting = list.filter((f) => f.state !== "done").length;

  // what to do next
  const next = $("next");
  let say, link;
  if (!settings.configured) { say = ["Choose an AI service", "cappv1 needs to know which one describes your slides."]; link = ["/services", "Choose a service"]; }
  else if (run.state === "running") { say = ["A run is in progress", "Open Files to watch it."]; link = ["/files", "Watch progress"]; }
  else if (!list.length) { say = ["Add your first deck", "Drop in a .pptx file and cappv1 writes the alt text."]; link = ["/files", "Add files"]; }
  else if (waiting) { say = [`${plural(waiting, "file is", "files are")} ready`, "Slides already described are reused, not paid for twice."]; link = ["/files", "Write alt text"]; }
  else { say = ["All your files are finished", "Download them from Files."]; link = ["/files", "Go to Files"]; }
  next.replaceChildren(h("p", {}, say[0], h("br"), h("span", { class: "muted" }, say[1])), h("a", { class: "btn", href: link[0] }, link[1]));

  // service
  const svc = services.services.find((s) => s.id === settings.provider);
  const box = $("service-facts");
  box.replaceChildren();
  if (!settings.configured) {
    fact(box, "Status", "Not set up yet");
  } else {
    fact(box, "Service", settings.provider_label);
    fact(box, "Model", settings.model);
    fact(box, "Where slides go", settings.private ? "Nowhere. Everything stays on this computer." : `To ${settings.provider_label}`);
    if (svc) fact(box, "API key", svc.needs_key ? (svc.key_saved ? "Saved" : "Missing") : "Not needed");
  }

  // files
  const fbox = $("file-facts");
  fbox.replaceChildren();
  fact(fbox, "In your list", String(list.length));
  fact(fbox, "Finished", String(count("done")));
  fact(fbox, "Waiting", String(count("new") + count("partial")));
  if (count("changed")) fact(fbox, "Edited since last run", String(count("changed")));
  const last = { done: "Finished", cancelled: "Stopped early", failed: "Stopped by a problem", running: "In progress" }[run.state];
  fact(fbox, "Last run", last ? last + (run.failed_files.length ? `, ${plural(run.failed_files.length, "file", "files")} not completed` : "") : "None since cappv1 started");
}

async function loadHealth() {
  try {
    const { checks, ok } = await getJson("/doctor");
    const bad = checks.filter((c) => !c.ok).length;
    $("health-line").textContent = ok ? "Everything is working." : `${plural(bad, "thing needs", "things need")} fixing.`;
    $("health-line").className = ok ? "ok" : "bad";
  } catch { $("health-line").textContent = "Couldn't run the checks."; }
}

async function loadData() {
  try {
    const { places } = await getJson("/storage");
    const slides = places.filter((p) => p.has_slides).reduce((n, p) => n + p.files, 0);
    $("data-line").textContent = slides
      ? `${plural(slides, "file", "files")} with slide content are kept in the folder cappv1 uses, on this computer only.`
      : "No slide content is kept right now.";
  } catch { $("data-line").textContent = ""; }
}

try { await load(); } catch (err) { $("problem").replaceChildren(problem(err)); $("next").hidden = true; }
loadHealth();
loadData();
