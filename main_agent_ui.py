import gradio as gr
import os
import uuid
import shutil
import base64
import mimetypes
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langgraph.errors import GraphRecursionError
from agent import build_workflow
from tools.rag import reset_vectorstore

load_dotenv()
# UI 모드에서는 agent.py 내부 stdout 스트리밍 출력 비활성화
os.environ["USE_STREAMING"] = "false"

workflow = build_workflow()

# 앱 실행 단위의 단일 세션 ID (멀티유저 확장 시 gr.State로 교체)
_SESSION_THREAD_ID = str(uuid.uuid4())

_DOCS_DIR      = os.path.join(os.path.dirname(__file__), "Docs")
_WORKSPACE_DIR = os.path.join(os.path.dirname(__file__), "workspace")

_TEXT_EXTENSIONS  = {".txt", ".md", ".py", ".js", ".ts", ".json", ".csv", ".yaml", ".yml", ".toml", ".html", ".xml"}
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
_AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac"}
_VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}

_MAX_TEXT_CHARS = 4000

_STATUS_MSG = {
    "rag_node":        "🔍 내부 문서(Docs)에서 관련 정보를 탐색 중입니다...",
    "web_search_node": "🌐 인터넷에서 최신 정보를 검색 중입니다...",
    "other_tools_node":"🛠️ 외부 도구를 실행 중입니다...",
    "tools":           "⚙️ 도구 실행 완료, 결과를 분석합니다...",
    "generate_node":   "✍️ 답변을 생성 중입니다...",
    "direct_chat_node":"✍️ 답변을 생성 중입니다...",
}

_AI_OUTPUT_NODES = {"generate_node", "direct_chat_node", "other_tools_node", "rag_node"}


def _process_attachments(files: list) -> tuple[str, list]:
    """첨부 파일을 분류·처리한다.

    Returns:
        text_context : PDF/텍스트 처리 결과를 메시지에 붙일 문자열
        media_files  : 멀티모달 분석 대상 파일 경로 목록 (이미지·음성·영상)
    """
    text_parts = []
    media_files = []
    pdf_added = False

    for file_path in files:
        filename = os.path.basename(file_path)
        ext = os.path.splitext(filename)[1].lower()

        if ext == ".pdf":
            os.makedirs(_DOCS_DIR, exist_ok=True)
            shutil.copy(file_path, os.path.join(_DOCS_DIR, filename))
            text_parts.append(
                f"[📄 PDF 첨부: '{filename}'이 Docs 폴더에 저장되었습니다. "
                "RAG 검색을 통해 이 문서의 내용을 물어볼 수 있습니다.]"
            )
            pdf_added = True

        elif ext in _TEXT_EXTENSIONS:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read(_MAX_TEXT_CHARS)
                note = f"\n*(앞 {_MAX_TEXT_CHARS}자만 표시)*" if len(content) == _MAX_TEXT_CHARS else ""
                text_parts.append(f"[📎 첨부 파일: {filename}]{note}\n```\n{content}\n```")
            except Exception as e:
                text_parts.append(f"[📎 첨부 파일: {filename} — 읽기 실패: {e}]")

        elif ext in (_IMAGE_EXTENSIONS | _AUDIO_EXTENSIONS | _VIDEO_EXTENSIONS):
            # 멀티모달 분석 대상으로 분류 (LLM에 직접 전달)
            media_files.append(file_path)

        else:
            os.makedirs(_WORKSPACE_DIR, exist_ok=True)
            shutil.copy(file_path, os.path.join(_WORKSPACE_DIR, filename))
            text_parts.append(
                f"[📁 파일 첨부: '{filename}'이 workspace 폴더에 저장되었습니다. "
                f"경로: workspace/{filename}]"
            )

    if pdf_added:
        reset_vectorstore()

    return "\n\n".join(text_parts), media_files


def _build_human_message(text: str, media_files: list, provider: str) -> HumanMessage:
    """텍스트와 미디어 파일을 합쳐 HumanMessage를 생성한다.

    - 이미지   : 모든 프로바이더 (base64 image_url)
    - 음성/영상 : Gemini는 media 블록으로 전달, 나머지는 지원 불가 안내 텍스트로 대체
    """
    if not media_files:
        return HumanMessage(content=text)

    # 미디어가 있을 때 텍스트가 비어 있으면 기본 프롬프트 사용
    display_text = text if text.strip() else "첨부한 파일을 분석해주세요."
    content_blocks: list = [{"type": "text", "text": display_text}]

    for file_path in media_files:
        filename = os.path.basename(file_path)
        ext = os.path.splitext(filename)[1].lower()
        mime_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"

        if ext in _IMAGE_EXTENSIONS:
            with open(file_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            content_blocks.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{b64}"},
            })

        elif ext in (_AUDIO_EXTENSIONS | _VIDEO_EXTENSIONS):
            if provider == "gemini":
                with open(file_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("utf-8")
                content_blocks.append({
                    "type": "media",
                    "data": b64,
                    "mime_type": mime_type,
                })
            else:
                media_label = "음성" if ext in _AUDIO_EXTENSIONS else "영상"
                content_blocks.append({
                    "type": "text",
                    "text": (
                        f"[⚠️ {media_label} 파일 '{filename}'이 첨부되었으나 "
                        f"현재 프로바이더({provider})는 {media_label} 분석을 지원하지 않습니다. "
                        "Gemini 프로바이더로 전환하면 분석이 가능합니다.]"
                    ),
                })

    return HumanMessage(content=content_blocks)


def respond(message, _history: list):
    # multimodal=True 일 때 message는 {"text": str, "files": [...]} 형태
    text  = message["text"]  if isinstance(message, dict) else message
    files = message.get("files", []) if isinstance(message, dict) else []

    text_context, media_files = _process_attachments(files)
    full_text = f"{text}\n\n{text_context}".strip() if text_context else text

    if not full_text and not media_files:
        yield "메시지를 입력하거나 파일을 첨부해주세요."
        return

    provider = os.getenv("LLM_PROVIDER", "ollama").lower()
    human_message = _build_human_message(full_text, media_files, provider)

    config = {
        "configurable": {"thread_id": _SESSION_THREAD_ID},
        "recursion_limit": 5,
    }

    try:
        events = workflow.stream(
            {"messages": [human_message]},
            config=config,
            stream_mode="updates",
        )

        final_response = ""

        for event in events:
            for node_name, state_update in event.items():
                if node_name in _STATUS_MSG:
                    yield _STATUS_MSG[node_name]

                if node_name in _AI_OUTPUT_NODES and "messages" in state_update:
                    msgs = state_update["messages"]
                    if not isinstance(msgs, list):
                        msgs = [msgs]
                    for msg in msgs:
                        if hasattr(msg, "type") and msg.type == "ai" and msg.content:
                            final_response = msg.content
                            yield final_response

        if not final_response:
            yield "응답을 생성하지 못했습니다."

    except GraphRecursionError:
        yield "에이전트의 최대 탐색 횟수(recursion_limit)를 초과하여 대화를 종료합니다."
    except Exception as e:
        yield f"오류가 발생했습니다: {e}"


def _model_info() -> str:
    provider = os.getenv("LLM_PROVIDER", "ollama").lower()
    if provider == "ollama":
        return f"Ollama / {os.getenv('OLLAMA_MODEL', 'gemma4:e4b')}"
    if provider == "openai":
        return "OpenAI / gpt-4o"
    if provider == "gemini":
        return "Gemini / gemini-1.5-pro"
    return provider


demo = gr.ChatInterface(
    fn=respond,
    multimodal=True,
    title="🤖 MyAgent",
    description=(
        f"LangGraph 기반 AI 에이전트 &nbsp;|&nbsp; Provider: **{_model_info()}**\n\n"
        "내부 문서 검색(RAG) · 웹 검색 · 파일 읽기/쓰기를 지원합니다.\n"
        "📎 **PDF** → RAG 인덱스 자동 추가 &nbsp;|&nbsp; "
        "🖼️ **이미지** → 멀티모달 분석 &nbsp;|&nbsp; "
        "🎵 **음성/영상** → Gemini 프로바이더에서 분석 가능"
    ),
    examples=[
        {"text": "안녕하세요! 무엇을 도와드릴까요?"},
        {"text": "최신 AI 뉴스를 검색해주세요"},
        {"text": "Docs 폴더에 있는 문서를 요약해주세요"},
    ],
    chatbot=gr.Chatbot(
        height=520,
        render_markdown=True,
        placeholder="<b>MyAgent</b>에게 무엇이든 물어보세요. 파일을 첨부할 수도 있습니다.",
    ),
    submit_btn="전송",
    stop_btn="중지",
)

if __name__ == "__main__":
    info = _model_info()
    print("========================================")
    print("MyAgent UI Started!")
    print(f"Provider: {info}")
    print("URL: http://localhost:7860")
    print("========================================")
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        inbrowser=True,
    )
