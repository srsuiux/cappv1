import { api, getJson, h, problem, announce, plural, ApiError } from "/app.js";

const $ = (id) => document.getElementById(id);
const rmBtn = document.getElementById("rm"); // kept by reference: "Remove all" swaps it out and back
const STATE = {
  new: ["New", ""], partial: ["Unfinished, will continue", "warn"], changed: ["Edited since last run", "warn"], done: ["✔ Done", "ok"],
};
let files = [];
let busy = false;
const fresh = new Set(); // finished in the latest run
const selected = new Set(); // names ticked for the next run
const known = new Set(); // names already seen, so only new arrivals are ticked automatically
const session = new Set(); // added or run on this page, so they stay under Current files

const isWord = (name) => name.toLowerCase().endsWith(".docx");
const KIND_LABEL = { slides: "PowerPoint deck", document: "Word document" };
const kindOf = (name) => (isWord(name) ? "document" : "slides");
// "deck" / "document" / "file" for a set of file names
const noun = (names, n = 1) => {
  const kinds = new Set(names.map(kindOf));
  const w = kinds.size > 1 ? ["file", "files"] : kinds.has("document") ? ["document", "documents"] : ["deck", "decks"];
  return n === 1 ? w[0] : w[1];
};

function showProblem(err) {
  $("problem").replaceChildren(err ? problem(err) : "");
  if (err) $("problem").scrollIntoView({ block: "center" }); // the page can be long: an error up top must not go unseen
}
const mb = (n) => (n / 1048576 >= 0.1 ? (n / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " KB");

const when = (secs) => new Date(secs * 1000).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
// A run folder is named for the local time it started: 2026-10-29_21-28-38
const runLabel = (run) => {
  const m = run.match(/^(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})-(\d{2})/);
  return m ? new Date(+m[1], m[2] - 1, +m[3], +m[4], +m[5], +m[6]).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "Made by an earlier version";
};
const runKey = (run) => run || "earlier"; // the API's name for loose copies from older versions

async function download(name, run) {
  try {
    const path = run === undefined ? `/files/${encodeURIComponent(name)}/download` : `/history/${encodeURIComponent(runKey(run))}/${encodeURIComponent(name)}/download`;
    const blob = await (await api("GET", path)).blob();
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
    selected.delete(name);
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

// The ? on a card: what could not be read, shown on hover, focus or tap so the card stays clean
let tips = 0;
function tip(f) {
  const list = f.skipped, id = "tip-" + ++tips;
  const btn = h("button", {
    type: "button", "aria-expanded": "false", "aria-describedby": id, title: "Processing notes",
    "aria-label": `Processing notes for ${f.name}`,
    onclick: () => btn.setAttribute("aria-expanded", String(btn.getAttribute("aria-expanded") !== "true")),
  }, "?");
  const box = h("span", { class: "tipbox", role: "tooltip", id },
    h("p", {}, h("b", {}, `${plural(list.length, "item was", "items were")} skipped.`), ` Check ${list.length === 1 ? "it" : "them"} in the original:`),
    h("ul", {}, ...list.slice(0, 10).map((s) => h("li", {}, `${s.where}, ${s.kind}: ${s.error}`)),
      list.length > 10 ? h("li", {}, `and ${list.length - 10} more (see the run log)`) : null));
  return h("span", { class: "tip" }, btn, box);
}
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  for (const b of document.querySelectorAll(".tip>button[aria-expanded=true]")) { b.setAttribute("aria-expanded", "false"); b.focus(); }
});
document.addEventListener("click", (e) => {
  for (const b of document.querySelectorAll(".tip>button[aria-expanded=true]")) if (!b.parentElement.contains(e.target)) b.setAttribute("aria-expanded", "false");
});

function row(f) {
  const [label, tone] = STATE[f.state] || [f.state, ""];
  const ready = fresh.has(f.name);
  return h("li", { class: ready ? "fresh" : "" },
    h("label", { class: "pick" }, h("input", {
      type: "checkbox", checked: selected.has(f.name), disabled: busy, "aria-label": "Select " + f.name,
      onchange: (e) => { e.target.checked ? selected.add(f.name) : selected.delete(f.name); summary(); },
    })),
    h("span", {}, h("span", { class: "card-top" }, h("span", { class: "name" }, f.name), f.skipped && f.skipped.length ? tip(f) : null),
      h("span", { class: "meta" }, h("span", {}, KIND_LABEL[kindOf(f.name)]), h("span", {}, mb(f.size)), f.modified ? h("span", {}, "Added " + when(f.modified)) : null,
        f.has_output ? h("span", {}, `Latest copy ${mb(f.output_size)}, ${when(f.output_modified)}`) : null)),
    h("span", { class: "card-act" },
      h("span", { class: "state " + (ready ? "ok" : tone) }, ready ? "✔ Finished copy ready" : label),
      !isWord(f.name) ? h("button", { class: "quiet small", type: "button", disabled: busy, onclick: () => audit(f.name) }, "Check accessibility", h("span", { class: "sr" }, " " + f.name)) : null,
      f.has_output ? h("button", { class: "quiet small", type: "button", onclick: () => download(f.name) }, "Download", h("span", { class: "sr" }, " " + f.name)) : null,
      h("button", { class: "quiet small", type: "button", disabled: busy, onclick: () => remove(f.name) }, "Remove", h("span", { class: "sr" }, " " + f.name))));
}

// ---- finished copies, one group per run ----------------------------------------
// Deleting a finished copy cannot be undone, so the button turns into a question first.
function confirmDelete(btn, what, action) {
  const cancel = h("button", { class: "quiet small", type: "button" }, "Cancel");
  const yes = h("button", { class: "danger small", type: "button", onclick: async () => {
    try { await action(); announce(`${what} deleted`); } catch (err) { showProblem(err); }
    await loadFiles();
  } }, "Yes, delete");
  const box = h("span", { class: "confirm", role: "group", "aria-label": `Confirm deleting ${what}` }, h("span", {}, "Delete? No undo."), yes, cancel);
  cancel.addEventListener("click", () => { box.replaceWith(btn); btn.focus(); });
  btn.replaceWith(box);
  cancel.focus();
}

const deleteCopy = (run, name) => api("DELETE", `/history/${encodeURIComponent(runKey(run))}` + (name ? `/${encodeURIComponent(name)}` : ""));

function renderHistory(runs) {
  $("hist").replaceChildren(...(runs.length ? runs.map((r) => {
    const del = h("button", { class: "quiet small", type: "button", disabled: busy, onclick: () => confirmDelete(del, "this run's finished copies", () => deleteCopy(r.run)) }, "Delete run", h("span", { class: "sr" }, " " + runLabel(r.run)));
    return h("li", {},
      h("div", { class: "runhead" }, h("span", {}, h("b", {}, runLabel(r.run)), h("span", { class: "meta" }, h("span", {}, plural(r.files.length, "file", "files")), h("span", {}, mb(r.bytes)), r.legacy ? null : h("span", {}, r.run))), del),
      h("ul", { class: "runfiles" }, ...r.files.map((f) => {
        const rm = h("button", { class: "quiet small", type: "button", disabled: busy, onclick: () => confirmDelete(rm, f.name, () => deleteCopy(r.run, f.name)) }, "Delete", h("span", { class: "sr" }, " " + f.name));
        return h("li", {}, h("span", { class: "name" }, f.name, h("span", { class: "meta" }, h("span", {}, mb(f.size)), h("span", {}, when(f.modified)))),
          h("span", { class: "card-act" }, h("button", { class: "quiet small", type: "button", onclick: () => download(f.name, r.run) }, "Download", h("span", { class: "sr" }, " " + f.name)), rm));
      })));
  }) : [h("li", { class: "muted" }, "No finished copies yet. They appear here after a run.")]));
}

const split = () => {
  // Current: waiting to be done, or touched on this page. Previous: finished earlier.
  const current = files.filter((f) => f.state !== "done" || session.has(f.name));
  return { current, previous: files.filter((f) => !current.includes(f)) };
};

function render() {
  const { current, previous } = split();
  $("empty").hidden = current.length > 0;
  $("files").replaceChildren(...current.map(row));
  $("prevwrap").hidden = previous.length === 0;
  $("prev").replaceChildren(...previous.map(row));
  summary();
}

// Everything that depends on what is ticked: the toolbar, the run button and its help.
function summary() {
  const { current } = split();
  const force = $("force").checked;
  const picked = files.filter((f) => selected.has(f.name));
  const inCurrent = current.filter((f) => selected.has(f.name)).length;
  $("tools").hidden = current.length === 0;
  $("all").checked = current.length > 0 && inCurrent === current.length;
  $("all").indeterminate = inCurrent > 0 && inCurrent < current.length;
  $("all").disabled = busy;
  $("picked").textContent = `${inCurrent} of ${current.length} selected`;
  if (!$("removeall").querySelector("#confirm")) rmBtn.disabled = busy;
  const todo = picked.filter((f) => force || f.state !== "done");
  const n = todo.length;
  $("run").disabled = busy || n === 0;
  $("run").textContent = n === 0 ? "Improve accessibility" : `${force ? "Replace and improve" : "Improve"} accessibility for ${plural(n, "selected file", "selected files")}`;
  $("runhelp").textContent = n === 0
    ? (picked.length ? "The selected files are already done. Tick the replace option to redo them." : "Tick the files you want to improve.")
    : force
      ? "This replaces alt text people wrote, in the finished copies, for the selected files. Your originals are not changed."
      : "Items already described are reused, not paid for twice.";
}

// "Remove all" empties the Current files list. It asks first, in place, and only touches the copies cappv1 holds.
function askRemoveAll() {
  const { current } = split();
  const box = $("removeall");
  const cancel = h("button", { class: "quiet small", type: "button", onclick: () => resetRemove() }, "Cancel");
  box.replaceChildren(
    h("span", { id: "confirm", role: "group", "aria-label": "Confirm removing all" }, `Remove ${plural(current.length, "file", "files")} from this list? Your originals aren't affected. `),
    h("button", { class: "danger small", type: "button", onclick: () => removeAll(current.map((f) => f.name)) }, "Yes, remove"), cancel);
  cancel.focus();
}
function resetRemove() {
  $("removeall").replaceChildren(rmBtn);
  rmBtn.disabled = busy;
  rmBtn.focus();
}
async function removeAll(names) {
  let gone = 0;
  try {
    for (const name of names) { await api("DELETE", `/files/${encodeURIComponent(name)}`); selected.delete(name); gone++; }
  } catch (err) { showProblem(err); }
  announce(`${plural(gone, "file", "files")} removed`);
  $("removeall").replaceChildren(rmBtn);
  await loadFiles();
  $("pick").focus();
}

async function loadFiles() {
  try {
    files = (await getJson("/files")).files;
    showProblem(null);
    const names = new Set(files.map((f) => f.name));
    for (const n of [...selected]) if (!names.has(n)) selected.delete(n);
    for (const f of files) if (!known.has(f.name)) { known.add(f.name); if (f.state !== "done") selected.add(f.name); } // new arrivals are ticked
    renderHistory((await getJson("/history")).runs);
  } catch (err) { showProblem(err); }
  render();
}

async function upload(list) {
  const picked = [...list];
  for (const file of picked) {
    announce(`Adding ${file.name}`);
    try {
      await api("PUT", `/files/${encodeURIComponent(file.name)}`, file, true);
    } catch (err) { showProblem(new ApiError({ code: err.code, message: `${file.name}: ${err.message}`, fix: err.fix })); continue; }
    session.add(file.name);
    selected.add(file.name);
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
  skippedTiles.clear();
  $("deck").classList.toggle("items", kind === "document");
  $("deck").replaceChildren(...tiles);
}
const skippedTiles = new Set(); // slides that had something it could not read
function mark(i, state) {
  const t = tiles[i];
  if (t) t.className = "tile " + (state === "done" && skippedTiles.has(i) ? "skip" : state);
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
  const saved = [], tally = { written: 0, kept: 0, skipped: 0 };
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
        session.add(name);
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
      case "element_skipped":
        tally.skipped++;
        if (kind === "slides") skippedTiles.add(ev.slide);
        feed(where(ev), `${ev.kind}: ${ev.error}`, "Skipped, and noted so you can check it later");
        announce(`Skipped a ${ev.kind} on ${ev.where}`);
        break;
      case "file_saving":
        $("now").textContent = "Saving the finished copy…";
        break;
      case "file_saved":
        saved.push({ name: ev.filename, path: ev.path, incomplete: ev.incomplete, kind, skipped: ev.skipped || 0 });
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
    tally.skipped ? h("p", { class: "note" }, `${plural(tally.skipped, "item", "items")} could not be read and ${tally.skipped === 1 ? "was" : "were"} skipped, so the rest could finish. The list below says which, so you can check ${tally.skipped === 1 ? "it" : "them"} in the original.`) : null,
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
  $("done").replaceChildren(...(ok ? doneList(saved, tally).filter(Boolean) : []));
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
  const names = files.filter((f) => selected.has(f.name) && (force || f.state !== "done")).map((f) => f.name);
  try {
    const run = await (await api("POST", "/runs", { force, confirm: force, files: names })).json();
    await watch(run.id);
  } catch (err) { busy = false; showProblem(err); render(); }
}

// ---- wiring --------------------------------------------------------------------
$("pick").addEventListener("change", (e) => { upload(e.target.files); e.target.value = ""; });
const drop = $("drop");
for (const t of ["dragenter", "dragover"]) drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.add("over"); });
for (const t of ["dragleave", "drop"]) drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.remove("over"); });
drop.addEventListener("drop", (e) => upload(e.dataTransfer.files));
$("force").addEventListener("change", summary);
$("all").addEventListener("change", () => {
  const { current } = split();
  for (const f of current) $("all").checked ? selected.add(f.name) : selected.delete(f.name);
  render();
  $("all").focus();
});
rmBtn.addEventListener("click", askRemoveAll);
$("run").addEventListener("click", start);
$("dismiss").addEventListener("click", () => { $("stage").hidden = true; fresh.clear(); render(); $("pick").focus(); });
// the terminal can add, remove and delete too: look again when this window is back in front
addEventListener("focus", () => { if (!busy) loadFiles(); });
$("aclose").addEventListener("click", () => { $("audit").hidden = true; $("pick").focus(); });

await loadFiles();
try {
  const run = await getJson("/runs/current");
  if (run.state === "running") watch(run.id).catch(showProblem); // a run started elsewhere, e.g. in the terminal
} catch { /* the status line already explains */ }
