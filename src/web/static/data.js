import { api, getJson, h, problem, announce, plural } from "/app.js";

const $ = (id) => document.getElementById(id);
const size = (n) => (n >= 1048576 ? (n / 1048576).toFixed(1) + " MB" : n >= 1024 ? Math.round(n / 1024) + " KB" : n + " bytes");

async function load() {
  try {
    const { places, workspace } = await getJson("/storage");
    $("workspace").textContent = workspace;
    $("places").replaceChildren(...places.map((p) => h("li", {},
      h("b", {}, p.label),
      h("span", {}, p.what),
      h("br"),
      h("span", { class: "muted" }, `${plural(p.files, "file", "files")}, ${size(p.bytes)} · `), h("code", {}, p.path))));
  } catch (err) { $("problem").replaceChildren(problem(err)); }
}

$("sure").addEventListener("change", () => { $("erase").disabled = !$("sure").checked; });
$("erase").addEventListener("click", async () => {
  $("erase").disabled = true;
  try {
    const { erased } = await (await api("POST", "/storage/clear", { confirm: true })).json();
    const total = erased.input + erased.output + erased.progress + erased.logs;
    const msg = `Erased ${plural(total, "item", "items")}.`;
    $("result").replaceChildren(h("div", { class: "note good", role: "status" }, h("b", {}, msg)));
    announce(msg);
    $("sure").checked = false;
    await load();
  } catch (err) {
    $("result").replaceChildren(problem(err));
    $("erase").disabled = !$("sure").checked;
  }
});
await load();
