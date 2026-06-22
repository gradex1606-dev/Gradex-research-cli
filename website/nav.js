document.addEventListener("DOMContentLoaded", () => {
  const toggle = document.querySelector("[data-nav-toggle]");
  const links = document.querySelector("[data-nav-links]");
  const actions = document.querySelector("[data-nav-actions]");
  const toast = document.getElementById("copy-toast");
  let toastTimer;

  const setMenuOpen = (isOpen) => {
    links.classList.toggle("open", isOpen);
    actions.classList.toggle("open", isOpen);
    toggle.setAttribute("aria-expanded", String(isOpen));
    toggle.setAttribute("aria-label", isOpen ? "Close menu" : "Open menu");
  };

  const showToast = (message) => {
    if (!toast || !message) {
      return;
    }

    toast.textContent = message;
    toast.hidden = false;
    toast.classList.add("show");

    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toast.classList.remove("show");
      toast.hidden = true;
    }, 2200);
  };

  if (toggle && links && actions) {
    toggle.addEventListener("click", () => {
      setMenuOpen(!links.classList.contains("open"));
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && links.classList.contains("open")) {
        setMenuOpen(false);
        toggle.focus();
      }
    });

    links.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => setMenuOpen(false));
    });
    actions.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => setMenuOpen(false));
    });
  }

  document.querySelectorAll("[data-copy]").forEach((button) => {
    if (!button.getAttribute("aria-label")) {
      button.setAttribute("aria-label", "Copy command to clipboard");
    }

    button.addEventListener("click", async () => {
      const text = button.getAttribute("data-copy");
      if (!text) {
        return;
      }

      const toastMessage = button.getAttribute("data-copy-toast");
      const previous = button.textContent;

      try {
        await navigator.clipboard.writeText(text);
        button.textContent = "Copied";
        button.classList.add("copied");
        button.setAttribute("aria-label", "Copied to clipboard");
        if (toastMessage) {
          showToast(toastMessage);
        }
        setTimeout(() => {
          button.textContent = previous;
          button.classList.remove("copied");
          button.setAttribute(
            "aria-label",
            button.classList.contains("token-copy-btn")
              ? "Copy contract address"
              : "Copy command to clipboard"
          );
        }, 1400);
      } catch {
        button.textContent = "Copy failed";
        button.setAttribute("aria-label", "Copy failed");
      }
    });
  });
});
