// Theme and accent color: System follows the device; the choices are remembered in this browser (theme.js applies them on every page).
const root = document.documentElement;
const say = (text) => { document.getElementById("live").textContent = text; };

function wire(selector, attr, key, fallback, label) {
  const buttons = [...document.querySelectorAll(selector)];
  const mark = () => {
    const chosen = root.dataset[attr] || fallback;
    for (const b of buttons) b.setAttribute("aria-pressed", String(b.dataset[attr + "Set"] === chosen));
  };
  for (const b of buttons) {
    b.addEventListener("click", () => {
      const value = b.dataset[attr + "Set"];
      if (value === fallback) delete root.dataset[attr]; else root.dataset[attr] = value;
      try { value === fallback ? localStorage.removeItem(key) : localStorage.setItem(key, value); } catch { /* not remembered */ }
      mark();
      say(`${label}: ${b.textContent.trim()}`);
    });
  }
  mark();
}
wire("[data-theme-set]", "theme", "cappv1.theme", "system", "Theme");
wire("[data-accent-set]", "accent", "cappv1.accent", "blue", "Accent color");
