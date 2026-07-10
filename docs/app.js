// Front-end da vitrine (GitHub Pages). Fala com o backend definido em config.js.
(function () {
  "use strict";

  var API_BASE = (window.API_BASE || "").replace(/\/+$/, "");
  var KEY_STORAGE = "agentapi_key";

  function backendConfigured() {
    return API_BASE.length > 0;
  }

  function showBackendWarning() {
    var w = document.getElementById("backend-warn");
    if (w) w.hidden = false;
  }

  async function api(path, options) {
    if (!backendConfigured()) {
      showBackendWarning();
      throw new Error("backend-not-configured");
    }
    var res = await fetch(API_BASE + path, options);
    var data = await res.json().catch(function () { return {}; });
    if (!res.ok) {
      throw new Error(data.detail || ("Erro " + res.status));
    }
    return data;
  }

  // --- Signup ---
  var form = document.getElementById("signup-form");
  if (form) {
    form.addEventListener("submit", async function (e) {
      e.preventDefault();
      var email = document.getElementById("email").value.trim();
      var out = document.getElementById("result");
      if (!backendConfigured()) { showBackendWarning(); return; }
      try {
        var data = await api("/auth/signup", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ email: email }),
        });
        if (data.api_key) localStorage.setItem(KEY_STORAGE, data.api_key);
        out.hidden = false;
        out.innerHTML =
          "<p>✅ Conta criada! Guarde sua chave de API (aparece só uma vez):</p>" +
          '<p class="key">' + (data.api_key || "(ver painel)") + "</p>" +
          "<p>Saldo inicial: <strong>" + (data.credits != null ? data.credits : 25) +
          " créditos</strong>. Use no cabeçalho <code>Authorization: Bearer &lt;chave&gt;</code>.</p>";
      } catch (err) {
        if (err.message === "backend-not-configured") return;
        out.hidden = false;
        out.textContent = "Não foi possível cadastrar: " + err.message;
      }
    });
  }

  // --- Buy credits (Stripe Checkout) ---
  var buttons = document.querySelectorAll(".buy");
  buttons.forEach(function (btn) {
    btn.addEventListener("click", async function () {
      if (!backendConfigured()) { showBackendWarning(); return; }
      var key = localStorage.getItem(KEY_STORAGE);
      if (!key) {
        document.getElementById("comecar").scrollIntoView();
        alert("Crie sua conta grátis primeiro para comprar créditos.");
        return;
      }
      try {
        var data = await api("/billing/checkout", {
          method: "POST",
          headers: {
            "content-type": "application/json",
            "authorization": "Bearer " + key,
          },
          body: JSON.stringify({ pack: btn.getAttribute("data-pack") }),
        });
        if (data.url) window.location.href = data.url; // Stripe Checkout
        else alert("Checkout indisponível (verifique a configuração da Stripe no backend).");
      } catch (err) {
        if (err.message === "backend-not-configured") return;
        alert("Erro ao iniciar a compra: " + err.message);
      }
    });
  });

  if (!backendConfigured()) showBackendWarning();
})();
