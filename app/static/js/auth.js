(() => {
  const body = document.body;
  const toRegister = document.getElementById("toRegister");
  const toLogin = document.getElementById("toLogin");

  const title = document.getElementById("title");
  const subtitle = document.getElementById("subtitle");

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
  };

  toRegister?.addEventListener("click", () => setMode("register"));
  toLogin?.addEventListener("click", () => setMode("login"));
})();