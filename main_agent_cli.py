import os
import sys
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langgraph.errors import GraphRecursionError
from agent import build_workflow

def main():
    load_dotenv()
    print("=======================================")
    print("LangGraph Agent Started!")
    print(f"Provider: {os.getenv('LLM_PROVIDER', 'ollama')}")
    if os.getenv('LLM_PROVIDER', 'ollama').lower() == "ollama":
        print(f"Model: {os.getenv('OLLAMA_MODEL', 'gemma4:e4b')}")
    print("=======================================\n")
    
    try:
        workflow = build_workflow()
        print("Agent initialized. Type 'quit' or 'exit' to end.\n")
    except Exception as e:
        print(f"Error initializing agent: {e}")
        sys.exit(1)

    # memory/checkpoint config (for thread isolation)
    config = {"configurable": {"thread_id": "1"}, "recursion_limit": 5}
    
    while True:
        try:
            user_input = input("User: ")
            if user_input.lower() in ["quit", "exit", "q"]:
                print("Bye!")
                break
                
            if not user_input.strip():
                continue
                
            # Stream the events from the workflow
            events = workflow.stream(
                {"messages": [HumanMessage(content=user_input)]},
                config=config,
                stream_mode="updates"
            )
            
            for event in events:
                for node_name, state_update in event.items():
                    # 사용자에게 각 노드 진행 상황을 알림
                    if node_name == "rag_node":
                        print("🔍 [System] 내부 문서(Docs)에서 관련 정보를 탐색 중입니다...")
                    elif node_name == "web_search_node":
                        print("🌐 [System] 인터넷에서 최신 정보를 검색 중입니다...")
                    elif node_name == "other_tools_node":
                        print("🛠️ [System] 외부 도구를 실행하기 위해 분석 중입니다...")
                    elif node_name == "tools":
                        print("⚙️ [System] 도구 실행 완료, 결과를 분석합니다...")
                    elif node_name == "generate_node" or node_name == "direct_chat_node":
                        print("✍️ [System] 답변을 생성 중입니다...")
                        
                    # 스트리밍 여부에 따라 출력할 노드 결정
                    is_streaming = os.getenv("USE_STREAMING", "true").lower() in ("true", "1", "yes")
                    nodes_to_print = ["other_tools_node", "rag_node"]
                    if not is_streaming:
                        nodes_to_print.extend(["generate_node", "direct_chat_node"])
                        
                    if node_name in nodes_to_print:
                        if "messages" in state_update:
                            msgs = state_update["messages"]
                            if not isinstance(msgs, list):
                                msgs = [msgs]
                            for msg in msgs:
                                if msg.type == "ai" and msg.content:
                                    print(f"\n🤖 Agent: {msg.content}\n")
                        
        except GraphRecursionError:
            print("\n[System] 에이전트의 최대 탐색 횟수(recursion_limit)를 초과하여 대화를 조기 종료합니다.\n")
        except Exception as e:
            print(f"\nError during execution: {e}\n")

if __name__ == "__main__":
    main()
