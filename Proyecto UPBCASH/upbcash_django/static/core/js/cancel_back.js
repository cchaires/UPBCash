(() => {
  function resolveTargetForm(control) {
    const selector = (control.getAttribute("data-form-selector") || "").trim();
    if (selector) {
      return document.querySelector(selector);
    }
    if (control.form) {
      return control.form;
    }
    return control.closest("form");
  }

  function resolveFallbackUrl(control) {
    const explicitFallback = (control.getAttribute("data-fallback-url") || "").trim();
    if (explicitFallback) {
      return explicitFallback;
    }
    const href = (control.getAttribute("href") || "").trim();
    return href || "";
  }

  function canGoBackWithinSite() {
    if (!document.referrer || window.history.length <= 1) {
      return false;
    }
    try {
      return new URL(document.referrer).origin === window.location.origin;
    } catch (_error) {
      return false;
    }
  }

  document.querySelectorAll(".js-cancel-back").forEach((control) => {
    control.addEventListener("click", (event) => {
      event.preventDefault();

      const targetForm = resolveTargetForm(control);
      if (targetForm && typeof targetForm.reset === "function") {
        targetForm.reset();
      }

      if (canGoBackWithinSite()) {
        window.history.back();
        return;
      }

      const fallbackUrl = resolveFallbackUrl(control);
      if (fallbackUrl) {
        window.location.href = fallbackUrl;
      }
    });
  });
})();
