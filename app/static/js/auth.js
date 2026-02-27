(() => {
  const body = document.body;

  const toRegister = document.getElementById("toRegister");
  const toLogin = document.getElementById("toLogin");

  const title = document.getElementById("title");
  const subtitle = document.getElementById("subtitle");

  const overlay = document.querySelector(".forms-overlay");

  // Register password confirm
  const pw = document.getElementById("password_reg");
  const pw2 = document.getElementById("confirm_password_reg");
  const pwHint = document.getElementById("pwHint");
  const registerForm = document.getElementById("registerForm");

  // Helpers
  const pulseOverlay = () => {
    if (!overlay) return;
    overlay.classList.remove("pulse");
    // reflow para reiniciar animación
    void overlay.offsetWidth;
    overlay.classList.add("pulse");
  };

  const setMode = (mode) => {
    if (mode === "register") {
      body.classList.remove("mode-login");
      body.classList.add("mode-register");
      title.textContent = "Registro institucional";
      subtitle.textContent = "CoyoLabs Universidad — Crear cuenta";
    } else {
      body.classList.remove("mode-register");
      body.classList.add("mode-login");
      title.textContent = "Iniciar sesión";
      subtitle.textContent = "CoyoLabs Universidad — Acceso institucional";
    }
    pulseOverlay();
  };

  // Modo inicial según clase del body
  if (body.classList.contains("mode-register")) setMode("register");
  else setMode("login");

  // Switch buttons
  toRegister?.addEventListener("click", () => setMode("register"));
  toLogin?.addEventListener("click", () => setMode("login"));

  // Toggle password (ojito)
  const toggleBtns = document.querySelectorAll(".toggle-pass[data-toggle]");
  toggleBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      const targetId = btn.getAttribute("data-toggle");
      const input = document.getElementById(targetId);
      if (!input) return;

      const isPassword = input.getAttribute("type") === "password";
      input.setAttribute("type", isPassword ? "text" : "password");

      btn.classList.toggle("is-on", isPassword);
      btn.setAttribute("aria-label", isPassword ? "Ocultar contraseña" : "Mostrar contraseña");
    });
  });

  // Confirm password validation (solo en register)
  const validateConfirm = () => {
    if (!pw || !pw2 || !pwHint) return true;

    const a = pw.value || "";
    const b = pw2.value || "";

    // No molestes si aún no teclea
    if (!a && !b) {
      pwHint.textContent = "";
      pwHint.className = "hint";
      return true;
    }

    if (b.length === 0) {
      pwHint.textContent = "";
      pwHint.className = "hint";
      return true;
    }

    const ok = a === b;
    pwHint.textContent = ok ? "✅ Las contraseñas coinciden" : "❌ Las contraseñas no coinciden";
    pwHint.className = ok ? "hint good" : "hint bad";

    return ok;
  };

  pw?.addEventListener("input", validateConfirm);
  pw2?.addEventListener("input", validateConfirm);

  registerForm?.addEventListener("submit", (e) => {
    if (!validateConfirm()) {
      e.preventDefault();
      pw2?.focus();
    }
  });
  
})();
