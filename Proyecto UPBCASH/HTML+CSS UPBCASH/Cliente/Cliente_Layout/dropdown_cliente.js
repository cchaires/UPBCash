const toggle = document.getElementById("userToggle");
const menu = document.getElementById("userMenu");

toggle?.addEventListener("click", (e) => {
  e.stopPropagation();
  const isOpen = menu.style.display === "block";
  menu.style.display = isOpen ? "none" : "block";
  toggle.setAttribute("aria-expanded", String(!isOpen));
  menu.setAttribute("aria-hidden", String(isOpen));
});

document.addEventListener("click", () => {
  if (!menu) return;
  menu.style.display = "none";
  toggle?.setAttribute("aria-expanded", "false");
  menu.setAttribute("aria-hidden", "true");
});


