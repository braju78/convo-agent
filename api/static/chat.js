// Persist conversation_id across page reloads via localStorage.
const CONV_KEY = "convo_agent_conversation_id";

function updateConvBadge(id) {
  const badge = document.getElementById("conv-badge");
  if (!badge) return;
  if (id) {
    badge.textContent = id.slice(0, 8);
    badge.classList.remove("muted");
    badge.classList.add("active");
  } else {
    badge.textContent = "no conversation";
    badge.classList.remove("active");
    badge.classList.add("muted");
  }
}

function setConversationId(id) {
  if (id) {
    localStorage.setItem(CONV_KEY, id);
  } else {
    localStorage.removeItem(CONV_KEY);
  }
  document.getElementById("conversation_id").value = id || "";
  updateConvBadge(id);
}

function startNewConversation() {
  setConversationId(null);
  document.getElementById("messages").innerHTML = "";
  document.getElementById("message-input").focus();
}

function scrollToBottom() {
  const box = document.getElementById("messages");
  box.scrollTop = box.scrollHeight;
}

function onBeforeSend(event) {
  const input = document.getElementById("message-input");
  const text = input.value.trim();
  if (!text) return;

  // Optimistically render the user bubble; server response includes the
  // canonical user + assistant pair (so we remove the optimistic bubble
  // right before the server-appended pair lands).
  const messages = document.getElementById("messages");
  const optimistic = document.createElement("div");
  optimistic.className = "message user optimistic";
  optimistic.innerHTML = `<div class="bubble">${escapeHtml(text)}</div>`;
  messages.appendChild(optimistic);

  const pending = document.createElement("div");
  pending.className = "message assistant pending";
  pending.innerHTML = `<div class="bubble"></div>`;
  messages.appendChild(pending);

  scrollToBottom();
}

function onAfterSend(event) {
  // Strip optimistic bubbles — server response contains canonical pair.
  document
    .querySelectorAll(".message.optimistic, .message.pending")
    .forEach((el) => el.remove());

  // Pick up any conversation_id emitted by the server fragment.
  const meta = document.getElementById("conv-meta");
  if (meta) {
    const id = meta.dataset.conversationId;
    if (id) setConversationId(id);
  }

  document.getElementById("message-input").value = "";
  document.getElementById("message-input").focus();
  scrollToBottom();
}

function escapeHtml(s) {
  return s
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

// Restore conversation_id on page load.
document.addEventListener("DOMContentLoaded", () => {
  const stored = localStorage.getItem(CONV_KEY);
  if (stored) setConversationId(stored);

  // Cmd/Ctrl+Enter to submit; plain Enter inserts newline.
  const input = document.getElementById("message-input");
  input.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      document.getElementById("chat-form").requestSubmit();
    }
  });
});
