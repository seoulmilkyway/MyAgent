# LangGraph 챗봇 에이전트 구현 명세서 (Implementation Plan)

본 문서는 프로젝트의 최신 구현 상태 및 아키텍처를 정의합니다. 앞으로 프로젝트 구조나 로직에 변경이 발생할 때마다 본 문서가 지속적으로 동기화됩니다.

---

## 1. 개발 환경 및 기본 설정
- **가상 환경**: Python `venv` 사용
- **의존성 관리**: `requirements.txt`
- **주요 라이브러리**:
  - `langchain`, `langgraph` (에이전트 워크플로우 구성)
  - `langchain-community`, `langchain-openai`, `langchain-google-genai` (다양한 제공자 연동)
  - `pypdf`, `faiss-cpu`, `sentence-transformers`, `langchain-huggingface` (RAG 로컬 구축)
  - `duckduckgo-search`, `tavily-python`, `google-search-results` (웹 검색)
  - `langsmith` (디버깅/트레이싱)

## 2. LLM 및 임베딩 구성
- **LLM 팩토리 (`llm_factory.py`)**: 
  - `.env` 파일의 `LLM_PROVIDER` 설정에 따라 Ollama(`gemma4:e4b` 등), OpenAI, Gemini 모델을 동적으로 반환합니다.
- **임베딩 모델 (RAG 용)**:
  - HuggingFace의 `jhgan/ko-sroberta-multitask` 모델을 기본으로 사용하여 빠르고 가벼운 한국어 임베딩을 제공합니다.

## 3. 에이전트 핵심 도구 (Tools)
- **RAG 문서 검색 (`tools/rag.py`)**: 
  - 프로젝트 루트의 `Docs` 폴더 내 PDF 파일을 읽어 `faiss_index`에 로컬 벡터 데이터베이스로 구축하고 검색 결과를 제공합니다.
  - **자동 인덱스 갱신**: 시스템 시작 시 `Docs` 폴더 내 파일들의 이름과 수정 날짜를 스캔해 고유 해시(Hash)를 생성합니다. 파일이 추가, 수정, 삭제될 경우 이를 자동으로 감지하여 인덱스를 즉시 재구성합니다.
- **웹 검색 (`tools/search.py`)**: 
  - `.env`의 `SEARCH_PROVIDER` 설정에 따라 DuckDuckGo(무료), Tavily, Google 중 하나를 선택하여 최신 정보를 검색합니다.
- **파일 제어 (`tools/file_ops.py`)**: 
  - 로컬 파일 시스템에서 파일을 읽거나(`read_file`) 쓰는(`write_file`) 기능을 수행합니다.

## 4. 라우터 기반 아키텍처 (`agent.py`)
에이전트는 LLM의 도구 판단 오류를 최소화하기 위해 **라우터(Router) 노드**를 최전방에 배치한 아키텍처를 가집니다.

- **`route_query` (조건부 라우터)**: 사용자의 질문을 분석하여 다음 4가지 노드 중 하나로 명확히 분기시킵니다.
  1. **`rag_node` (Corrective RAG 적용)**: 내부 문서/PDF 검색이 필요할 때 이동합니다. 
     - RAG를 통해 문서를 검색한 후, **LLM이 직접 해당 문서가 사용자의 질문을 해결하는 데 유효한지 평가(Relevance Check)**합니다.
     - 문서가 관련이 있다고 판정되면 `generate_node`로 전달합니다.
     - 문서가 무관하다고 판정되면 로컬 검색을 포기하고 **자동으로 `web_search_node`로 폴백(Fallback)**하여 인터넷 검색으로 넘깁니다.
  2. **`web_search_node`**: 인터넷 최신 정보 검색이 필요할 때 이동. 도구 실행 후 `generate_node`로 전달.
  3. **`other_tools_node`**: 파일 입출력 등 기타 도구 사용이 필요할 때 이동. `ToolNode`와 상호작용.
  4. **`direct_chat_node`**: 도구 없이 바로 답변이 가능할 때 이동. 답변 생성 후 즉시 종료(`END`).
- **`generate_node`**: RAG나 웹 검색을 통해 확보한 컨텍스트(Context)를 바탕으로 최종 자연어 답변을 합성(Synthesis)합니다.

## 5. 예외 및 무한 루프 방지 처리
- **LangGraph Recursion Limit (`main.py`)**:
  - `config = {"recursion_limit": 5}` 설정을 통해 에이전트의 노드 탐색이 최대 5단계를 초과할 경우, 무한 탐색에 빠진 것으로 간주합니다.
  - 초과 시 `GraphRecursionError`를 안전하게 캐치하여, 에이전트가 다운되지 않고 "최대 탐색 횟수를 초과했다"는 시스템 안내 메시지를 출력한 뒤 다음 질문을 대기합니다.
