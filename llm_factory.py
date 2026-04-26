import os
from dotenv import load_dotenv

load_dotenv()

def get_llm():
    provider = os.getenv("LLM_PROVIDER", "ollama").lower()
    
    if provider == "ollama":
        from langchain_ollama import ChatOllama
        model = os.getenv("OLLAMA_MODEL", "gemma4:e4b")
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        return ChatOllama(model=model, base_url=base_url)
        
    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다. .env 파일을 확인하세요.")
        return ChatOpenAI(model="gpt-4o", api_key=api_key)

    elif provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY 환경변수가 설정되지 않았습니다. .env 파일을 확인하세요.")
        return ChatGoogleGenerativeAI(model="gemini-1.5-pro", api_key=api_key)
        
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")
