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

// ── 发送消息（流式版本）─────────────────────────────────────────────────────────
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

  // 创建助手消息气泡（内容先为空，流式填充）
  const assistantMsg = appendMessage("assistant", "");
  const bubble = assistantMsg.querySelector(".bubble");
  let fullText = "";

  try {
    const res = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, history: history.slice(0, -1) }),
    });

    if (!res.ok) {
      const err = await res.json();
      bubble.innerHTML = marked.parse("⚠️ 请求出错：" + (err.error || "未知错误"));
      setLoading(false);
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // 解析 SSE 消息（以 "data: " 开头，以 \n\n 结束）
      const lines = buffer.split("\n\n");
      buffer = lines.pop(); // 最后一段可能不完整，留在 buffer

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const jsonStr = line.slice(6); // 去掉 "data: "

        try {
          const event = JSON.parse(jsonStr);

          if (event.type === "text") {
            fullText += event.text;
            bubble.innerHTML = marked.parse(fullText);
            scrollToBottom();
          } else if (event.type === "done") {
            // 添加来源标签
            if (event.sources && event.sources.length > 0) {
              const sourcesEl = document.createElement("div");
              sourcesEl.className = "sources";
              event.sources.forEach((src) => {
                const tag = document.createElement("span");
                tag.className = "source-tag";
                tag.textContent = "📄 " + src;
                sourcesEl.appendChild(tag);
              });
              assistantMsg.appendChild(sourcesEl);
            }
            history.push({ role: "assistant", content: fullText });
          } else if (event.type === "error") {
            bubble.innerHTML = marked.parse("⚠️ " + event.message);
          }
        } catch (e) {
          // JSON 解析失败，跳过
        }
      }
    }
  } catch (err) {
    bubble.innerHTML = marked.parse("⚠️ 网络错误，请检查服务是否启动。");
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
    bubble.innerHTML = text ? marked.parse(text) : "";
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

function setLoading(isLoading) {
  sendBtn.disabled = isLoading;
  inputEl.disabled = isLoading;
}

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}
