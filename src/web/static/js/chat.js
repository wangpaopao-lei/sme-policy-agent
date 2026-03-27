// 对话历史，格式与 agent.chat() 的 history 参数一致
const history = [];

const messagesEl = document.getElementById("messages");
const inputEl    = document.getElementById("input");
const sendBtn    = document.getElementById("send-btn");

// ── 自动撑高 textarea ──────────────────────────────────────────────────────────
inputEl.addEventListener("input", () => {
  inputEl.style.height = "auto";
  inputEl.style.height = Math.min(inputEl.scrollHeight, 140) + "px";
});

// Enter 发送，Shift+Enter 换行
inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

// ── 示例问题按钮 ───────────────────────────────────────────────────────────────
function sendExample(btn) {
  inputEl.value = btn.textContent.trim();
  sendMessage();
}

// ── 发送消息 ───────────────────────────────────────────────────────────────────
async function sendMessage() {
  const text = inputEl.value.trim();
  if (!text || sendBtn.disabled) return;

  // 隐藏欢迎区
  const welcome = document.getElementById("welcome");
  if (welcome) welcome.remove();

  appendMessage("user", text);
  history.push({ role: "user", content: text });

  inputEl.value = "";
  inputEl.style.height = "auto";
  setLoading(true);

  const loadingEl = appendLoading();

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, history: history.slice(0, -1) }),
    });

    const data = await res.json();
    loadingEl.remove();

    if (data.error) {
      appendMessage("assistant", "⚠️ 请求出错：" + data.error);
    } else {
      appendMessage("assistant", data.answer, data.sources || []);
      history.push({ role: "assistant", content: data.answer });
    }
  } catch (err) {
    loadingEl.remove();
    appendMessage("assistant", "⚠️ 网络错误，请检查服务是否启动。");
  } finally {
    setLoading(false);
  }
}

// ── DOM 辅助函数 ───────────────────────────────────────────────────────────────
function appendMessage(role, text, sources = []) {
  const msg = document.createElement("div");
  msg.className = `message ${role}`;

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  if (role === "assistant") {
    bubble.innerHTML = marked.parse(text);
  } else {
    bubble.textContent = text;
  }
  msg.appendChild(bubble);

  if (sources.length > 0) {
    const sourcesEl = document.createElement("div");
    sourcesEl.className = "sources";
    sources.forEach((src) => {
      const tag = document.createElement("span");
      tag.className = "source-tag";
      tag.textContent = "📄 " + src;
      sourcesEl.appendChild(tag);
    });
    msg.appendChild(sourcesEl);
  }

  messagesEl.appendChild(msg);
  scrollToBottom();
  return msg;
}

function appendLoading() {
  const msg = document.createElement("div");
  msg.className = "message assistant";

  const bubble = document.createElement("div");
  bubble.className = "bubble loading-bubble";
  bubble.innerHTML = "<span></span><span></span><span></span>";
  msg.appendChild(bubble);

  messagesEl.appendChild(msg);
  scrollToBottom();
  return msg;
}

function setLoading(isLoading) {
  sendBtn.disabled = isLoading;
  inputEl.disabled = isLoading;
}

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}
