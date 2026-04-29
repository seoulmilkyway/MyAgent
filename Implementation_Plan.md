# LangGraph 챗봇 에이전트 구현 명세서 (Implementation Plan)

본 문서는 프로젝트의 최신 구현 상태 및 아키텍처를 정의합니다. 새롭게 추가된 기능(Google API, MCP 연동, Chrome 확장 프로그램 등)을 모두 반영한 최신 버전입니다.

---

## 1. 개발 환경 및 기본 설정
- **가상 환경**: Python `venv` 사용
- **의존성 관리**: `requirements.txt`
- **주요 라이브러리**:
  - `langchain`, `langgraph` (에이전트 워크플로우 구성)
  - `langchain-community`, `langchain-openai`, `langchain-google-genai` (다양한 모델 연동)
  - `pypdf`, `faiss-cpu`, `sentence-transformers`, `langchain-huggingface` (RAG 로컬 구축)
  - `duckduckgo-search`, `tavily-python` (웹 검색)
  - `google-api-python-client`, `google-auth-oauthlib` (Google 캘린더 및 Gmail 제어)
  - `fastapi`, `uvicorn` (Chrome 확장 프로그램용 백엔드 서버)

## 2. LLM 및 임베딩 구성
- **LLM 팩토리 (`llm_factory.py`)**: 
  - `.env` 파일의 `LLM_PROVIDER` 설정에 따라 Ollama(`gemma4:e4b` 등), OpenAI, Gemini 모델을 동적으로 반환합니다.
- **임베딩 모델 (RAG 용)**:
  - HuggingFace의 `jhgan/ko-sroberta-multitask` 모델을 기본으로 사용하여 빠르고 가벼운 한국어 임베딩을 제공합니다.

## 3. 에이전트 핵심 도구 (Tools)
- **RAG 문서 검색 (`tools/rag.py`)**: 
  - `Docs` 폴더 내 PDF를 FAISS 기반 벡터 DB로 구축합니다.
  - **자동 인덱스 갱신 및 무결성 검증**: 문서의 해시(MD5)와 인덱스 무결성 검증(SHA-256)을 통해 파일이 추가되거나 조작될 경우 인덱스를 실시간 자동 재구성합니다.
- **웹 검색 (`tools/search.py`)**: 
  - 최신 정보 탐색을 위해 외부 검색 엔진을 제어합니다.
- **파일 제어 (`tools/file_ops.py`)**: 
  - 시스템 파일 읽기(`read_file`) 및 쓰기(`write_file`).
- **Google Workspace 제어 (`tools/google_auth.py`, `google_calendar.py`, `gmail.py`)**:
  - `google_auth.py`를 통해 통합 OAuth 2.0 인증 토큰을 안전하게 발급 및 관리합니다.
  - **캘린더 툴**: 일정 정밀 검색, 등록, 수정, 삭제
  - **메일(Gmail) 툴**: 안 읽은 메일 조회, 본문 파싱, 새로운 메일 발송, 회신, 원본 포함 전달, 휴지통 삭제
- **외부 서비스 프로토콜 연동 (`tools/mcp_client.py`)**:
  - `mcp_servers.json` 설정을 읽어들여 Notion, Jira 등 **Model Context Protocol(MCP)**을 지원하는 모든 외부 서비스를 LangChain 도구로 변환하여 에이전트에 공급합니다.

## 4. 라우터 기반 아키텍처 (`agent.py`)
에이전트는 프롬프트 인젝션 방어(`_sanitize`)와 이미지/미디어 멀티모달 메시지를 처리하며, **라우터(Router) 노드**를 통해 의도를 정밀하게 분기합니다.

- **`route_query` (조건부 라우터)**: 사용자의 질문을 분석하여 분기.
  1. **`rag_node` (Corrective RAG 적용)**: 내부 문서 검색. 
     - LLM이 직접 검색 결과의 유효성을 평가(Relevance Check)하고, 정보가 없으면 웹 검색으로 자동 폴백(Fallback)합니다.
  2. **`web_search_node`**: 웹 검색 수행.
  3. **`other_tools_node`**: 파일 입출력, **Google 캘린더**, **Gmail**, **MCP 도구** 전체가 바인딩된 범용 제어 노드.
  4. **`direct_chat_node`**: 도구가 필요 없는 일상 대화.
- **`generate_node`**: 획득한 컨텍스트(Context)를 바탕으로 자연어 답변 합성 및 스트리밍(`USE_STREAMING`) 출력.

## 5. 다양한 사용자 인터페이스 (Interface)
에이전트 코어는 분리되어 있으며, 사용자는 3가지 방식으로 접근할 수 있습니다.
- **CLI 모드 (`main_agent_cli.py`)**: 터미널 기반의 빠르고 가벼운 인터페이스. 실시간 타자(스트리밍) 효과 지원.
- **Web UI 모드 (`main_agent_ui.py`)**: Gradio 기반의 친숙한 웹 브라우저 인터페이스.
- **Chrome 확장 프로그램 (`main_agent_server.py` & `chrome_extension/sidebar.js`)**: 
  - FastAPI 기반의 백엔드 서버를 구동하여, 크롬 브라우저 우측 사이드바 확장 프로그램과 실시간 통신합니다. 
  - 마크다운 렌더링 및 웹 서핑 중 챗봇 비서 활용 가능.

## 6. 예외 및 보안 처리
- **무한 루프 방지**: LangGraph Recursion Limit (5단계 제한) 적용.
- **보안 격리**: `credentials.json`, `token.json` 등을 `.gitignore`로 엄격히 관리하여 인증 키 유출을 방지.
