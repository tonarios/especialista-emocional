"use strict";

// ── Estado local (token + sesión sobreviven refresh) ──────────────
const LS_TOKEN = "ah_emociones.token";
const LS_EMAIL = "ah_emociones.email";
const LS_SESSION = "ah_emociones.session";

function getToken() { return localStorage.getItem(LS_TOKEN); }
function saveSession(token, email) {
  localStorage.setItem(LS_TOKEN, token);
  localStorage.setItem(LS_EMAIL, email);
  if (!localStorage.getItem(LS_SESSION)) {
    localStorage.setItem(LS_SESSION, "s-" + Math.random().toString(36).slice(2, 10));
  }
}
function clearSession() {
  localStorage.removeItem(LS_TOKEN);
  localStorage.removeItem(LS_EMAIL);
  localStorage.removeItem(LS_SESSION);
}
function sessionId() { return localStorage.getItem(LS_SESSION) || "default"; }

// ── Elementos ─────────────────────────────────────────────────────
const loginView = document.getElementById("login-view");
const chatView = document.getElementById("chat-view");
const authForm = document.getElementById("auth-form");
const registerBtn = document.getElementById("register-btn");
const logoutBtn = document.getElementById("logout-btn");
const authError = document.getElementById("auth-error");
const userEmail = document.getElementById("user-email");
const messages = document.getElementById("messages");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const sendBtn = document.getElementById("send-btn");
const emailInput = document.getElementById("email");
const passwordInput = document.getElementById("password");

let mode = "login"; // "login" | "register"

// ── Vista ─────────────────────────────────────────────────────────
function show(view) {
  loginView.hidden = view !== loginView;
  chatView.hidden = view !== chatView;
}

function showError(msg) {
  authError.textContent = msg;
  authError.hidden = false;
}

// ── Acceso ────────────────────────────────────────────────────────
async function submitAuth(ev) {
  ev.preventDefault();
  authError.hidden = true;
  const endpoint = mode === "login" ? "/api/login" : "/api/register";
  const payload = { email: emailInput.value.trim(), password: passwordInput.value };
  try {
    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      showError(data.detail || (res.status === 429 ? "Demasiados intentos; espera un minuto." : "No se pudo completar."));
      return;
    }
    saveSession(data.token, data.email);
    enterChat(data.email);
  } catch {
    showError("No se pudo conectar con el servidor.");
  }
}

function enterChat(email) {
  userEmail.textContent = email;
  show(chatView);
  renderPlaceholder();
}

function renderPlaceholder() {
  messages.innerHTML = "";
  addMessage("assistant", "Hola. Cuéntame qué sientes y exploramos juntas su significado emocional desde el diccionario. Recuerda: esto es reflexión y autoconocimiento, no un diagnóstico médico.");
}

// ── Chat ──────────────────────────────────────────────────────────
function addMessage(role, text, sources, kind) {
  const wrap = document.createElement("div");
  wrap.className = "message " + (role === "user" ? "user" : "assistant") + (kind === "emergency" ? " emergency" : "");
  wrap.textContent = text || "…";
  if (sources && sources.length) {
    const chips = document.createElement("div");
    chips.className = "chips";
    for (const s of sources) {
      const chip = document.createElement("span");
      chip.className = "chip";
      chip.textContent = s.title || s.slug;
      chips.appendChild(chip);
    }
    wrap.appendChild(chips);
  }
  messages.appendChild(wrap);
  messages.scrollTop = messages.scrollHeight;
  return wrap;
}

async function sendMessage(ev) {
  ev.preventDefault();
  const text = chatInput.value.trim();
  if (!text) return;
  chatInput.value = "";
  addMessage("user", text);
  const typing = addMessage("assistant", "…", null, null);

  try {
    const res = await fetch("/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + getToken(),
      },
      body: JSON.stringify({ message: text, session_id: sessionId() }),
    });

    if (res.status === 401) { handleSessionExpired(); return; }
    if (res.status === 403) {
      // No se expone el `detail` del backend: es el motivo técnico del
      // guardarraíl y decirle al usuario qué patrón saltó facilita evadirlo.
      await res.json().catch(() => ({}));
      typing.textContent = "Tu mensaje fue bloqueado por seguridad. "
        + "Cuéntame qué síntoma sientes y con gusto te acompaño.";
      typing.classList.add("blocked");
      return;
    }
    if (res.status === 429) {
      typing.textContent = "Demasiados mensajes; espera un minuto y vuelve a intentarlo.";
      return;
    }
    if (!res.ok) { typing.textContent = "Ocurrió un error. Inténtalo de nuevo."; return; }

    // Streaming NDJSON: leemos eventos línea a línea hasta el evento final.
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let doneEvent = null;
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.trim()) continue;
        const ev = JSON.parse(line);
        if (ev.done) doneEvent = ev;
      }
    }
    if (doneEvent) {
      typing.textContent = doneEvent.text || "…";
      // El resaltado de emergencia depende del evento final: al crear la burbuja
      // todavía no se conoce el `kind`.
      if (doneEvent.kind === "emergency") typing.classList.add("emergency");
      if (doneEvent.sources && doneEvent.sources.length) {
        renderChips(typing, doneEvent.sources);
      }
      // La burbuja crece al llegar el texto: sin re-scroll el final de la
      // respuesta y los chips de fuentes quedan fuera de vista.
      messages.scrollTop = messages.scrollHeight;
    } else {
      typing.textContent = "No hubo respuesta.";
    }
  } catch {
    typing.textContent = "No se pudo conectar con el servidor.";
    typing.scrollIntoView();
  }
}

function renderChips(msgEl, sources) {
  const chips = document.createElement("div");
  chips.className = "chips";
  for (const s of sources) {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.textContent = s.title || s.slug;
    chips.appendChild(chip);
  }
  msgEl.appendChild(chips);
}

function handleSessionExpired() {
  clearSession();
  show(loginView);
  showError("Tu sesión venció. Inicia sesión de nuevo.");
}

// ── Wire-up ───────────────────────────────────────────────────────
authForm.addEventListener("submit", submitAuth);
registerBtn.addEventListener("click", () => {
  mode = mode === "login" ? "register" : "login";
  registerBtn.textContent = mode === "login" ? "Crear cuenta" : "Ya tengo cuenta";
  document.getElementById("login-btn").textContent = mode === "login" ? "Entrar" : "Registrarme";
});
logoutBtn.addEventListener("click", () => { clearSession(); location.reload(); });
chatForm.addEventListener("submit", sendMessage);

chatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); chatForm.requestSubmit(); }
});

// ── Arranque ──────────────────────────────────────────────────────
(function init() {
  registerBtn.textContent = "Crear cuenta";
  if (getToken()) {
    enterChat(localStorage.getItem(LS_EMAIL) || "usuario");
  } else {
    show(loginView);
  }
})();
