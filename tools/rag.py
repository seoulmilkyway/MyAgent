import os
import hashlib
import threading
from langchain_core.tools import tool
from langchain_community.document_loaders import PyPDFDirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

DOCS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Docs")
FAISS_INDEX_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".faiss_index")

_vectorstore = None
_vectorstore_lock = threading.Lock()

def get_docs_hash() -> str:
    """Calculate an MD5 hash based on the names and modification times of all PDFs in Docs."""
    if not os.path.exists(DOCS_DIR):
        return ""

    file_info = []
    for root, _, files in os.walk(DOCS_DIR):
        for f in sorted(files):
            if f.endswith(".pdf"):
                filepath = os.path.join(root, f)
                mtime = os.path.getmtime(filepath)
                file_info.append(f"{filepath}_{mtime}")

    return hashlib.md5("".join(file_info).encode()).hexdigest()

def get_index_integrity_hash() -> str:
    """FAISS 인덱스 파일들의 SHA-256 해시를 계산하여 무결성 검증에 사용."""
    if not os.path.exists(FAISS_INDEX_DIR):
        return ""

    file_hashes = []
    for fname in sorted(os.listdir(FAISS_INDEX_DIR)):
        if fname in ("docs_hash.txt", "index_integrity.txt"):
            continue
        fpath = os.path.join(FAISS_INDEX_DIR, fname)
        if os.path.isfile(fpath):
            with open(fpath, "rb") as f:
                file_hashes.append(hashlib.sha256(f.read()).hexdigest())

    return hashlib.sha256("".join(file_hashes).encode()).hexdigest()

def _save_index_integrity():
    integrity_file = os.path.join(FAISS_INDEX_DIR, "index_integrity.txt")
    with open(integrity_file, "w") as f:
        f.write(get_index_integrity_hash())

def _verify_index_integrity() -> bool:
    integrity_file = os.path.join(FAISS_INDEX_DIR, "index_integrity.txt")
    if not os.path.exists(integrity_file):
        return False
    with open(integrity_file, "r") as f:
        saved = f.read().strip()
    return saved == get_index_integrity_hash()

def get_vectorstore():
    print("\n[System] Initializing embedding model (jhgan/ko-sroberta-multitask)...")
    embeddings = HuggingFaceEmbeddings(model_name="jhgan/ko-sroberta-multitask")

    current_hash = get_docs_hash()
    hash_file = os.path.join(FAISS_INDEX_DIR, "docs_hash.txt")

    rebuild_needed = True
    if os.path.exists(FAISS_INDEX_DIR) and os.path.exists(hash_file):
        with open(hash_file, "r") as f:
            saved_hash = f.read().strip()
        if saved_hash == current_hash:
            rebuild_needed = False

    if not rebuild_needed:
        if not _verify_index_integrity():
            print("[Warning] FAISS 인덱스 무결성 검증 실패. 인덱스를 재생성합니다.")
            rebuild_needed = True
        else:
            try:
                return FAISS.load_local(FAISS_INDEX_DIR, embeddings, allow_dangerous_deserialization=True)
            except Exception as e:
                print(f"[Warning] Error loading FAISS index: {e}. Rebuilding...")

    # If no index or hash/integrity mismatch, create a new one from Docs directory
    print(f"[System] Changes detected or missing index. Loading PDFs from {DOCS_DIR}...")
    os.makedirs(DOCS_DIR, exist_ok=True)
    loader = PyPDFDirectoryLoader(DOCS_DIR)
    docs = loader.load()

    if not docs:
        print("[System] No documents found in Docs folder. Creating an empty FAISS index.")
        from langchain_core.documents import Document
        docs = [Document(page_content="empty", metadata={"source": "empty"})]

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    splits = text_splitter.split_documents(docs)

    print(f"[System] Creating FAISS index with {len(splits)} chunks...")
    vectorstore = FAISS.from_documents(splits, embeddings)
    vectorstore.save_local(FAISS_INDEX_DIR)

    with open(hash_file, "w") as f:
        f.write(current_hash)

    # 인덱스 저장 후 무결성 해시 기록
    _save_index_integrity()

    print("[System] FAISS index created and saved.")
    return vectorstore

@tool
def search_local_docs(query: str) -> str:
    """Search for relevant information in the local PDF documents stored in the Docs directory. Use this when the user asks about internal documents or PDFs."""
    global _vectorstore
    # 스레드 안전한 초기화
    if _vectorstore is None:
        with _vectorstore_lock:
            if _vectorstore is None:
                _vectorstore = get_vectorstore()

    try:
        results = _vectorstore.similarity_search(query, k=3)
        if not results or (len(results) == 1 and results[0].page_content == "empty"):
            return "No relevant information found in the local documents. Ensure PDFs are placed in the Docs folder."

        formatted_results = []
        for doc in results:
            source = doc.metadata.get("source", "Unknown")
            page = doc.metadata.get("page", "?")
            formatted_results.append(f"[Source: {os.path.basename(source)}, Page: {page}]\n{doc.page_content}")

        return "\n\n---\n\n".join(formatted_results)
    except Exception as e:
        return f"Error searching documents: {e}"
