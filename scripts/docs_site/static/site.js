/* Copyright 2026 Datakeel contributors — SPDX-License-Identifier: Apache-2.0 */
(function () {
  var storageKey = "datakeel.site.theme";
  var root = document.documentElement;
  var saved = null;
  try {
    saved = localStorage.getItem(storageKey);
  } catch (err) {
    saved = null;
  }
  if (saved === "dark" || saved === "light") {
    root.setAttribute("data-theme", saved);
  }

  function currentTheme() {
    var explicit = root.getAttribute("data-theme");
    if (explicit === "dark" || explicit === "light") {
      return explicit;
    }
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  }

  var toggle = document.querySelector("[data-theme-toggle]");
  if (toggle) {
    toggle.addEventListener("click", function () {
      var next = currentTheme() === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try {
        localStorage.setItem(storageKey, next);
      } catch (err) {
        /* Storage may be unavailable in private browsing. */
      }
    });
  }

  var sidebarToggle = document.querySelector("[data-sidebar-toggle]");
  var sidebar = document.querySelector("[data-docs-sidebar]");
  if (sidebarToggle && sidebar) {
    sidebarToggle.addEventListener("click", function () {
      var open = sidebar.classList.toggle("is-open");
      sidebarToggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  var copyButtons = document.querySelectorAll("[data-copy-target]");
  copyButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      var targetId = button.getAttribute("data-copy-target");
      var target = targetId ? document.getElementById(targetId) : null;
      if (!target || !navigator.clipboard) {
        return;
      }
      var original = button.textContent;
      navigator.clipboard.writeText(target.textContent.trim()).then(function () {
        button.textContent = button.getAttribute("data-copied-label") || "Copied";
        window.setTimeout(function () {
          button.textContent = original;
        }, 1600);
      });
    });
  });
})();
