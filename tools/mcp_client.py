import os
import json
import asyncio
import threading
from typing import List, Any
from langchain_core.tools import StructuredTool, Tool

_mcp_tools_cache = []
_mcp_initialized = False

# 백그라운드 이벤트 루프 (비동기 MCP 클라이언트 유지용)
_mcp_loop = None

def _run_mcp_loop(loop: asyncio.AbstractEventLoop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

def _init_mcp_if_needed():
    global _mcp_loop
    if _mcp_loop is None:
        _mcp_loop = asyncio.new_event_loop()
        threading.Thread(target=_run_mcp_loop, args=(_mcp_loop,), daemon=True).start()

def load_mcp_config() -> dict:
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "mcp_servers.json")
    # mcp_servers.json이 없다면 example.json을 찾음 (테스트/예제 용도)
    if not os.path.exists(config_path):
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "mcp_servers.json.example")
    
    if not os.path.exists(config_path):
        return {}
        
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[MCP Error] 설정 파일을 읽는 중 오류가 발생했습니다: {e}")
        return {}

def get_mcp_tools() -> List[Tool]:
    """
    의존성을 최소화하고 UI와 코어 로직의 분리를 유지하기 위해,
    이 함수가 호출될 때 MCP 설정들을 LangChain의 범용 Tool 로 변환하여 반환합니다.
    """
    global _mcp_initialized, _mcp_tools_cache
    if _mcp_initialized:
        return _mcp_tools_cache

    _mcp_initialized = True
    config = load_mcp_config()
    servers = config.get("mcpServers", {})

    if not servers:
        return _mcp_tools_cache

    try:
        import mcp
    except ImportError:
        print("\n[MCP Alert] mcp 패키지가 설치되지 않았습니다.")
        print("Notion, Jira 등의 MCP를 연결하려면 다음 명령어로 패키지를 설치하세요:")
        print("  pip install mcp")
        print("현재는 MCP 기능이 비활성화된 상태로 진행됩니다.\n")
        return _mcp_tools_cache

    # TODO: mcp-python SDK를 사용한 실제 stdio 연결 및 Tool 변환 코드 (UI 의존성 없음)
    # 실제 환경에서는 아래와 같이 백그라운드 이벤트 루프를 생성해 세션을 유지합니다.
    # config의 command, args, env를 파싱 -> stdio_client() 연결 -> session.list_tools()
    # 변환된 Tools를 _mcp_tools_cache에 담습니다.
    
    _init_mcp_if_needed()
    print(f"\n[MCP Init] {len(servers)}개의 MCP 서버 연결을 구성 중입니다... (Notion, Jira 등)")
    
    # 예시: 임시 목업(Mock) Tool 등록 (실제 mcp 라이브러리 연동 전 뼈대)
    # mcp.client.stdio.stdio_client 의 비동기 통신을 동기화하여 LangChain Tool로 감쌉니다.
    for server_name, server_config in servers.items():
        def make_mcp_runner(srv_name: str):
            def run_mock_mcp_tool(query: str) -> str:
                return f"[{srv_name} MCP 실행 결과] '{query}' 요청을 성공적으로 처리했습니다."
            return run_mock_mcp_tool

        mock_tool = Tool(
            name=f"{server_name}_mcp_tool",
            description=f"{server_name} 서비스를 제어하거나 데이터를 읽어옵니다. 쿼리를 텍스트로 입력하세요.",
            func=make_mcp_runner(server_name)
        )
        _mcp_tools_cache.append(mock_tool)

    return _mcp_tools_cache
