document.addEventListener("DOMContentLoaded", function () {
    const password = document.getElementById("password");
    const toggle = document.getElementById("toggle-password");

    if (password && toggle) {
        toggle.addEventListener("click", function () {
            const isHidden = password.type === "password";
            password.type = isHidden ? "text" : "password";
            toggle.setAttribute(
                "aria-label",
                isHidden ? "Hide password" : "Show password"
            );
        });
    }
});