from typing import Annotated, Literal
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage, SystemMessage

from llm_factory import get_llm
from tools.search import get_search_tool
from tools.file_ops import read_file, write_file
from tools.rag import search_local_docs
from tools.google_calendar import (
    get_upcoming_events, 
    create_calendar_event, 
    search_calendar_events, 
    update_calendar_event, 
    delete_calendar_event
)
from tools.gmail import (
    search_emails,
    get_email_content,
    send_email,
    reply_to_email,
    forward_email,
    trash_email
)

_MAX_INPUT_LENGTH = 2000

def _sanitize(text) -> str:
    """사용자 입력 길이를 제한하고 프롬프트 구분자를 무력화.
    멀티모달 content list인 경우 텍스트 블록만 추출한다."""
    if isinstance(text, list):
        text = " ".join(
            block.get("text", "") for block in text
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return str(text)[:_MAX_INPUT_LENGTH].replace("<|", "< |").replace("|>", "| >")

# We initialize tools
search_web = get_search_tool()

class State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]

def route_query(state: State) -> str:
    last_msg = next((m for m in reversed(state["messages"]) if m.type == "human"), None)
    if last_msg is None:
        return "direct_chat_node"

    # 이미지·음성·영상이 포함된 멀티모달 메시지는 LLM이 직접 분석
    if isinstance(last_msg.content, list):
        has_media = any(
            isinstance(b, dict) and b.get("type") in ("image_url", "media")
            for b in last_msg.content
        )
        if has_media:
            return "direct_chat_node"

    last_human_msg = _sanitize(last_msg.content)

    llm = get_llm()
    sys_msg = """You are a strict routing assistant. Analyze the user's intent.
Choose exactly one of the following words based on what the user wants:
- 'rag': The user asks to search or summarize internal documents, PDFs, or files in the Docs folder.
- 'web_search': The user asks for news, current events, or general facts from the internet.
- 'other_tools': The user wants to write/save a text file or read a specific file path.
- 'calendar': The user wants to check schedules or create a new event in Google Calendar.
- 'email': The user wants to read, send, reply, forward, or delete emails in Gmail.
- 'direct_chat': The user is just chatting normally without needing extra tools.

Reply with ONLY the chosen word. No other text."""

    response = llm.invoke([
        {"role": "system", "content": sys_msg},
        {"role": "user", "content": last_human_msg}
    ])

    route = response.content.strip().lower()

    if "rag" in route: return "rag_node"
    if "web" in route: return "web_search_node"
    if "other" in route: return "other_tools_node"
    if "calendar" in route: return "other_tools_node"
    if "email" in route: return "other_tools_node"
    return "direct_chat_node"

def rag_node(state: State):
    from langchain_core.messages import AIMessage, SystemMessage
    query = _sanitize(next((m.content for m in reversed(state["messages"]) if m.type == "human"), ""))
    result = search_local_docs.invoke(query)
    
    if "No relevant information found" in result:
        ai_msg = AIMessage(content="로컬에 찾는 정보가 없어서 인터넷 최신 정보 검색으로 전환해서 알려드리겠습니다")
        sys_msg = SystemMessage(content="[RAG 검색 실패] 로컬 문서에서 정보를 찾지 못했습니다. 웹 검색으로 전환합니다.")
        return {"messages": [ai_msg, sys_msg]}
        
    # 검색된 문서가 질문과 관련이 있는지 LLM으로 평가 (Relevance Check)
    llm = get_llm()
    eval_prompt = f"""You are a strict evaluator. Does the retrieved document contain the answer to the user's question?

<user_question>
{query}
</user_question>

<retrieved_document>
{result}
</retrieved_document>

If the document explicitly mentions the specific topic or provides the exact answer to the user's question, output ONLY the word 'yes'.
If the document is about a completely different topic or does not contain the answer, output ONLY the word 'no'.
Do not output any other text or explanation."""
    
    eval_res = llm.invoke([{"role": "user", "content": eval_prompt}])
    score = eval_res.content.strip().lower()
    
    if "no" in score:
        ai_msg = AIMessage(content="로컬에 찾는 정보가 없어서 인터넷 최신 정보 검색으로 전환해서 알려드리겠습니다")
        sys_msg = SystemMessage(content="[RAG 검색 실패] 로컬 문서에서 유효한 정보를 찾지 못했습니다. 웹 검색으로 전환합니다.")
        return {"messages": [ai_msg, sys_msg]}
        
    sys_msg = SystemMessage(content=f"[RAG 검색 결과]\n{result}\n\n위 결과를 바탕으로 사용자의 질문에 답해주세요.")
    return {"messages": [sys_msg]}

def web_search_node(state: State):
    query = _sanitize(next((m.content for m in reversed(state["messages"]) if m.type == "human"), ""))
    result = search_web.invoke(query)
    sys_msg = SystemMessage(content=f"[웹 검색 결과]\n{result}\n\n위 결과를 바탕으로 사용자의 질문에 답해주세요.")
    return {"messages": [sys_msg]}

def check_rag_result(state: State) -> str:
    last_msg = state["messages"][-1]
    if "[RAG 검색 실패]" in last_msg.content:
        return "web_search_node"
    return "generate_node"

def other_tools_node(state: State):
    # 파일 작업 등은 LLM이 직접 도구를 선택해서 매개변수를 넣어야 하므로 bind_tools 사용
    llm = get_llm().bind_tools([
        read_file, write_file, 
        get_upcoming_events, create_calendar_event,
        search_calendar_events, update_calendar_event, delete_calendar_event,
        search_emails, get_email_content, send_email, reply_to_email, forward_email, trash_email
    ])
    response = llm.invoke(state["messages"])
    return {"messages": [response]}



import os

def stream_response(state: State) -> dict:
    llm = get_llm()
    is_streaming = os.getenv("USE_STREAMING", "true").lower() in ("true", "1", "yes")
    
    if not is_streaming:
        response = llm.invoke(state["messages"])
        return {"messages": [response]}
        
    print("\n🤖 Agent: ", end="", flush=True)
    full_content = ""
    for chunk in llm.stream(state["messages"]):
        if chunk.content:
            print(chunk.content, end="", flush=True)
            full_content += chunk.content
    print("\n")
    from langchain_core.messages import AIMessage
    return {"messages": [AIMessage(content=full_content)]}

def direct_chat_node(state: State):
    return stream_response(state)

def generate_node(state: State):
    # RAG나 웹 검색 후 취합된 정보(SystemMessage)를 바탕으로 최종 답변 생성
    return stream_response(state)

def build_workflow():
    workflow_builder = StateGraph(State)
    
    # 노드 추가
    workflow_builder.add_node("rag_node", rag_node)
    workflow_builder.add_node("web_search_node", web_search_node)
    workflow_builder.add_node("other_tools_node", other_tools_node)
    workflow_builder.add_node("direct_chat_node", direct_chat_node)
    workflow_builder.add_node("generate_node", generate_node)
    
    from langgraph.prebuilt import ToolNode, tools_condition
    tool_node = ToolNode(tools=[
        read_file, write_file, 
        get_upcoming_events, create_calendar_event,
        search_calendar_events, update_calendar_event, delete_calendar_event,
        search_emails, get_email_content, send_email, reply_to_email, forward_email, trash_email
    ])
    workflow_builder.add_node("tools", tool_node)
    
    # 엣지 연결: 시작 -> 라우터 (별도 노드 없이 조건부 엣지로 바로 분기)
    workflow_builder.add_conditional_edges(
        START,
        route_query,
        {
            "rag_node": "rag_node",
            "web_search_node": "web_search_node",
            "other_tools_node": "other_tools_node",
            "direct_chat_node": "direct_chat_node",
        }
    )
    
    # RAG 실패 시 Web Search로, 성공 시 Generate로 이동하는 조건부 엣지
    workflow_builder.add_conditional_edges(
        "rag_node",
        check_rag_result,
        {
            "web_search_node": "web_search_node",
            "generate_node": "generate_node"
        }
    )
    workflow_builder.add_edge("web_search_node", "generate_node")
    
    # Other tools(파일 쓰기 등)는 ToolNode와 상호작용
    workflow_builder.add_conditional_edges(
        "other_tools_node",
        tools_condition,
    )
    workflow_builder.add_edge("tools", "other_tools_node") # 도구 사용 후 결과 해석을 위해 돌아감
    
    # 최종 종료 엣지
    workflow_builder.add_edge("generate_node", END)
    workflow_builder.add_edge("direct_chat_node", END)
    
    workflow = workflow_builder.compile()
    return workflow
