// Shared CCS Assistant chat logic (persistence + send + render)
// - Stores messages in localStorage keyed by user_id
// - Exposes global window.sendQuery() and window.downloadSource() for existing templates

(function () {
  const MAX_MESSAGES = 60;
  const DEFAULT_GREETING =
    "Hello! I am your web guide. How can I help you today?";

  function getMeta(name) {
    const el = document.querySelector(`meta[name="${name}"]`);
    return el ? el.content : "";
  }

  function safeJsonParse(raw) {
    try {
      return JSON.parse(raw);
    } catch (_) {
      return null;
    }
  }

  function init() {
    const userId = getMeta("user-id");
    const apiUrl = getMeta("api-url");
    const downloadUrl = getMeta("download-url");

    const chatMessages = document.getElementById("chat-messages");
    const chatInput = document.getElementById("chat-input");

    if (!userId || !chatMessages || !chatInput) return;

    const storageKey = `ccs_chat_history_${userId}`;
    let isHydrating = false;

    function loadHistory() {
      const raw = localStorage.getItem(storageKey);
      const parsed = raw ? safeJsonParse(raw) : [];
      return Array.isArray(parsed) ? parsed : [];
    }

    function saveHistory(history) {
      try {
        localStorage.setItem(storageKey, JSON.stringify(history.slice(-MAX_MESSAGES)));
      } catch (_) {
        // ignore quota / blocked storage
      }
    }

    function pushMessageToHistory(entry) {
      if (isHydrating) return;
      const history = loadHistory();
      history.push(entry);
      saveHistory(history);
    }

    function appendMessage(content, sender, isHtml = false, skipStore = false) {
      const msg = document.createElement("div");
      msg.style.padding = "10px";
      msg.style.borderRadius = "8px";
      msg.style.maxWidth = "85%";
      msg.style.overflowWrap = "break-word";
      msg.style.wordBreak = "break-word";

      if (sender === "user") {
        msg.style.background = "#005ea5";
        msg.style.color = "white";
        msg.style.alignSelf = "flex-end";
        msg.textContent = content;
      } else {
        msg.style.background = "#f3f2f1";
        msg.style.alignSelf = "flex-start";
        if (isHtml) msg.innerHTML = content;
        else msg.textContent = content;
      }

      chatMessages.appendChild(msg);
      chatMessages.scrollTop = chatMessages.scrollHeight;

      if (!skipStore) {
        pushMessageToHistory({ sender, content, isHtml });
      }
    }

    function hydrateChat() {
      isHydrating = true;
      chatMessages.innerHTML = "";
      const history = loadHistory();
      // Always show the greeting at the top (do not store it in history).
      appendMessage(DEFAULT_GREETING, "bot", false, true);

      // Render the stored conversation below. (Greeting is not stored.)
      history.forEach((m) => appendMessage(m.content, m.sender, !!m.isHtml, true));
      chatMessages.scrollTop = chatMessages.scrollHeight;
      isHydrating = false;
    }

    async function downloadSource(fileName) {
      if (!downloadUrl) return;
      try {
        const resp = await fetch(`${downloadUrl}/${encodeURIComponent(fileName)}`);
        const data = await resp.json();
        const hiddenLink = document.createElement("a");
        hiddenLink.href = data.download_url;
        hiddenLink.setAttribute("download", fileName);
        document.body.appendChild(hiddenLink);
        hiddenLink.click();
        document.body.removeChild(hiddenLink);
      } catch (e) {
        console.error("Download Error:", e);
      }
    }

    async function sendQuery() {
      const query = (chatInput.value || "").trim();
      if (!query) return;

      appendMessage(query, "user", false);
      chatInput.value = "";

      if (!apiUrl) {
        appendMessage("Chat backend is not configured.", "bot", false);
        return;
      }

      try {
        const resp = await fetch(apiUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ user_id: userId, query }),
        });

        const data = await resp.json();
        let responseHTML = `<div class="msg-content">${data.AI_response}</div>`;

        if (data.source_content && data.source_content.length > 0) {
          responseHTML += `
            <div style="border-top: 1px solid #ddd; padding-top: 10px; margin-top: 10px;">
              <p style="font-size: 11px; font-weight: bold; color: #666; margin-bottom: 5px;">SOURCES:</p>
              <div style="display: flex; flex-direction: column; gap: 5px;">
                ${data.source_content
                  .map(
                    (source) =>
                      `<button onclick="downloadSource('${source}')" class="download-btn">📥 ${source}</button>`
                  )
                  .join("")}
              </div>
            </div>`;
        }

        appendMessage(responseHTML, "bot", true);
      } catch (e) {
        appendMessage("Error connecting to AI service.", "bot", false);
      }
    }

    // expose for inline onclick handlers
    window.sendQuery = sendQuery;
    window.downloadSource = downloadSource;

    // Enter-to-send
    chatInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        sendQuery();
      }
    });

    hydrateChat();
  }

  window.addEventListener("DOMContentLoaded", init);
})();

