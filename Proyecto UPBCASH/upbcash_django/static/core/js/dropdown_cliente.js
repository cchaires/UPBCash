(function () {
  const toggle = document.getElementById("userToggle");
  const menu = document.getElementById("userMenu");

  if (!toggle || !menu) {
    return;
  }

  const closeMenu = () => {
    menu.classList.remove("is-open");
    toggle.setAttribute("aria-expanded", "false");
    menu.setAttribute("aria-hidden", "true");
  };

  const openMenu = () => {
    menu.classList.add("is-open");
    toggle.setAttribute("aria-expanded", "true");
    menu.setAttribute("aria-hidden", "false");
  };

  toggle.addEventListener("click", (event) => {
    event.stopPropagation();
    if (menu.classList.contains("is-open")) {
      closeMenu();
      return;
    }
    openMenu();
  });

  document.addEventListener("click", (event) => {
    if (!menu.contains(event.target) && !toggle.contains(event.target)) {
      closeMenu();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeMenu();
      toggle.focus();
    }
  });
})();
