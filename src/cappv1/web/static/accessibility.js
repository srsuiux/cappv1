import { api, getJson, h, problem, announce } from "/app.js";

const $ = (id) => document.getElementById(id);

function render(data) {
  $("lengths").replaceChildren(...data.lengths.map((l) => h("div", { class: "opt-row" },
    h("label", { class: "opt" },
      h("input", { type: "radio", name: "length", value: l.id, checked: l.id === data.alt_text_length }),
      h("span", {}, h("b", {}, l.label), h("small", {}, l.help))))));
}

async function save() {
  $("result").replaceChildren();
  $("save").disabled = true;
  try {
    const length = document.querySelector("input[name=length]:checked").value;
    const saved = await (await api("PUT", "/settings/accessibility", { alt_text_length: length })).json();
    const msg = `Alt text length: ${saved.alt_text_length}`;
    $("result").replaceChildren(h("div", { class: "note good", role: "status" }, h("b", {}, msg + ". "), h("a", { href: "/files" }, "Go to Files")));
    announce(msg);
  } catch (err) {
    $("result").replaceChildren(problem(err));
  } finally {
    $("save").disabled = false;
  }
}

try {
  render(await getJson("/settings/accessibility"));
} catch (err) {
  $("problem").replaceChildren(problem(err));
}
$("form").addEventListener("submit", (e) => { e.preventDefault(); save(); });
