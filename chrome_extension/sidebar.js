const SERVER_URL = "http://localhost:8000";
const THREAD_ID_KEY = "myagent_thread_id";

let threadId = "";
let isStreaming = false;
let pageContext = null; // 현재 읽어온 페이지 컨텍스트

// ── 초기화 ──────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", async () => {
  threadId = await loadOrCreateThreadId();
  await checkServerStatus();
  setupEventListeners();
  autoResizeTextarea();
});

async function loadOrCreateThreadId() {
  return new Promise((resolve) => {
    chrome.storage.local.get([THREAD_ID_KEY], (result) => {
      if (result[THREAD_ID_KEY]) {
        resolve(result[THREAD_ID_KEY]);
      } else {
        const id = crypto.randomUUID();
        chrome.storage.local.set({ [THREAD_ID_KEY]: id });
        resolve(id);
      }
    });
  });
}

// ── 서버 상태 확인 ────────────────────────────────────────

async function checkServerStatus() {
  const el = document.getElementById("server-status");
  try {
    const res = await fetch(`${SERVER_URL}/health`, { signal: AbortSignal.timeout(3000) });
    if (res.ok) {
      el.textContent = "✅ 서버 연결됨 (localhost:8000)";
      el.className = "server-status connected";
      setTimeout(() => el.classList.add("hidden"), 3000);
    } else {
      throw new Error();
    }
  } catch {
    el.textContent = "❌ 서버 연결 실패 — python main_agent_server.py 를 실행해주세요.";
    el.className = "server-status disconnected";
  }
}

// ── 페이지 DOM 읽기 ───────────────────────────────────────

async function readPageContent() {
  const btn = document.getElementById("read-page-btn");
  btn.textContent = "⏳";
  btn.disabled = true;

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab) throw new Error("활성 탭을 찾을 수 없습니다.");

    const response = await chrome.tabs.sendMessage(tab.id, { action: "getPageContent" });
    if (!response) throw new Error("페이지에서 응답이 없습니다.");

    pageContext = response;
    showPageContextBar(response);

  } catch (err) {
    alert(`페이지 읽기 실패: ${err.message}\n\n이 페이지는 확장 프로그램 접근이 제한되어 있을 수 있습니다.`);
  } finally {
    btn.textContent = "📄";
    btn.disabled = false;
  }
}

function showPageContextBar(ctx) {
  const bar   = document.getElementById("page-context-bar");
  const label = document.getElementById("page-context-label");

  const source = ctx.selectedText
    ? `✂️ 선택 텍스트 (${ctx.selectedText.length}자)`
    : `📄 ${ctx.title || ctx.url} (${ctx.bodyText.length}자)`;

  label.textContent = source;
  bar.classList.remove("hidden");
}

function clearPageContext() {
  pageContext = null;
  document.getElementById("page-context-bar").classList.add("hidden");
}

function buildMessageWithContext(userText) {
  if (!pageContext) return userText;

  const ctx = pageContext;
  const content = ctx.selectedText || ctx.bodyText;
  const source  = ctx.selectedText ? "선택한 텍스트" : "페이지 본문";

  return (
    `[현재 브라우저 페이지 컨텍스트]\n` +
    `URL: ${ctx.url}\n` +
    `제목: ${ctx.title}\n` +
    `${source}:\n"""\n${content}\n"""\n\n` +
    `위 내용을 참고하여 다음 질문에 답해주세요:\n${userText}`
  );
}

// ── 이벤트 리스너 ──────────────────────────────────────────

function setupEventListeners() {
  const sendBtn     = document.getElementById("send-btn");
  const input       = document.getElementById("input");
  const clearBtn    = document.getElementById("clear-btn");
  const checkBtn    = document.getElementById("server-check-btn");
  const readPageBtn = document.getElementById("read-page-btn");
  const ctxClear    = document.getElementById("page-context-clear");

  sendBtn.addEventListener("click", sendMessage);
  checkBtn.addEventListener("click", checkServerStatus);
  readPageBtn.addEventListener("click", readPageContent);
  ctxClear.addEventListener("click", clearPageContext);

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  input.addEventListener("input", autoResizeTextarea);

  clearBtn.addEventListener("click", () => {
    if (confirm("대화 내용을 초기화할까요?")) {
      document.getElementById("messages").innerHTML = "";
      clearPageContext();
      const id = crypto.randomUUID();
      threadId = id;
      chrome.storage.local.set({ [THREAD_ID_KEY]: id });
    }
  });
}

function autoResizeTextarea() {
  const el = document.getElementById("input");
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 120) + "px";
}

// ── 메시지 전송 ────────────────────────────────────────────

async function sendMessage() {
  if (isStreaming) return;

  const input = document.getElementById("input");
  const userText = input.value.trim();
  if (!userText) return;

  input.value = "";
  autoResizeTextarea();

  // 사용자에게 보여줄 텍스트 (컨텍스트 미포함)
  appendMessage("user", userText);
  // 에이전트에 전달할 텍스트 (컨텍스트 포함)
  const fullMessage = buildMessageWithContext(userText);

  // 페이지 컨텍스트는 1회 사용 후 유지 (사용자가 명시적으로 지워야 함)
  setStreaming(true);

  const agentEl  = appendMessage("agent", "");
  const bubble   = agentEl.querySelector(".bubble");
  const statusBar = document.getElementById("status-bar");

  let finalAnswer = "";

  try {
    const res = await fetch(`${SERVER_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: fullMessage, thread_id: threadId }),
    });

    if (!res.ok) throw new Error(`서버 오류: ${res.status}`);

    const reader  = res.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n\n");
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        try {
          const payload = JSON.parse(line.slice(6));
          handleSSE(payload, bubble, statusBar);
          if (payload.type === "answer") finalAnswer = payload.content;
        } catch { /* JSON 파싱 실패 무시 */ }
      }
    }
  } catch (err) {
    bubble.innerHTML = renderMarkdown(`❌ 오류: ${err.message}`);
  } finally {
    statusBar.textContent = "";
    statusBar.classList.add("hidden");
    if (!finalAnswer && !bubble.innerHTML) {
      bubble.innerHTML = renderMarkdown("응답을 생성하지 못했습니다.");
    }
    setStreaming(false);
    scrollToBottom();
  }
}

function handleSSE(payload, bubble, statusBar) {
  switch (payload.type) {
    case "status":
      statusBar.textContent = payload.content;
      statusBar.classList.remove("hidden");
      break;
    case "answer":
      statusBar.classList.add("hidden");
      bubble.innerHTML = renderMarkdown(payload.content);
      scrollToBottom();
      break;
    case "error":
      statusBar.classList.add("hidden");
      bubble.innerHTML = renderMarkdown(`❌ ${payload.content}`);
      scrollToBottom();
      break;
    case "done":
      statusBar.classList.add("hidden");
      break;
  }
}

// ── UI 유틸 ───────────────────────────────────────────────

function appendMessage(role, text) {
  const wrap = document.createElement("div");
  wrap.className = `message ${role}`;

  const label = document.createElement("div");
  label.className = "sender-label";
  label.textContent = role === "user" ? "나" : "Agent";

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  if (text) bubble.innerHTML = renderMarkdown(text);

  wrap.appendChild(label);
  wrap.appendChild(bubble);
  document.getElementById("messages").appendChild(wrap);
  scrollToBottom();
  return wrap;
}

function scrollToBottom() {
  const msgs = document.getElementById("messages");
  msgs.scrollTop = msgs.scrollHeight;
}

function setStreaming(val) {
  isStreaming = val;
  document.getElementById("send-btn").disabled = val;
  document.getElementById("input").disabled = val;
}

// ── 마크다운 렌더러 (간이) ────────────────────────────────

function renderMarkdown(text) {
  text = text.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    const escaped = escapeHtml(code.trim());
    return `<pre><code class="language-${lang}">${escaped}</code></pre>`;
  });
  text = text.replace(/`([^`\n]+)`/g, (_, c) => `<code>${escapeHtml(c)}</code>`);
  text = text.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  text = text.replace(/\*(.+?)\*/g, "<em>$1</em>");
  text = text.replace(/^[-•] (.+)$/gm, "<li>$1</li>");
  text = text.replace(/(<li>.*<\/li>)/s, "<ul>$1</ul>");
  text = text.replace(/^\d+\. (.+)$/gm, "<li>$1</li>");
  text = text.replace(/\n/g, "<br>");
  return text;
}

function escapeHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
