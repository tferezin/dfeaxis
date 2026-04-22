/**
 * DFeAxis Chat Widget — versão vanilla JS pra landing estática.
 * Não tem dependências. Injeta um botão flutuante + modal de chat.
 * Consome POST /api/v1/chat/landing no backend.
 */
(function () {
  var API_URL = "https://api.dfeaxis.com.br";
  var STORAGE_KEY = "dfeaxis:chat_session";
  var STORAGE_LEAD = "dfeaxis:chat_lead";

  // Não carregar no dashboard (tem o React widget próprio)
  if (window.location.pathname.startsWith("/dashboard")) return;
  if (window.location.pathname.startsWith("/cadastros")) return;
  if (window.location.pathname.startsWith("/historico")) return;
  if (window.location.pathname.startsWith("/logs")) return;
  if (window.location.pathname.startsWith("/financeiro")) return;
  if (window.location.pathname.startsWith("/execucao")) return;
  if (window.location.pathname.startsWith("/getting-started")) return;

  // Lista de domínios públicos bloqueados client-side (UX). O backend re-valida.
  var PUBLIC_DOMAINS = [
    "gmail.com","googlemail.com","hotmail.com","hotmail.com.br","outlook.com",
    "outlook.com.br","live.com","live.com.br","msn.com","yahoo.com","yahoo.com.br",
    "ymail.com","icloud.com","me.com","mac.com","aol.com","aim.com","uol.com.br",
    "bol.com.br","terra.com.br","ig.com.br","r7.com","zipmail.com.br","globo.com",
    "proton.me","protonmail.com","pm.me","mail.com","gmx.com","fastmail.com",
    "tutanota.com","qq.com","163.com","126.com"
  ];

  // Lead salvo? (localStorage)
  function loadSavedLead() {
    try {
      var raw = localStorage.getItem(STORAGE_LEAD);
      if (!raw) return null;
      var parsed = JSON.parse(raw);
      if (parsed && parsed.email && parsed.conversation_id) return parsed;
    } catch (e) {}
    return null;
  }

  var savedLead = loadSavedLead();

  // ---------- State ----------
  var state = {
    open: false,
    messages: [
      {
        role: "assistant",
        content: savedLead
          ? "Oi de novo, " + (savedLead.nome || "").split(" ")[0] + "! Como posso ajudar hoje?"
          : "Oi! Sou o assistente do DFeAxis. Posso tirar dúvidas sobre captura automática de NF-e, integração com seu ERP, planos ou o trial. Por onde quer começar?",
      },
    ],
    loading: false,
    conversationId: savedLead ? savedLead.conversation_id : null,
    leadCaptured: !!savedLead,
  };

  function getSessionId() {
    var id = localStorage.getItem(STORAGE_KEY);
    if (!id) {
      id =
        (crypto && crypto.randomUUID && crypto.randomUUID()) ||
        "sess-" + Date.now() + "-" + Math.random().toString(36).slice(2);
      localStorage.setItem(STORAGE_KEY, id);
    }
    return id;
  }

  // ---------- Styles ----------
  var css = `
.dfeax-chat-btn {
  position: fixed;
  /* Fica acima da sticky-bar da landing (~60px desktop, ~52px mobile).
     Desktop: 24px margem + 64px sticky-bar = 88px
     Mobile: ajustado via media query abaixo. */
  bottom: 72px;
  right: 32px;
  z-index: 9999;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 18px;
  background: #0c4a30;
  color: #fff;
  border: none;
  border-radius: 999px;
  font-family: -apple-system, BlinkMacSystemFont, 'Outfit', 'Segoe UI', sans-serif;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 8px 24px rgba(12, 74, 48, 0.3);
  transition: all 0.2s;
}
.dfeax-chat-btn:hover {
  background: #197550;
  transform: translateY(-2px);
  box-shadow: 0 12px 32px rgba(12, 74, 48, 0.4);
}
@media (max-width: 800px) {
  .dfeax-chat-btn {
    /* Mobile portrait: sticky-bar empilha em 2 linhas (~90px).
       Fica logo acima. */
    bottom: 100px;
    right: 16px;
    padding: 10px 16px;
    font-size: 13px;
  }
}
@media (max-width: 800px) and (orientation: landscape) {
  .dfeax-chat-btn {
    /* Landscape: sticky-bar volta a ser 1 linha, ~60px. */
    bottom: 76px;
  }
}
.dfeax-chat-panel {
  position: fixed;
  /* Fica acima da sticky-bar da landing (alinhado com o botão) */
  bottom: 72px;
  right: 32px;
  z-index: 9999;
  width: 380px;
  max-width: calc(100vw - 48px);
  height: 560px;
  max-height: calc(100vh - 112px);
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.2);
  display: flex;
  flex-direction: column;
  font-family: -apple-system, BlinkMacSystemFont, 'Outfit', 'Segoe UI', sans-serif;
  overflow: hidden;
}
@media (max-width: 800px) {
  .dfeax-chat-panel {
    bottom: 130px;
    right: 16px;
    max-width: calc(100vw - 32px);
    max-height: calc(100vh - 160px);
  }
}
@media (max-width: 800px) and (orientation: landscape) {
  .dfeax-chat-panel {
    bottom: 76px;
    max-height: calc(100vh - 100px);
  }
}
.dfeax-chat-header {
  background: #0c4a30;
  color: #fff;
  padding: 14px 18px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}
.dfeax-chat-header-text {
  font-size: 14px;
  font-weight: 600;
}
.dfeax-chat-header-sub {
  font-size: 11px;
  opacity: 0.8;
  margin-top: 2px;
}
.dfeax-chat-close {
  background: none;
  border: none;
  color: #fff;
  font-size: 22px;
  cursor: pointer;
  padding: 0;
  width: 24px;
  height: 24px;
  line-height: 1;
  opacity: 0.8;
}
.dfeax-chat-close:hover {
  opacity: 1;
}
.dfeax-chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: #f7f9fb;
}
.dfeax-chat-msg {
  max-width: 85%;
  padding: 10px 14px;
  border-radius: 16px;
  font-size: 14px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-wrap: break-word;
}
.dfeax-chat-msg-user {
  align-self: flex-end;
  background: #0c4a30;
  color: #fff;
}
.dfeax-chat-msg-assistant {
  align-self: flex-start;
  background: #fff;
  color: #111d2e;
  border: 1px solid #e8eefa;
}
.dfeax-chat-typing {
  align-self: flex-start;
  color: #8898b0;
  font-size: 12px;
  padding: 8px 14px;
}
.dfeax-chat-input-wrap {
  border-top: 1px solid #e8eefa;
  padding: 12px;
  background: #fff;
}
.dfeax-chat-input-row {
  display: flex;
  gap: 8px;
  align-items: flex-end;
}
.dfeax-chat-input {
  flex: 1;
  resize: none;
  padding: 10px 12px;
  font-family: inherit;
  font-size: 14px;
  border: 1px solid #d1d9e6;
  border-radius: 10px;
  outline: none;
  min-height: 40px;
  max-height: 120px;
  color: #111d2e;
}
.dfeax-chat-input:focus {
  border-color: #197550;
}
.dfeax-chat-send {
  background: #0c4a30;
  color: #fff;
  border: none;
  border-radius: 10px;
  padding: 10px 16px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  min-height: 40px;
}
.dfeax-chat-send:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.dfeax-chat-footer {
  margin-top: 8px;
  font-size: 10px;
  color: #8898b0;
  text-align: center;
}

/* Lead capture form (pré-chat) */
.dfeax-chat-lead {
  flex: 1;
  overflow-y: auto;
  padding: 18px 18px 16px;
  background: #f7f9fb;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.dfeax-chat-lead h3 {
  font-size: 14px;
  font-weight: 600;
  color: #111d2e;
  margin: 0 0 2px 0;
}
.dfeax-chat-lead p {
  font-size: 12.5px;
  color: #4a5670;
  line-height: 1.5;
  margin: 0 0 10px 0;
}
.dfeax-chat-lead label {
  display: block;
  font-size: 11px;
  font-weight: 600;
  color: #4a5670;
  letter-spacing: 0.02em;
  margin: 6px 0 4px;
}
.dfeax-chat-lead label .req { color: #a81a1a; }
.dfeax-chat-lead input {
  width: 100%;
  box-sizing: border-box;
  padding: 9px 11px;
  border: 1px solid #d1d9e6;
  border-radius: 8px;
  font-family: inherit;
  font-size: 13.5px;
  color: #111d2e;
  outline: none;
  background: #fff;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.dfeax-chat-lead input:focus {
  border-color: #197550;
  box-shadow: 0 0 0 3px rgba(25, 117, 80, 0.1);
}
.dfeax-chat-lead input.err {
  border-color: rgba(168, 26, 26, 0.5);
}
.dfeax-chat-lead .err-msg {
  font-size: 11.5px;
  color: #a81a1a;
  margin-top: 4px;
  line-height: 1.4;
}
.dfeax-chat-lead-btn {
  margin-top: 14px;
  padding: 11px;
  background: #0c4a30;
  color: #fff;
  border: none;
  border-radius: 9px;
  font-family: inherit;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
}
.dfeax-chat-lead-btn:hover:not(:disabled) {
  background: #197550;
}
.dfeax-chat-lead-btn:disabled {
  opacity: 0.6;
  cursor: wait;
}
.dfeax-chat-lead-note {
  font-size: 10.5px;
  color: #8898b0;
  text-align: center;
  margin-top: 8px;
  line-height: 1.5;
}
`;

  function injectStyle() {
    var style = document.createElement("style");
    style.textContent = css;
    document.head.appendChild(style);
  }

  // ---------- DOM helpers ----------
  var elements = {};

  function createButton() {
    var btn = document.createElement("button");
    btn.className = "dfeax-chat-btn";
    btn.type = "button";
    btn.setAttribute("aria-label", "Abrir chat");
    btn.innerHTML =
      '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg><span>Dúvidas?</span>';
    btn.addEventListener("click", openPanel);
    return btn;
  }

  function createPanel() {
    var panel = document.createElement("div");
    panel.className = "dfeax-chat-panel";
    panel.style.display = "none";
    panel.innerHTML =
      '<div class="dfeax-chat-header">' +
      '<div>' +
      '<div class="dfeax-chat-header-text">Assistente DFeAxis</div>' +
      '<div class="dfeax-chat-header-sub">Dúvidas sobre o produto</div>' +
      "</div>" +
      '<button class="dfeax-chat-close" type="button" aria-label="Fechar">&times;</button>' +
      "</div>" +
      // Lead form (pré-chat) — escondido se já capturou
      '<form class="dfeax-chat-lead" style="display:none">' +
      '<h3>Antes da gente conversar…</h3>' +
      '<p>Preciso só de 3 coisinhas pra te atender certo. Prometido: sem SDR ligando depois.</p>' +
      '<label>Nome <span class="req">*</span></label>' +
      '<input name="nome" type="text" placeholder="Como você se chama?" maxlength="100" autocomplete="name" required>' +
      '<label>E-mail corporativo <span class="req">*</span></label>' +
      '<input name="email" type="email" placeholder="nome@suaempresa.com.br" maxlength="200" autocomplete="email" required>' +
      '<label>Empresa <span class="req">*</span></label>' +
      '<input name="empresa" type="text" placeholder="Razão social ou nome fantasia" maxlength="120" autocomplete="organization" required>' +
      '<label>Telefone (opcional)</label>' +
      '<input name="telefone" type="tel" placeholder="(11) 99999-9999" maxlength="40" autocomplete="tel">' +
      '<div class="err-msg" style="display:none"></div>' +
      '<button type="submit" class="dfeax-chat-lead-btn">Começar conversa →</button>' +
      '<div class="dfeax-chat-lead-note">Só aceitamos e-mail corporativo (sem gmail/hotmail/outlook).<br>Seus dados ficam com a gente, sob LGPD — nada é vendido.</div>' +
      "</form>" +
      '<div class="dfeax-chat-messages"></div>' +
      '<div class="dfeax-chat-input-wrap" style="display:none">' +
      '<div class="dfeax-chat-input-row">' +
      '<textarea class="dfeax-chat-input" rows="2" placeholder="Escreva sua mensagem..."></textarea>' +
      '<button class="dfeax-chat-send" type="button">Enviar</button>' +
      "</div>" +
      '<div class="dfeax-chat-footer">Este chat é gravado para melhorar o atendimento. Powered by Claude.</div>' +
      "</div>";

    panel.querySelector(".dfeax-chat-close").addEventListener("click", closePanel);

    var input = panel.querySelector(".dfeax-chat-input");
    var sendBtn = panel.querySelector(".dfeax-chat-send");
    var leadForm = panel.querySelector(".dfeax-chat-lead");

    sendBtn.addEventListener("click", sendMessage);
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });

    leadForm.addEventListener("submit", function (e) {
      e.preventDefault();
      submitLead(leadForm);
    });

    elements.panel = panel;
    elements.messagesBox = panel.querySelector(".dfeax-chat-messages");
    elements.input = input;
    elements.sendBtn = sendBtn;
    elements.leadForm = leadForm;
    elements.leadErr = leadForm.querySelector(".err-msg");
    elements.leadBtn = leadForm.querySelector(".dfeax-chat-lead-btn");
    elements.inputWrap = panel.querySelector(".dfeax-chat-input-wrap");
    return panel;
  }

  function getDomain(email) {
    var at = email.indexOf("@");
    if (at < 0) return "";
    return email.slice(at + 1).toLowerCase().trim();
  }

  function showLeadErr(msg) {
    if (!elements.leadErr) return;
    elements.leadErr.textContent = msg;
    elements.leadErr.style.display = msg ? "block" : "none";
  }

  function submitLead(form) {
    var fd = new FormData(form);
    var nome = (fd.get("nome") || "").toString().trim();
    var email = (fd.get("email") || "").toString().trim().toLowerCase();
    var empresa = (fd.get("empresa") || "").toString().trim();
    var telefone = (fd.get("telefone") || "").toString().trim();

    // Reset estados
    showLeadErr("");
    Array.prototype.forEach.call(form.querySelectorAll("input"), function (i) {
      i.classList.remove("err");
    });

    // Validação simples
    if (!nome || nome.length < 2) {
      form.querySelector('[name=nome]').classList.add("err");
      showLeadErr("Escreve teu nome aí 👆");
      return;
    }
    if (!email || email.indexOf("@") < 0 || email.indexOf(".") < 0) {
      form.querySelector('[name=email]').classList.add("err");
      showLeadErr("E-mail inválido.");
      return;
    }
    var domain = getDomain(email);
    if (PUBLIC_DOMAINS.indexOf(domain) >= 0) {
      form.querySelector('[name=email]').classList.add("err");
      showLeadErr("Usa um e-mail corporativo (sem gmail/hotmail/outlook). Ajuda a gente a te atender melhor.");
      return;
    }
    if (!empresa || empresa.length < 2) {
      form.querySelector('[name=empresa]').classList.add("err");
      showLeadErr("Qual o nome da empresa?");
      return;
    }

    // UTM/attribution salvo no localStorage da landing
    var utmData = null;
    try {
      var raw = localStorage.getItem("dfeaxis_attribution");
      if (raw) utmData = JSON.parse(raw);
    } catch (e) {}

    elements.leadBtn.disabled = true;
    elements.leadBtn.textContent = "Enviando…";

    fetch(API_URL + "/api/v1/chat/landing/lead", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: email,
        nome: nome,
        empresa: empresa,
        telefone: telefone || null,
        session_id: getSessionId(),
        page_url: window.location.pathname + window.location.search,
        utm_data: utmData,
      }),
    })
      .then(function (res) {
        return res.json().then(function (body) {
          if (!res.ok) throw new Error(body.detail || ("HTTP " + res.status));
          return body;
        });
      })
      .then(function (body) {
        // Salva lead no localStorage pra não pedir de novo
        try {
          localStorage.setItem(STORAGE_LEAD, JSON.stringify({
            email: email, nome: nome, empresa: empresa,
            conversation_id: body.conversation_id,
            at: new Date().toISOString(),
          }));
        } catch (e) {}
        state.leadCaptured = true;
        state.conversationId = body.conversation_id;
        state.messages = [{
          role: "assistant",
          content: "Valeu, " + nome.split(" ")[0] + "! Agora me conta: qual ERP vocês usam hoje, e tá avaliando o DFeAxis pra qual cenário?",
        }];
        transitionToChat();
        // Dispara evento de conversão (landing GA4 + Ads se tiver)
        try {
          if (typeof window.DFEAXIS_CONVERT === "function") {
            window.DFEAXIS_CONVERT("chat_lead_captured", { value: 80, email_domain: domain });
          }
        } catch (e) {}
      })
      .catch(function (err) {
        elements.leadBtn.disabled = false;
        elements.leadBtn.textContent = "Começar conversa →";
        var msg = err && err.message ? err.message : "Não rolou enviar. Tenta de novo?";
        showLeadErr(msg);
      });
  }

  function transitionToChat() {
    if (elements.leadForm) elements.leadForm.style.display = "none";
    if (elements.messagesBox) elements.messagesBox.style.display = "flex";
    if (elements.inputWrap) elements.inputWrap.style.display = "block";
    renderMessages();
    setTimeout(function () {
      if (elements.input) elements.input.focus();
    }, 100);
  }

  function renderMessages() {
    if (!elements.messagesBox) return;
    elements.messagesBox.innerHTML = "";
    state.messages.forEach(function (msg) {
      var div = document.createElement("div");
      div.className =
        "dfeax-chat-msg " +
        (msg.role === "user" ? "dfeax-chat-msg-user" : "dfeax-chat-msg-assistant");
      div.textContent = msg.content;
      elements.messagesBox.appendChild(div);
    });
    if (state.loading) {
      var typing = document.createElement("div");
      typing.className = "dfeax-chat-typing";
      typing.textContent = "Digitando...";
      elements.messagesBox.appendChild(typing);
    }
    elements.messagesBox.scrollTop = elements.messagesBox.scrollHeight;
  }

  function openPanel() {
    state.open = true;
    elements.btn.style.display = "none";
    elements.panel.style.display = "flex";
    if (!state.leadCaptured) {
      // Mostra form de lead, esconde chat
      if (elements.leadForm) elements.leadForm.style.display = "flex";
      if (elements.messagesBox) elements.messagesBox.style.display = "none";
      if (elements.inputWrap) elements.inputWrap.style.display = "none";
      setTimeout(function () {
        var first = elements.leadForm && elements.leadForm.querySelector('input[name=nome]');
        if (first) first.focus();
      }, 120);
    } else {
      // Já tem lead, vai direto pro chat
      if (elements.leadForm) elements.leadForm.style.display = "none";
      if (elements.messagesBox) elements.messagesBox.style.display = "flex";
      if (elements.inputWrap) elements.inputWrap.style.display = "block";
      renderMessages();
      setTimeout(function () {
        elements.input && elements.input.focus();
      }, 100);
    }
  }

  function closePanel() {
    state.open = false;
    elements.panel.style.display = "none";
    elements.btn.style.display = "flex";
  }

  function sendMessage() {
    var text = (elements.input.value || "").trim();
    if (!text || state.loading) return;

    state.messages.push({ role: "user", content: text });
    elements.input.value = "";
    state.loading = true;
    elements.sendBtn.disabled = true;
    renderMessages();

    var payload = {
      messages: state.messages,
      conversation_id: state.conversationId,
      session_id: getSessionId(),
      page_url: window.location.pathname,
    };

    fetch(API_URL + "/api/v1/chat/landing", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(function (data) {
        state.conversationId = data.conversation_id;
        state.messages.push({ role: "assistant", content: data.message });
      })
      .catch(function (err) {
        console.error("DFeAxis chat error", err);
        state.messages.push({
          role: "assistant",
          content:
            "Desculpa, tive um problema pra processar sua mensagem. Pode tentar novamente em alguns instantes?",
        });
      })
      .finally(function () {
        state.loading = false;
        elements.sendBtn.disabled = false;
        renderMessages();
      });
  }

  // ---------- Init ----------
  function init() {
    injectStyle();
    elements.btn = createButton();
    elements.panel = createPanel();
    document.body.appendChild(elements.btn);
    document.body.appendChild(elements.panel);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
