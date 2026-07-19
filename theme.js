/* ==========================================================
   MindMirror — theme.js
   ----------------------------------------------------------
   Dark is the original/default look. This adds a Light theme
   toggle, persisted in localStorage so it holds across pages.

   IMPORTANT: this file is loaded synchronously in <head>
   (not deferred, not at the bottom of <body>) specifically so
   applyStoredTheme() runs BEFORE the page paints — otherwise
   people would see a flash of the dark theme before it swaps
   to light on every page load.
========================================================== */
(function applyStoredTheme(){
  try {
    var saved = localStorage.getItem("mindmirror-theme");
    if (saved === "light") {
      document.documentElement.setAttribute("data-theme", "light");
    }
  } catch (e) {
    // localStorage unavailable (private mode, etc.) — just fall back to dark.
  }
})();

function toggleTheme(){
  var isLight = document.documentElement.getAttribute("data-theme") === "light";
  var next = isLight ? "dark" : "light";
  if (next === "light") {
    document.documentElement.setAttribute("data-theme", "light");
  } else {
    document.documentElement.removeAttribute("data-theme");
  }
  try { localStorage.setItem("mindmirror-theme", next); } catch (e) {}
}

document.addEventListener("DOMContentLoaded", function(){
  var buttons = document.querySelectorAll(".theme-toggle");
  buttons.forEach(function(btn){
    btn.addEventListener("click", toggleTheme);
  });
});