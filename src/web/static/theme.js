// Loaded in <head>, before the page paints: applies the chosen theme and the remembered "in use" state.
try {
  const theme = localStorage.getItem("cappv1.theme");
  if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
  if (localStorage.getItem("cappv1.used") === "1") document.documentElement.dataset.used = "1";
} catch { /* storage blocked: the device setting and the first-visit layout apply */ }
