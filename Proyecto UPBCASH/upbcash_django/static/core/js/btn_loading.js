(() => {
  // Estado de carga para botones de submit: aplica en cualquier formulario
  // cuyo boton de envio declare data-loading-text="...". No requiere
  // marcar nada en los demas formularios (opt-in por atributo).
  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) {
      return;
    }

    const button = form.querySelector('button[type="submit"][data-loading-text]');
    if (!button || button.disabled) {
      return;
    }

    const loadingText = button.getAttribute("data-loading-text") || "";
    if (!button.dataset.originalText) {
      button.dataset.originalText = button.textContent;
    }

    button.setAttribute("aria-busy", "true");
    button.disabled = true;
    if (loadingText) {
      button.textContent = loadingText;
    }
  });
})();
