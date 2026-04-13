/**
 * DFeAxis Chat Widget — versão vanilla JS pra landing estática.
 * Não tem dependências. Injeta um botão flutuante + modal de chat.
 * Consome POST /api/v1/chat/landing no backend.
 */
(function () {
  var API_URL = "https://api.dfeaxis.com.br";
  var STORAGE_KEY = "dfeaxis:chat_session";
  var STORAGE_CONV = "dfeaxis:chat_conv";

  // Não carregar no dashboard (tem o React widget próprio)
  if (window.location.pathname.startsWith("/dashboard")) return;
  if (window.location.pathname.startsWith("/cadastros")) return;
  if (window.location.pathname.startsWith("/historico")) return;
  if (window.location.pathname.startsWith("/logs")) return;
  if (window.location.pathname.startsWith("/financeiro")) return;
  if (window.location.pathname.startsWith("/execucao")) return;
  if (window.location.pathname.startsWith("/getting-started")) return;

  // ---------- State ----------
  var state = {
    open: false,
    messages: [
      {
        role: "assistant",
        content:
          "Oi! Sou o assistente do DFeAxis. Posso tirar dúvidas sobre captura automática de NF-e, integração com seu ERP, planos ou o trial. Por onde quer começar?",
      },
    ],
    loading: false,
    conversationId: null,
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
  bottom: 88px;
  right: 24px;
  z-index: 9999;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 20px;
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
    /* Mobile: sticky-bar é menor, ~52px. Margem 16 + 52 = 68 */
    bottom: 76px;
    right: 16px;
    padding: 10px 16px;
    font-size: 13px;
  }
}
.dfeax-chat-panel {
  position: fixed;
  /* Fica acima da sticky-bar da landing (mesmo cálculo do botão) */
  bottom: 88px;
  right: 24px;
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
    bottom: 76px;
    right: 16px;
    max-width: calc(100vw - 32px);
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
      '<div class="dfeax-chat-messages"></div>' +
      '<div class="dfeax-chat-input-wrap">' +
      '<div class="dfeax-chat-input-row">' +
      '<textarea class="dfeax-chat-input" rows="2" placeholder="Escreva sua mensagem..."></textarea>' +
      '<button class="dfeax-chat-send" type="button">Enviar</button>' +
      "</div>" +
      '<div class="dfeax-chat-footer">Este chat é gravado para melhorar o atendimento. Powered by Claude.</div>' +
      "</div>";

    panel.querySelector(".dfeax-chat-close").addEventListener("click", closePanel);

    var input = panel.querySelector(".dfeax-chat-input");
    var sendBtn = panel.querySelector(".dfeax-chat-send");

    sendBtn.addEventListener("click", sendMessage);
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });

    elements.panel = panel;
    elements.messagesBox = panel.querySelector(".dfeax-chat-messages");
    elements.input = input;
    elements.sendBtn = sendBtn;
    return panel;
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
    renderMessages();
    setTimeout(function () {
      elements.input && elements.input.focus();
    }, 100);
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
