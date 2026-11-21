/* Customer-facing cart: add without navigation, update one shared session-backed badge. */
(function () {
  "use strict";
  const badge = document.querySelector("[data-cart-badge]");
  const toast = document.getElementById("g12-cart-message");
  let toastTimeout;

  function updateBadge(total) {
    const amount = Math.max(0, Number(total) || 0);
    document.querySelectorAll("[data-cart-badge]").forEach(function (el) {
      el.textContent = String(amount);
      el.hidden = amount === 0;
    });
    document.querySelectorAll(".g12-header-cart").forEach(function (link) {
      link.setAttribute("aria-label", "Your cart (" + amount + " vehicles)");
    });
  }

  function notify(message, error, loginUrl) {
    if (!toast) return;
    toast.replaceChildren();
    toast.appendChild(document.createTextNode(message));
    if (loginUrl) {
      const a = document.createElement("a");
      a.href = loginUrl;
      a.textContent = "Log in";
      toast.appendChild(a);
    }
    toast.classList.toggle("g12-cart-error", Boolean(error));
    toast.hidden = false;
    window.clearTimeout(toastTimeout);
    toastTimeout = window.setTimeout(function () { toast.hidden = true; }, 3600);
  }

  // If user navigates to the home, listing, or detail page, the server-side
  // count is already rendered from the same rental_cart Flask session.
  // AJAX updates it immediately on the page currently open.
  document.addEventListener("submit", async function (event) {
    const form = event.target.closest("form[data-ajax-add-to-cart]");
    if (!form) return;
    if (typeof window.fetch !== "function") return;
    event.preventDefault();
    const button = form.querySelector('button[type="submit"]');
    if (button && button.disabled) return;
    if (button) button.disabled = true;

    try {
      const data = Object.fromEntries(new FormData(form).entries());
      const response = await fetch(form.action, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: JSON.stringify(data)
      });
      if (response.status === 401) {
        notify("Please log in to add a car to your cart.", true,
          form.dataset.loginUrl || "/login");
        return;
      }
      if (!response.ok) throw new Error("Unable to add car to cart.");
      const result = await response.json();
      if (!result.ok) throw new Error(result.message || "Unable to add car to cart.");
      updateBadge(result.total_count);
      notify(result.added === false ? "This car is already in your cart."
        : "Added to cart successfully!", false);
    } catch (error) {
      notify(error.message || "Unable to add car to cart. Please try again.", true);
    } finally {
      if (button) button.disabled = false;
    }
  });

  // A page reached with a full navigation already receives its current count
  // from the backend session. Keep the badge accessible to screen readers.
  if (badge && !badge.hidden) updateBadge(badge.textContent);
})();