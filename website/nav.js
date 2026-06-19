document.addEventListener("DOMContentLoaded", () => {
  const toggle = document.querySelector("[data-nav-toggle]");
  const links = document.querySelector("[data-nav-links]");
  const actions = document.querySelector("[data-nav-actions]");

  const setMenuOpen = (isOpen) => {
    links.classList.toggle("open", isOpen);
    actions.classList.toggle("open", isOpen);
    toggle.setAttribute("aria-expanded", String(isOpen));
    toggle.setAttribute("aria-label", isOpen ? "Close menu" : "Open menu");
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

      try {
        await navigator.clipboard.writeText(text);
        const previous = button.textContent;
        button.textContent = "Copied";
        button.classList.add("copied");
        button.setAttribute("aria-label", "Copied to clipboard");
        setTimeout(() => {
          button.textContent = previous;
          button.classList.remove("copied");
          button.setAttribute("aria-label", "Copy command to clipboard");
        }, 1400);
      } catch {
        button.textContent = "Copy failed";
        button.setAttribute("aria-label", "Copy failed");
      }
    });
  });
});
