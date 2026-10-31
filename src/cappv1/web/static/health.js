import { getJson, h, problem, announce, plural } from "/app.js";

const $ = (id) => document.getElementById(id);

async function check() {
  $("again").disabled = true;
  $("problem").replaceChildren();
  $("summary").replaceChildren();
  $("checks").replaceChildren(h("li", {}, h("span", { "aria-hidden": "true" }, "…"), h("span", {}, "Checking…")));
  announce("Checking");
  try {
    const { checks, ok } = await getJson("/doctor");
    $("checks").replaceChildren(...checks.map((c) => h("li", {},
      h("span", { class: c.ok ? "ok" : "bad", "aria-hidden": "true" }, c.ok ? "✔" : "✖"),
      h("span", {}, h("b", {}, c.label), h("span", { class: "sr" }, c.ok ? ": passed" : ": needs fixing")),
      c.detail ? h("small", {}, c.detail) : null)));
    const bad = checks.filter((c) => !c.ok).length;
    const text = ok ? "Everything is working." : `${plural(bad, "thing needs", "things need")} fixing.`;
    $("summary").replaceChildren(h("div", { class: ok ? "note good" : "note", role: "status" }, h("b", {}, text),
      ok ? " You're ready to add files." : " Follow the line under each one, then check again."));
    announce(text);
  } catch (err) {
    $("checks").replaceChildren();
    $("problem").replaceChildren(problem(err));
  } finally {
    $("again").disabled = false;
  }
}

$("again").addEventListener("click", check);
await check();
