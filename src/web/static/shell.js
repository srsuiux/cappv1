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
