// 사이드패널(sidebar.js)의 요청을 받아 현재 페이지 DOM을 읽어 반환한다.

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "getPageContent") {
    sendResponse(extractPageContent());
  }
  return true; // 비동기 응답을 위해 채널 유지
});

function extractPageContent() {
  const selectedText = window.getSelection().toString().trim();

  // 본문 우선순위: 선택 텍스트 → 시맨틱 태그 → body 전체
  let bodyText = "";
  if (selectedText) {
    bodyText = selectedText;
  } else {
    const candidates = [
      "article",
      "main",
      "[role='main']",
      ".article-body",
      ".post-content",
      ".entry-content",
      "#content",
      ".content",
    ];
    for (const sel of candidates) {
      const el = document.querySelector(sel);
      if (el && el.innerText.trim().length > 300) {
        bodyText = el.innerText.trim();
        break;
      }
    }
    if (!bodyText) {
      bodyText = document.body.innerText.trim();
    }
  }

  return {
    url: location.href,
    title: document.title,
    selectedText,
    bodyText: bodyText.slice(0, 8000), // 최대 8000자
    metaDescription:
      document.querySelector('meta[name="description"]')?.content || "",
  };
}
