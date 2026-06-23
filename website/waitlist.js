document.addEventListener("DOMContentLoaded", () => {
  const modal = document.getElementById("waitlist-modal");
  if (!modal) {
    return;
  }

  const dialog = modal.querySelector(".waitlist-dialog");
  const form = modal.querySelector("#waitlist-form");
  const emailInput = modal.querySelector("#waitlist-email");
  const submitBtn = modal.querySelector("#waitlist-submit");
  const formView = modal.querySelector("[data-waitlist-form-view]");
  const successView = modal.querySelector("[data-waitlist-success-view]");
  const errorEl = modal.querySelector("[data-waitlist-error]");
  const closeButtons = modal.querySelectorAll("[data-waitlist-close]");

  const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  const isLocalDev =
    window.location.hostname === "localhost" ||
    window.location.hostname === "127.0.0.1";

  const openModal = () => {
    modal.hidden = false;
    modal.setAttribute("aria-hidden", "false");
    modal.classList.add("open");
    document.body.classList.add("waitlist-open");
    resetForm();
    emailInput.focus();
  };

  const closeModal = () => {
    modal.classList.remove("open");
    modal.hidden = true;
    modal.setAttribute("aria-hidden", "true");
    document.body.classList.remove("waitlist-open");
  };

  const resetForm = () => {
    form.reset();
    formView.hidden = false;
    successView.hidden = true;
    if (errorEl) {
      errorEl.hidden = true;
      errorEl.textContent = "";
    }
    updateSubmitState();
  };

  const updateSubmitState = () => {
    const valid = EMAIL_RE.test(emailInput.value.trim());
    submitBtn.disabled = !valid;
  };

  const showError = (message) => {
    if (!errorEl) {
      return;
    }
    errorEl.textContent = message;
    errorEl.hidden = false;
  };

  const showSuccess = () => {
    formView.hidden = true;
    successView.hidden = false;
    if (errorEl) {
      errorEl.hidden = true;
    }
  };

  const saveLocalDev = (email) => {
    const key = "gradex-waitlist-emails";
    const existing = JSON.parse(localStorage.getItem(key) || "[]");
    if (!existing.includes(email)) {
      existing.push(email);
      localStorage.setItem(key, JSON.stringify(existing));
    }
  };

  document.querySelectorAll("[data-waitlist-open]").forEach((trigger) => {
    trigger.addEventListener("click", (event) => {
      event.preventDefault();
      openModal();
    });
  });

  closeButtons.forEach((btn) => {
    btn.addEventListener("click", closeModal);
  });

  modal.addEventListener("click", (event) => {
    if (event.target === modal) {
      closeModal();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && modal.classList.contains("open")) {
      closeModal();
    }
  });

  emailInput.addEventListener("input", updateSubmitState);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const email = emailInput.value.trim().toLowerCase();
    if (!EMAIL_RE.test(email)) {
      return;
    }

    submitBtn.disabled = true;
    submitBtn.textContent = "Joining…";

    try {
      if (isLocalDev) {
        saveLocalDev(email);
        showSuccess();
        return;
      }

      const response = await fetch("/api/waitlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });

      const data = await response.json().catch(() => ({}));

      if (response.ok && data.ok) {
        showSuccess();
        return;
      }

      showError(
        data.error ||
          "Something went wrong. Please try again or star us on GitHub."
      );
    } catch {
      showError("Network error. Please check your connection and try again.");
    } finally {
      submitBtn.textContent = "Join Waitlist";
      updateSubmitState();
    }
  });

  if (dialog) {
    dialog.addEventListener("click", (event) => {
      event.stopPropagation();
    });
  }
});
