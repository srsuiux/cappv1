import { api, getJson, h, problem, announce, plural, ApiError } from "/app.js";

const $ = (id) => document.getElementById(id);
const STATE = {
  new: ["New", ""], partial: ["Unfinished, will continue", "warn"], changed: ["Edited since last run", "warn"], done: ["✔ Done", "ok"],
};
let files = [];
let busy = false;
const fresh = new Set(); // finished in the latest run

const isWord = (name) => name.toLowerCase().endsWith(".docx");
const KIND_LABEL = { slides: "PowerPoint deck", document: "Word document" };
const kindOf = (name) => (isWord(name) ? "document" : "slides");
// "deck" / "document" / "file" for a set of file names
const noun = (names, n = 1) => {
  const kinds = new Set(names.map(kindOf));
  const w = kinds.size > 1 ? ["file", "files"] : kinds.has("document") ? ["document", "documents"] : ["deck", "decks"];
  return n === 1 ? w[0] : w[1];
};

function showProblem(err) { $("problem").replaceChildren(err ? problem(err) : ""); }
const mb = (n) => (n / 1048576 >= 0.1 ? (n / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " KB");

async function download(name) {
  try {
    const blob = await (await api("GET", `/files/${encodeURIComponent(name)}/download`)).blob();
    const a = h("a", { href: URL.createObjectURL(blob), download: name });
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 10000);
  } catch (err) { showProblem(err); }
}

async function remove(name) {
  try {
    await api("DELETE", `/files/${encodeURIComponent(name)}`);
    announce(`${name} removed`);
    await loadFiles();
  } catch (err) { showProblem(err); }
}

const KIND = { contrast: "Hard to read", reading_order: "Reading order" };
const slideList = (n) => n.slice(0, 15).join(", ") + (n.length > 15 ? ` and ${n.length - 15} more` : "");

async function audit(name) {
  showProblem(null);
  announce(`Checking ${name}`);
  try {
    const r = await getJson(`/files/${encodeURIComponent(name)}/audit`);
    $("atitle").textContent = `Accessibility check: ${r.file}`;
    $("ascope").textContent = `Checked the ${r.checked}. This looks at text contrast and reading order only; Blackboard and PowerPoint may check more.`;
    const found = r.groups.length
      ? h("ul", { class: "feed" }, ...r.groups.map((g) => h("li", {}, h("b", {}, KIND[g.kind] || g.kind), h("span", {}, g.message), h("small", {}, g.detail), h("small", {}, "Slides: " + slideList(g.slides)))))
      : h("p", { class: "note good" }, "✔ No contrast or reading-order problems found.");
    $("aresult").replaceChildren(found, r.unmeasured_text ? h("p", { class: "muted" }, `${plural(r.unmeasured_text, "piece", "pieces")} of text sat on a picture or an unusual color and could not be judged.`) : "");
    $("audit").hidden = false;
    announce(r.groups.length ? `${plural(r.groups.length, "problem", "problems")} found` : "No problems found");
    $("audit").focus();
  } catch (err) { showProblem(err); }
}

function render() {
  $("empty").hidden = files.length > 0;
  $("files").replaceChildren(...files.map((f) => {
    const [label, tone] = STATE[f.state] || [f.state, ""];
    const ready = fresh.has(f.name);
    return h("li", { class: ready ? "fresh" : "" },
      h("span", {}, h("span", { class: "name" }, f.name), h("br"), h("span", { class: "muted" }, `${KIND_LABEL[kindOf(f.name)]} · ${mb(f.size)}`),
        isWord(f.name) ? h("span", { class: "muted" }, " · pictures and tables") : null),
      h("span", { class: "state" },
        h("span", { class: ready ? "ok" : tone }, ready ? "✔ Finished copy ready" : label), " ",
        !isWord(f.name) ? h("button", { class: "quiet small", type: "button", disabled: busy, onclick: () => audit(f.name) }, "Check accessibility", h("span", { class: "sr" }, " " + f.name)) : null, " ",
        f.has_output ? h("button", { class: "quiet small", type: "button", onclick: () => download(f.name) }, "Download", h("span", { class: "sr" }, " " + f.name)) : null, " ",
        h("button", { class: "quiet small", type: "button", disabled: busy, onclick: () => remove(f.name) }, "Remove", h("span", { class: "sr" }, " " + f.name))));
  }));
  const force = $("force").checked;
  const n = force ? files.length : files.filter((f) => f.state !== "done").length;
  $("run").disabled = busy || n === 0;
  $("run").textContent = n === 0 ? "Write alt text" : `${force ? "Replace and write" : "Write"} alt text for ${plural(n, "file", "files")}`;
  $("runhelp").textContent = force
    ? "This replaces alt text people wrote, in the finished copies. Your originals are not changed."
    : "Items already described are reused, not paid for twice.";
}

async function loadFiles() {
  try { files = (await getJson("/files")).files; showProblem(null); } catch (err) { showProblem(err); }
  render();
}

async function upload(list) {
  const picked = [...list];
  for (const file of picked) {
    announce(`Adding ${file.name}`);
    try {
      await api("PUT", `/files/${encodeURIComponent(file.name)}`, file, true);
    } catch (err) { showProblem(new ApiError({ code: err.code, message: `${file.name}: ${err.message}`, fix: err.fix })); continue; }
    announce(`${file.name} added`);
  }
  await loadFiles();
}

// ---- a run -------------------------------------------------------------------
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function stream(id, onEvent) {
  let last = 0, failures = 0;
  while (failures < 30) {
    try {
      const res = await api("GET", `/runs/${id}/events?after=${last}`);
      failures = 0;
      const reader = res.body.getReader(), decoder = new TextDecoder();
      let buf = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        for (let i; (i = buf.indexOf("\n\n")) >= 0;) {
          const line = buf.slice(0, i).split("\n").find((l) => l.startsWith("data: "));
          buf = buf.slice(i + 2);
          if (!line) continue;
          const ev = JSON.parse(line.slice(6));
          last = ev.id;
          onEvent(ev);
          if (ev.event === "run_finished") return;
        }
      }
    } catch (err) {
      if (err.code && err.code !== "offline") throw err;
      failures++;
    }
    await sleep(1000);
  }
  throw new ApiError({ code: "offline", message: "Lost touch with cappv1.", fix: "Check that it is still running, then reload this page." });
}

const clip = (t) => (t.length > 280 ? t.slice(0, 277) + "…" : t);
const VERB = { picture: "Looking at a picture", table: "Reading a table", chart: "Reading a chart", object: "Reading an embedded object", diagram: "Reading a diagram" };
let tiles = [];

let kind = "slides", items = { total: 0, done: 0 };

// A deck is a row of numbered slides. A Word document has no slides, so it gets
// one chip per picture or table instead, filled in as each is described.
function buildDeck(total) {
  tiles = Array.from({ length: total }, (_, i) => h("span", { class: "tile" }, String(i + 1)));
  $("deck").classList.toggle("items", kind === "document");
  $("deck").replaceChildren(...tiles);
}
function mark(i, state) {
  const t = tiles[i];
  if (t) t.className = "tile " + state;
}

function watch(id) {
  busy = true;
  fresh.clear();
  render();
  const stage = $("stage");
  stage.dataset.phase = "working";
  stage.hidden = false;
  $("done").hidden = true;
  $("dismiss").hidden = true;
  $("stop").hidden = false;
  $("stop").disabled = false;
  $("deck").hidden = false;
  kind = "slides";
  $("feed").replaceChildren();
  $("ptitle").textContent = "Starting…";
  $("pcopy").textContent = "cappv1 is adding alt text to a copy of your document. Your original isn't changed, and the finished copy appears right here.";
  $("pdetail").textContent = "";
  $("now").textContent = "";
  setBar(0);
  stage.scrollIntoView({ block: "start" });
  stage.focus({ preventScroll: true });
  let fileNo = 1, fileCount = 1, name = "";
  const saved = [], tally = { written: 0, kept: 0 };
  $("stop").onclick = async () => {
    $("stop").disabled = true;
    announce("Stopping after this slide");
    try { await api("POST", `/runs/${id}/cancel`); } catch (err) { showProblem(err); }
  };
  const feed = (title, text, note) => {
    const li = h("li", {}, h("b", {}, title), note ? h("small", {}, note) : null, h("span", {}, text));
    $("feed").prepend(li);
    while ($("feed").children.length > 200) $("feed").lastChild.remove();
  };
  const where = (ev) => {
    const spot = kind === "document" ? `Item ${items.done}` : `Slide ${ev.slide + 1}`;
    return fileCount > 1 ? `${ev.filename} · ${spot.toLowerCase()}` : spot;
  };
  const stopLabel = () => (kind === "document" ? "Stop (finished captions are kept)" : "Stop after this slide");
  return stream(id, (ev) => {
    switch (ev.event) {
      case "file_start":
        fileNo = ev.index; fileCount = ev.total; name = ev.filename;
        kind = ev.kind || kindOf(name);
        items = { total: 0, done: 0 };
        $("stop").textContent = stopLabel();
        $("pcopy").textContent = kind === "document"
          ? "cappv1 is adding alt text to a copy of your Word document. Your original isn't changed, and the finished copy appears right here."
          : "cappv1 is adding alt text to a copy of your deck. Your original isn't changed, and the finished copy appears right here.";
        $("ptitle").textContent = fileCount > 1 ? `Working on ${name} (file ${fileNo} of ${fileCount})` : `Working on ${name}`;
        announce(`Starting ${name}, file ${fileNo} of ${fileCount}`);
        break;
      case "file_open":
        kind = ev.kind || kind;
        items = { total: ev.items || 0, done: 0 };
        buildDeck(kind === "document" ? items.total : ev.total_slides);
        $("deck").hidden = !tiles.length;
        if (kind === "slides") for (let i = 0; i < ev.resumed; i++) mark(i, "done");
        break;
      case "slide_start": {
        if (kind === "document") {
          const c = ev.counts || {}, bits = [["picture", "picture"], ["table", "table"]].filter(([k]) => c[k]).map(([k, w]) => plural(c[k], w, w + "s"));
          $("now").textContent = bits.length ? `In this document: ${bits.join(", ")}` : "This document has no pictures or tables to describe";
          $("pdetail").textContent = items.total ? `0 of ${plural(items.total, "item", "items")} described` : "";
          break;
        }
        mark(ev.slide, "now");
        const c = ev.counts || {}, bits = [["picture", "picture"], ["table", "table"], ["chart", "chart"], ["object", "object"], ["diagram", "diagram"]]
          .filter(([k]) => c[k]).map(([k, w]) => plural(c[k], w, w + "s"));
        $("now").textContent = bits.length ? `Slide ${ev.slide + 1}: ${bits.join(", ")}` : `Slide ${ev.slide + 1}: nothing to describe`;
        break;
      }
      case "element_start":
        $("now").textContent = kind === "document" ? `${VERB[ev.kind] || "Working on an item"}…` : `Slide ${ev.slide + 1}: ${VERB[ev.kind] || "Working on an item"}…`;
        break;
      case "slide_end":
        if (kind === "document") {
          tiles.forEach((_, i) => mark(i, "done"));
          $("pdetail").textContent = items.total ? `${plural(items.done, "item", "items")} described${items.done < items.total ? `, ${items.total - items.done} left as they were` : ""}` : "";
          setBar(fileNo / fileCount * 100);
          break;
        }
        mark(ev.slide, "done");
        $("ptitle").textContent = fileCount > 1 ? `Working on ${ev.filename} (file ${fileNo} of ${fileCount})` : `Working on ${ev.filename}`;
        $("pdetail").textContent = `Slide ${ev.slide + 1} of ${ev.total}`;
        setBar(((fileNo - 1) + (ev.slide + 1) / ev.total) / fileCount * 100);
        break;
      case "alt_written": {
        const say = { captioned: [""], enhanced: ["Improved the text the author wrote"], kept: [""], cached: ["Reused from an earlier run"] }[ev.outcome];
        ev.outcome === "kept" ? tally.kept++ : tally.written++;
        if (kind === "document") {
          mark(items.done, "done");
          items.done++;
          $("pdetail").textContent = `${items.done} of ${plural(items.total, "item", "items")} described`;
          setBar(((fileNo - 1) + items.done / Math.max(items.total, 1)) / fileCount * 100);
        }
        feed(where(ev), ev.outcome === "kept" ? "Kept the alt text you wrote." : clip(ev.text), say && say[0]);
        break;
      }
      case "file_saving":
        $("now").textContent = "Saving the finished copy…";
        break;
      case "file_saved":
        saved.push({ name: ev.filename, path: ev.path, incomplete: ev.incomplete, kind });
        fresh.add(ev.filename);
        announce(ev.incomplete ? `${ev.filename} saved, some items could not be described` : `${ev.filename} finished`);
        break;
      case "file_failed":
        feed(ev.filename, ev.error, "Could not finish this file");
        announce(`${ev.filename} could not be finished`);
        break;
      case "run_finished": finish(ev.state, saved, tally); break;
    }
  });
}

function setBar(pct) {
  const p = Math.round(pct);
  $("fill").style.width = p + "%"; // allowed by the content policy: a CSSOM write, not inline markup
  document.querySelector("[role=progressbar]").setAttribute("aria-valuenow", p);
}

function doneList(saved, tally) {
  const one = saved.length === 1;
  return [
    h("p", {}, one
      ? `This is the same ${noun([saved[0].name])} as the one you added, with alt text now written into it. Your original, ${saved[0].name}, is unchanged.`
      : `These are the same ${noun(saved.map((f) => f.name), 2)} you added, with alt text now written into them. Your originals are unchanged.`),
    h("ul", { class: "ready" }, ...saved.map((f) => h("li", {},
      h("span", {}, h("b", {}, f.name), h("small", {}, f.incomplete ? "Finished copy ready. Some items couldn't be described, so run again to finish them." : "Finished copy ready"), h("small", { class: "path" }, "Saved on this computer: " + f.path)),
      h("span", { class: "row-actions" },
        h("button", { type: "button", onclick: () => download(f.name) }, "Download finished copy", h("span", { class: "sr" }, " " + f.name)),
        !isWord(f.name) ? h("button", { class: "quiet", type: "button", onclick: () => audit(f.name) }, "Check accessibility", h("span", { class: "sr" }, " " + f.name)) : null)))),
    h("p", { class: "muted" }, `${plural(tally.written, "description", "descriptions")} written` + (tally.kept ? `, ${tally.kept} kept as the author wrote them.` : ".") + " It's also in your list below, marked as ready."),
  ];
}

async function finish(state, saved, tally) {
  busy = false;
  const stage = $("stage");
  $("stop").hidden = true;
  $("dismiss").hidden = false;
  $("stop").textContent = "Stop after this slide";
  $("now").textContent = "";
  const failed = (await getJson("/runs/current")).failed_files || [];
  const ok = saved.length > 0;
  stage.dataset.phase = state === "done" && !failed.length ? "done" : state === "failed" ? "failed" : "stopped";
  const one = saved.length === 1;
  const title = {
    done: failed.length ? `${plural(saved.length, noun(saved.map((f) => f.name)), noun(saved.map((f) => f.name), 2))} finished, ${failed.length} could not be completed` : one ? `Your finished ${noun(saved.map((f) => f.name))} is ready` : `Your finished ${noun(saved.map((f) => f.name), 2)} are ready`,
    cancelled: ok ? "Stopped. Finished files are ready below" : "Stopped. Finished captions are saved",
    failed: "The run stopped because of a problem",
  }[state] || "Finished";
  $("ptitle").textContent = title;
  $("pcopy").textContent = {
    done: failed.length ? `Could not complete: ${failed.join(", ")}. Open Health to see what to fix.` : "",
    cancelled: "The next run continues from where this one stopped.",
    failed: "Open Health to see what to fix. Your files and progress are safe.",
  }[state] || "";
  $("pdetail").textContent = "";
  if (state === "done" && !failed.length) { setBar(100); tiles.forEach((_, i) => mark(i, "done")); }
  $("deck").hidden = !tiles.length || !ok && state === "failed";
  $("done").replaceChildren(...(ok ? doneList(saved, tally) : []));
  $("done").hidden = !ok;
  $("log").open = !ok;
  announce(title);
  await loadFiles();
  stage.scrollIntoView({ block: "start" });
  stage.focus({ preventScroll: true });
}

async function start() {
  showProblem(null);
  const force = $("force").checked;
  try {
    const run = await (await api("POST", "/runs", { force, confirm: force })).json();
    await watch(run.id);
  } catch (err) { busy = false; showProblem(err); render(); }
}

// ---- wiring --------------------------------------------------------------------
$("pick").addEventListener("change", (e) => { upload(e.target.files); e.target.value = ""; });
const drop = $("drop");
for (const t of ["dragenter", "dragover"]) drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.add("over"); });
for (const t of ["dragleave", "drop"]) drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.remove("over"); });
drop.addEventListener("drop", (e) => upload(e.dataTransfer.files));
$("force").addEventListener("change", render);
$("run").addEventListener("click", start);
$("dismiss").addEventListener("click", () => { $("stage").hidden = true; fresh.clear(); render(); $("pick").focus(); });
$("aclose").addEventListener("click", () => { $("audit").hidden = true; $("pick").focus(); });

await loadFiles();
try {
  const run = await getJson("/runs/current");
  if (run.state === "running") watch(run.id).catch(showProblem); // a run started elsewhere, e.g. in the terminal
} catch { /* the status line already explains */ }
