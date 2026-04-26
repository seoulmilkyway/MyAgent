from langchain_core.tools import tool
import os

# 파일 작업을 허용할 기준 디렉토리 (프로젝트 내 workspace 폴더로 제한)
_BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "workspace"))

def _safe_path(file_path: str) -> str:
    abs_path = os.path.realpath(os.path.abspath(file_path))
    base = os.path.realpath(_BASE_DIR)
    if not (abs_path.startswith(base + os.sep) or abs_path == base):
        raise ValueError(f"접근 거부: 허용된 디렉토리 외부 경로입니다. (허용 경로: {_BASE_DIR})")
    return abs_path

@tool
def read_file(file_path: str) -> str:
    """Read the contents of a file given its path. Only files inside the workspace directory are accessible."""
    try:
        safe = _safe_path(file_path)
        with open(safe, "r", encoding="utf-8") as f:
            return f.read()
    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error reading file: {e}"

@tool
def write_file(file_path: str, content: str) -> str:
    """Write content to a file given its path and the content. Only files inside the workspace directory are writable."""
    try:
        safe = _safe_path(file_path)
        os.makedirs(os.path.dirname(safe), exist_ok=True)
        with open(safe, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote to {safe}"
    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error writing to file: {e}"
