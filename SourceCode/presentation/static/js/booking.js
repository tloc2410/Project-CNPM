/* ==========================================================================
   Client-side interactivity for Rental Cart & Booking (Do Thu Thao)
   - Instant AJAX overlap checking & fee recalculation
   - Cart selection checkboxes, Select All, Remove Selected, Remove item
   - Days stepper (- N +) synchronized with pickup/return date pickers
   - Checkout payment method cards, receiving method toggle, live date sync
   - Order cancellation confirmation
   ========================================================================== */

(function () {
    "use strict";

    function formatVnd(amount) {
        const num = Math.round(Number(amount) || 0);
        return num.toLocaleString("vi-VN") + "₫";
    }

    function addDays(isoDateStr, deltaDays) {
        if (!isoDateStr) return "";
        const parts = isoDateStr.split("-").map(Number);
        if (parts.length !== 3) return "";
        const d = new Date(Date.UTC(parts[0], parts[1] - 1, parts[2]));
        d.setUTCDate(d.getUTCDate() + deltaDays);
        return d.toISOString().slice(0, 10);
    }

    function formatEnDate(isoDateStr) {
        if (!isoDateStr) return "Select date";
        const parts = isoDateStr.split("-").map(Number);
        if (parts.length !== 3) return isoDateStr;
        const d = new Date(Date.UTC(parts[0], parts[1] - 1, parts[2]));
        return d.toLocaleDateString("en-US", {
            month: "short",
            day: "2-digit",
            year: "numeric",
            timeZone: "UTC",
        });
    }

    async function postJson(url, payload) {
        const res = await fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                Accept: "application/json",
            },
            body: JSON.stringify(payload || {}),
        });
        return res.json();
    }

    /* ---------------------- Header user menu ---------------------- */
    const userTrigger = document.getElementById("user-menu-trigger");
    const userDropdown = document.getElementById("user-menu-dropdown");
    if (userTrigger && userDropdown) {
        userTrigger.addEventListener("click", (e) => {
            e.stopPropagation();
            const isHidden = userDropdown.hasAttribute("hidden");
            if (isHidden) {
                userDropdown.removeAttribute("hidden");
                userTrigger.setAttribute("aria-expanded", "true");
            } else {
                userDropdown.setAttribute("hidden", "");
                userTrigger.setAttribute("aria-expanded", "false");
            }
        });
        document.addEventListener("click", () => {
            userDropdown.setAttribute("hidden", "");
            userTrigger.setAttribute("aria-expanded", "false");
        });
    }

    /* ---------------------- Cart page logic ---------------------- */
    const cartRoot = document.querySelector('[data-page="cart"]');
    if (cartRoot) {
        const selectAllEl = document.getElementById("select-all-checkbox");
        const removeSelectedBtn = document.getElementById("remove-selected-btn");
        const navBadge = document.getElementById("nav-cart-badge");
        const titleCount = document.getElementById("cart-title-count");
        const selectedCountEl = document.getElementById("summary-selected-count");
        const selectedSubtotalEl = document.getElementById("summary-selected-subtotal");
        const rentalFeeEl = document.getElementById("summary-rental-fee");
        const totalEl = document.getElementById("summary-total");
        const proceedBtn = document.getElementById("proceed-checkout-btn");
        const helperText = document.getElementById("summary-helper-text");

        function applyCartSummary(data) {
            if (!data || !data.ok) return;

            if (navBadge) navBadge.textContent = String(data.total_count);
            if (titleCount) titleCount.textContent = String(data.total_count);
            if (selectedCountEl) selectedCountEl.textContent = String(data.selected_count);
            if (selectedSubtotalEl) selectedSubtotalEl.textContent = formatVnd(data.subtotal);
            if (rentalFeeEl) rentalFeeEl.textContent = formatVnd(data.subtotal);
            if (totalEl) totalEl.textContent = formatVnd(data.total);
            if (selectAllEl) selectAllEl.checked = Boolean(data.all_selected);
            if (removeSelectedBtn) removeSelectedBtn.disabled = data.selected_count === 0;

            if (proceedBtn) {
                if (data.is_valid) {
                    proceedBtn.classList.add("is-enabled");
                    proceedBtn.classList.remove("is-disabled");
                    proceedBtn.removeAttribute("aria-disabled");
                } else {
                    proceedBtn.classList.remove("is-enabled");
                    proceedBtn.classList.add("is-disabled");
                    proceedBtn.setAttribute("aria-disabled", "true");
                }
            }

            if (helperText) {
                if (data.selected_count === 0) {
                    helperText.textContent =
                        "Select the cars you want to rent to calculate the order total.";
                } else if (!data.is_valid) {
                    helperText.textContent =
                        "Vui lòng xử lý cảnh báo trùng lịch hoặc ngày thuê không hợp lệ trước khi thanh toán.";
                } else {
                    helperText.textContent =
                        "Đã sẵn sàng! Nhấn Proceed to Checkout để xác nhận thông tin và thanh toán.";
                }
            }

            (data.items || []).forEach((item) => {
                const card = cartRoot.querySelector(`.cart-card[data-car-id="${item.car_id}"]`);
                if (!card) return;

                const cb = card.querySelector(".item-checkbox");
                if (cb) cb.checked = Boolean(item.selected);

                const daysEl = card.querySelector(`[data-days-display="${item.car_id}"]`);
                if (daysEl) daysEl.textContent = String(item.rental_days > 0 ? item.rental_days : 1);

                const lineTotalEl = card.querySelector(`[data-line-total="${item.car_id}"]`);
                if (lineTotalEl) {
                    lineTotalEl.textContent =
                        item.rental_days > 0
                            ? `(${item.rental_days} ngày: ${formatVnd(item.line_total)})`
                            : "";
                }

                const errBox = card.querySelector(`[data-error-box="${item.car_id}"]`);
                const errText = card.querySelector(`[data-error-text="${item.car_id}"]`);
                if (item.error) {
                    card.classList.add("has-error");
                    if (errText) errText.textContent = item.error;
                    if (errBox) errBox.removeAttribute("hidden");
                } else {
                    card.classList.remove("has-error");
                    if (errText) errText.textContent = "";
                    if (errBox) errBox.setAttribute("hidden", "");
                }
            });
        }

        async function syncDatesForCar(carId) {
            const pickupEl = document.getElementById(`pickup-${carId}`);
            const returnEl = document.getElementById(`return-${carId}`);
            if (!pickupEl || !returnEl) return;

            const data = await postJson("/api/cart/dates", {
                car_id: carId,
                pickup_date: pickupEl.value,
                return_date: returnEl.value,
            });
            applyCartSummary(data);
        }

        // Date picker changes -> instant overlap check + price recalc
        cartRoot.querySelectorAll(".cart-date-input").forEach((input) => {
            input.addEventListener("change", () => {
                const carId = Number(input.dataset.carId);
                syncDatesForCar(carId);
            });
        });

        // Rental days stepper (- / +) -> adjusts return_date and syncs
        cartRoot.querySelectorAll(".stepper-btn").forEach((btn) => {
            btn.addEventListener("click", () => {
                const carId = Number(btn.dataset.carId);
                const pickupEl = document.getElementById(`pickup-${carId}`);
                const returnEl = document.getElementById(`return-${carId}`);
                if (!pickupEl || !returnEl) return;

                if (!pickupEl.value) {
                    const tomorrow = new Date();
                    tomorrow.setDate(tomorrow.getDate() + 1);
                    pickupEl.value = tomorrow.toISOString().slice(0, 10);
                }
                if (!returnEl.value || returnEl.value <= pickupEl.value) {
                    returnEl.value = addDays(pickupEl.value, 1);
                }

                const delta = btn.classList.contains("stepper-plus") ? 1 : -1;
                const nextReturn = addDays(returnEl.value, delta);
                if (nextReturn <= pickupEl.value) {
                    return; // Minimum 1 rental day
                }
                returnEl.value = nextReturn;
                syncDatesForCar(carId);
            });
        });

        // Individual checkbox selection
        cartRoot.querySelectorAll(".item-checkbox").forEach((cb) => {
            cb.addEventListener("change", async () => {
                const data = await postJson("/api/cart/select", {
                    car_id: Number(cb.dataset.carId),
                    selected: cb.checked,
                });
                applyCartSummary(data);
            });
        });

        // Select All checkbox
        if (selectAllEl) {
            selectAllEl.addEventListener("change", async () => {
                const data = await postJson("/api/cart/select", {
                    select_all: selectAllEl.checked,
                });
                applyCartSummary(data);
            });
        }

        // Remove single car via AJAX (fallback to normal POST if JS off)
        cartRoot.querySelectorAll(".remove-car-form").forEach((form) => {
            form.addEventListener("submit", async (e) => {
                e.preventDefault();
                const carId = Number(form.dataset.carId);
                const data = await postJson(form.action, {});
                const card = cartRoot.querySelector(`.cart-card[data-car-id="${carId}"]`);
                if (card) card.remove();
                if (!data || data.total_count === 0) {
                    window.location.reload();
                    return;
                }
                applyCartSummary(data);
            });
        });
    }

    /* ---------------------- Checkout page logic ---------------------- */
    const checkoutRoot = document.querySelector('[data-page="checkout"]');
    if (checkoutRoot) {
        const pickupInput = document.getElementById("co-pickup-date");
        const returnInput = document.getElementById("co-return-date");
        const pickupLocInput = document.getElementById("co-pickup-location");
        const returnLocInput = document.getElementById("co-return-location");
        const datesModifiedInput = document.getElementById("co-dates-modified");
        const errBanner = document.getElementById("checkout-error-banner");
        const errText = document.getElementById("checkout-error-text");
        const submitBtn = document.getElementById("btn-submit-order");

        const daysLabel = document.getElementById("co-days-label");
        const subtotalEl = document.getElementById("co-subtotal");
        const deliveryEl = document.getElementById("co-delivery-fee");
        const depositEl = document.getElementById("co-deposit");
        const totalEl = document.getElementById("co-total");

        const cardDetailsPanel = document.getElementById("card-details-panel");
        const altPaymentNote = document.getElementById("alt-payment-note");

        const ALT_PAYMENT_HINTS = {
            E_WALLET:
                "Thanh toán nhanh qua ví điện tử (MoMo / ZaloPay). Mã QR sẽ được hiển thị sau khi xác nhận đơn.",
            BANK_TRANSFER:
                "Chuyển khoản ngân hàng theo thông tin đơn hàng sau khi đặt. Đơn sẽ giữ lịch xe ngay lập tức.",
            CASH:
                "Thanh toán tiền mặt trực tiếp khi nhận xe tại điểm hẹn hoặc khi nhân viên giao xe tận nơi.",
        };

        function getSelectedReceiving() {
            const checked = checkoutRoot.querySelector('input[name="receiving_method"]:checked');
            return checked ? checked.value : "PICKUP";
        }

        function applyCheckoutSummary(data) {
            if (!data || !data.ok) return;

            const totalDays = (data.items || []).reduce((acc, i) => acc + (i.rental_days || 0), 0);
            if (daysLabel) {
                daysLabel.textContent = `${totalDays} ${totalDays === 1 ? "day" : "days"}`;
            }
            if (subtotalEl) subtotalEl.textContent = formatVnd(data.subtotal);
            if (deliveryEl) {
                if (data.delivery_fee === 0) {
                    deliveryEl.textContent = "Free";
                    deliveryEl.classList.add("text-free");
                } else {
                    deliveryEl.textContent = formatVnd(data.delivery_fee);
                    deliveryEl.classList.remove("text-free");
                }
            }
            if (depositEl) depositEl.textContent = formatVnd(data.deposit);
            if (totalEl) totalEl.textContent = formatVnd(data.total);

            (data.items || []).forEach((item) => {
                const dateSpan = checkoutRoot.querySelector(`[data-co-date-range="${item.car_id}"]`);
                if (dateSpan) {
                    const dayWord = item.rental_days === 1 ? "day" : "days";
                    dateSpan.textContent = `${formatEnDate(item.pickup_date)} – ${formatEnDate(
                        item.return_date
                    )} (${item.rental_days} ${dayWord})`;
                }
                const locSpan = checkoutRoot.querySelector(`[data-co-loc="${item.car_id}"]`);
                if (locSpan && item.pickup_location) {
                    locSpan.textContent = item.pickup_location;
                }
            });

            const firstErr = (data.items || []).find((i) => i.error);
            if (firstErr) {
                if (errText) errText.textContent = firstErr.error;
                if (errBanner) errBanner.removeAttribute("hidden");
                if (submitBtn) submitBtn.disabled = true;
            } else {
                if (errText) errText.textContent = "";
                if (errBanner) errBanner.setAttribute("hidden", "");
                if (submitBtn) submitBtn.disabled = !data.is_valid;
            }
        }

        async function syncCheckoutDates() {
            if (datesModifiedInput) datesModifiedInput.value = "1";
            const data = await postJson("/api/cart/dates", {
                apply_selected: true,
                pickup_date: pickupInput ? pickupInput.value : "",
                return_date: returnInput ? returnInput.value : "",
                pickup_location: pickupLocInput ? pickupLocInput.value : "",
                return_location: returnLocInput ? returnLocInput.value : "",
                receiving_method: getSelectedReceiving(),
            });
            applyCheckoutSummary(data);
        }

        async function syncCheckoutSummaryOnly() {
            const data = await postJson("/api/cart/summary", {
                receiving_method: getSelectedReceiving(),
                selected_only: true,
            });
            applyCheckoutSummary(data);
        }

        if (pickupInput) pickupInput.addEventListener("change", syncCheckoutDates);
        if (returnInput) returnInput.addEventListener("change", syncCheckoutDates);
        if (pickupLocInput) {
            pickupLocInput.addEventListener("change", () => {
                if (pickupLocInput.value === "Home Delivery") {
                    const delRadio = checkoutRoot.querySelector(
                        'input[name="receiving_method"][value="DELIVERY"]'
                    );
                    if (delRadio) {
                        delRadio.checked = true;
                        updateReceivingPills();
                    }
                }
                syncCheckoutDates();
            });
        }
        if (returnLocInput) returnLocInput.addEventListener("change", syncCheckoutDates);

        function updateReceivingPills() {
            checkoutRoot.querySelectorAll(".receiving-pill").forEach((pill) => {
                const radio = pill.querySelector('input[type="radio"]');
                pill.classList.toggle("is-selected", Boolean(radio && radio.checked));
            });
        }

        checkoutRoot.querySelectorAll('input[name="receiving_method"]').forEach((radio) => {
            radio.addEventListener("change", () => {
                updateReceivingPills();
                syncCheckoutSummaryOnly();
            });
        });

        // Payment Method 4-card selector
        checkoutRoot.querySelectorAll(".pay-card").forEach((card) => {
            card.addEventListener("click", () => {
                const radio = card.querySelector('input[type="radio"]');
                if (!radio) return;
                radio.checked = true;
                checkoutRoot.querySelectorAll(".pay-card").forEach((c) => {
                    c.classList.toggle("is-selected", c === card);
                });

                const method = radio.value;
                if (method === "CARD") {
                    if (cardDetailsPanel) cardDetailsPanel.removeAttribute("hidden");
                    if (altPaymentNote) altPaymentNote.setAttribute("hidden", "");
                } else {
                    if (cardDetailsPanel) cardDetailsPanel.setAttribute("hidden", "");
                    if (altPaymentNote) {
                        altPaymentNote.textContent = ALT_PAYMENT_HINTS[method] || "";
                        altPaymentNote.removeAttribute("hidden");
                    }
                }
            });
        });

        // Format card number & expiry neatly
        const cardNumInput = document.getElementById("card-number");
        if (cardNumInput) {
            cardNumInput.addEventListener("input", () => {
                const digits = cardNumInput.value.replace(/\D/g, "").slice(0, 16);
                cardNumInput.value = digits.replace(/(\d{4})(?=\d)/g, "$1 ");
            });
        }
        const cardExpInput = document.getElementById("card-expiry");
        if (cardExpInput) {
            cardExpInput.addEventListener("input", () => {
                const digits = cardExpInput.value.replace(/\D/g, "").slice(0, 4);
                cardExpInput.value =
                    digits.length > 2 ? `${digits.slice(0, 2)} / ${digits.slice(2)}` : digits;
            });
        }
    }

    /* ---------------------- Orders page confirmation ---------------------- */
    document.querySelectorAll(".cancel-order-form").forEach((form) => {
        form.addEventListener("submit", (e) => {
            const orderId = form.dataset.orderId;
            const ok = window.confirm(
                `Bạn có chắc chắn muốn hủy đơn hàng #${orderId} không? Lịch thuê xe sẽ được giải phóng ngay sau khi hủy.`
            );
            if (!ok) {
                e.preventDefault();
            }
        });
    });
})();
