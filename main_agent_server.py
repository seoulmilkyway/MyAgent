import os
import json
import asyncio
import threading
from queue import Queue as SyncQueue

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from langgraph.errors import GraphRecursionError
from pydantic import BaseModel

from agent import build_workflow

load_dotenv()
os.environ["USE_STREAMING"] = "false"

app = FastAPI(title="MyAgent Server")

# Chrome Extension은 chrome-extension:// origin으로 요청하므로 전체 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

print("[Server] Initializing workflow...")
workflow = build_workflow()
print("[Server] Workflow ready.")

_STATUS_MSG = {
    "rag_node":        "🔍 내부 문서에서 탐색 중...",
    "web_search_node": "🌐 웹 검색 중...",
    "other_tools_node":"🛠️ 도구 실행 중...",
    "tools":           "⚙️ 도구 결과 분석 중...",
    "generate_node":   "✍️ 답변 생성 중...",
    "direct_chat_node":"✍️ 답변 생성 중...",
}

_AI_OUTPUT_NODES = {"generate_node", "direct_chat_node", "other_tools_node", "rag_node"}


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


class ChatRequest(BaseModel):
    message: str
    thread_id: str = "default"


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/chat")
async def chat(req: ChatRequest):
    """SSE 스트리밍으로 에이전트 응답을 전달한다."""

    sync_q: SyncQueue = SyncQueue()

    def run_workflow():
        config = {
            "configurable": {"thread_id": req.thread_id},
            "recursion_limit": 5,
        }
        try:
            events = workflow.stream(
                {"messages": [HumanMessage(content=req.message)]},
                config=config,
                stream_mode="updates",
            )
            for event in events:
                for node_name, state_update in event.items():
                    if node_name in _STATUS_MSG:
                        sync_q.put(_sse({"type": "status", "content": _STATUS_MSG[node_name]}))

                    if node_name in _AI_OUTPUT_NODES and "messages" in state_update:
                        msgs = state_update["messages"]
                        if not isinstance(msgs, list):
                            msgs = [msgs]
                        for msg in msgs:
                            if hasattr(msg, "type") and msg.type == "ai" and msg.content:
                                sync_q.put(_sse({"type": "answer", "content": msg.content}))

            sync_q.put(_sse({"type": "done"}))

        except GraphRecursionError:
            sync_q.put(_sse({"type": "error", "content": "최대 탐색 횟수(recursion_limit)를 초과했습니다."}))
        except Exception as e:
            sync_q.put(_sse({"type": "error", "content": str(e)}))
        finally:
            sync_q.put(None)  # 종료 신호

    async def generate():
        thread = threading.Thread(target=run_workflow, daemon=True)
        thread.start()

        loop = asyncio.get_event_loop()
        while True:
            # 블로킹 queue.get을 executor에서 실행해 이벤트 루프를 막지 않음
            item = await loop.run_in_executor(None, sync_q.get)
            if item is None:
                break
            yield item

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    import uvicorn
    provider = os.getenv("LLM_PROVIDER", "ollama")
    print("========================================")
    print("MyAgent Server Started!")
    print(f"Provider: {provider}")
    print("URL: http://localhost:8000")
    print("Docs: http://localhost:8000/docs")
    print("========================================")
    uvicorn.run(app, host="0.0.0.0", port=8000)
