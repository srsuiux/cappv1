// Runs on every page: remembers the token, fills the status line, and folds the menu on small screens.
import { statusLine } from "/app.js";

if (document.getElementById("status")) statusLine();

const menu = document.getElementById("menu");
if (menu) {
  const wide = matchMedia("(min-width: 56rem)");
  const sync = () => { menu.open = wide.matches; };
  sync();
  wide.addEventListener("change", sync);
}

// Theme: System follows the device; Light and Dark are remembered in this browser.
const root = document.documentElement;
const buttons = [...document.querySelectorAll("[data-theme-set]")];
const setPressed = () => {
  const chosen = root.dataset.theme || "system";
  for (const b of buttons) b.setAttribute("aria-pressed", String(b.dataset.themeSet === chosen));
};
for (const b of buttons) {
  b.addEventListener("click", () => {
    const value = b.dataset.themeSet;
    if (value === "system") delete root.dataset.theme; else root.dataset.theme = value;
    try { value === "system" ? localStorage.removeItem("cappv1.theme") : localStorage.setItem("cappv1.theme", value); } catch { /* not remembered */ }
    setPressed();
    document.getElementById("live").textContent = `Theme: ${value}`;
    b.focus();
  });
}
setPressed();

// Accent color: the color of buttons and links. Remembered in this browser.
const accents = [...document.querySelectorAll("[data-accent-set]")];
const markAccent = () => {
  const chosen = root.dataset.accent || "blue";
  for (const b of accents) b.setAttribute("aria-pressed", String(b.dataset.accentSet === chosen));
};
for (const b of accents) {
  b.addEventListener("click", () => {
    const value = b.dataset.accentSet;
    if (value === "blue") delete root.dataset.accent; else root.dataset.accent = value;
    try { value === "blue" ? localStorage.removeItem("cappv1.accent") : localStorage.setItem("cappv1.accent", value); } catch { /* not remembered */ }
    markAccent();
    document.getElementById("live").textContent = `Accent color: ${b.title}`;
  });
}
markAccent();
