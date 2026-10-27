import { api, getJson, h, problem, statusLine, announce, plural, ApiError } from "./app.js";

const $ = (id) => document.getElementById(id);
const STATE = {
  new: ["New", ""], partial: ["Unfinished, will continue", "warn"], changed: ["Edited since last run", "warn"], done: ["✔ Done", "ok"],
};
let files = [];
let busy = false;

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

function render() {
  $("empty").hidden = files.length > 0;
  $("files").replaceChildren(...files.map((f) => {
    const [label, tone] = STATE[f.state] || [f.state, ""];
    return h("li", {},
      h("span", {}, h("span", { class: "name" }, f.name), h("br"), h("span", { class: "muted" }, mb(f.size))),
      h("span", { class: "state" },
        h("span", { class: tone }, label), " ",
        f.has_output ? h("button", { class: "quiet small", type: "button", onclick: () => download(f.name) }, "Download", h("span", { class: "sr" }, " " + f.name)) : null, " ",
        h("button", { class: "quiet small", type: "button", disabled: busy, onclick: () => remove(f.name) }, "Remove", h("span", { class: "sr" }, " " + f.name))));
  }));
  const force = $("force").checked;
  const n = force ? files.length : files.filter((f) => f.state !== "done").length;
  $("run").disabled = busy || n === 0;
  $("run").textContent = n === 0 ? "Write alt text" : `${force ? "Replace and write" : "Write"} alt text for ${plural(n, "file", "files")}`;
  $("runhelp").textContent = force
    ? "This replaces alt text people wrote, in the finished copies. Your originals are not changed."
    : "Slides already described are reused, not paid for twice.";
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

function watch(id) {
  busy = true;
  render();
  $("progress").hidden = false;
  $("stop").hidden = false;
  $("stop").disabled = false;
  $("feed").replaceChildren();
  $("ptitle").textContent = "Starting…";
  $("pdetail").textContent = "";
  setBar(0);
  let fileNo = 1, fileCount = 1, name = "";
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
  const where = (ev) => (fileCount > 1 ? `${ev.filename} · slide ${ev.slide + 1}` : `Slide ${ev.slide + 1}`);
  return stream(id, (ev) => {
    switch (ev.event) {
      case "file_start":
        fileNo = ev.index; fileCount = ev.total; name = ev.filename;
        $("ptitle").textContent = name;
        announce(`Starting ${name}, file ${fileNo} of ${fileCount}`);
        break;
      case "slide_end":
        $("ptitle").textContent = `${ev.filename} · slide ${ev.slide + 1} of ${ev.total}`;
        setBar(((fileNo - 1) + (ev.slide + 1) / ev.total) / fileCount * 100);
        break;
      case "alt_written": {
        const say = { captioned: [""], enhanced: ["Improved the text the author wrote"], kept: [""], cached: ["Reused from an earlier run"] }[ev.outcome];
        feed(where(ev), ev.outcome === "kept" ? "Kept the alt text you wrote." : clip(ev.text), say && say[0]);
        break;
      }
      case "file_saved":
        announce(ev.incomplete ? `${ev.filename} saved, some items could not be described` : `${ev.filename} finished`);
        break;
      case "file_failed":
        feed(ev.filename, ev.error, "Could not finish this file");
        announce(`${ev.filename} could not be finished`);
        break;
      case "run_finished": finish(ev.state); break;
    }
  });
}

function setBar(pct) {
  const p = Math.round(pct);
  $("fill").style.width = p + "%"; // allowed by the content policy: a CSSOM write, not inline markup
  document.querySelector("[role=progressbar]").setAttribute("aria-valuenow", p);
  $("pdetail").textContent = p + "%";
}

async function finish(state) {
  busy = false;
  $("stop").hidden = true;
  const failed = (await getJson("/runs/current")).failed_files || [];
  const text = {
    done: failed.length ? `Finished, but ${plural(failed.length, "file", "files")} could not be completed: ${failed.join(", ")}` : "Finished. Your files are ready to download.",
    cancelled: "Stopped. Finished slides are saved, and the next run continues from here.",
    failed: "The run stopped because of a problem. Open Doctor to see what to fix.",
  }[state] || "Finished.";
  $("ptitle").textContent = text;
  if (state === "done" && !failed.length) setBar(100);
  announce(text);
  await loadFiles();
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

statusLine();
await loadFiles();
try {
  const run = await getJson("/runs/current");
  if (run.state === "running") watch(run.id).catch(showProblem); // a run started elsewhere, e.g. in the terminal
} catch { /* the status line already explains */ }
