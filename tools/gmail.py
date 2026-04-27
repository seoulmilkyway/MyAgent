import base64
from email.message import EmailMessage
from googleapiclient.discovery import build
from langchain_core.tools import tool
from tools.google_auth import get_google_credentials

def get_gmail_service():
    """OAuth 인증을 거쳐 Gmail 서비스 객체를 반환합니다."""
    creds = get_google_credentials()
    return build("gmail", "v1", credentials=creds)

@tool
def search_emails(query: str = "", max_results: int = 5) -> str:
    """Gmail에서 특정 조건(query)에 맞는 이메일 목록을 검색합니다.
    Args:
        query (str): Gmail 검색 쿼리 (예: 'is:unread', 'from:boss@company.com')
        max_results (int): 가져올 최대 메일 개수 (기본 5개)
    """
    try:
        service = get_gmail_service()
        results = service.users().messages().list(userId='me', q=query, maxResults=max_results).execute()
        messages = results.get('messages', [])

        if not messages:
            return "검색된 이메일이 없습니다."

        output = "검색된 이메일 목록:\n"
        for msg in messages:
            msg_id = msg['id']
            msg_data = service.users().messages().get(userId='me', id=msg_id, format='metadata', metadataHeaders=['Subject', 'From', 'Date']).execute()
            
            headers = msg_data.get('payload', {}).get('headers', [])
            subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), "제목 없음")
            sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), "알 수 없는 발신자")
            date = next((h['value'] for h in headers if h['name'].lower() == 'date'), "")
            
            output += f"- [ID: {msg_id}] {date} | From: {sender} | Subject: {subject}\n"
            
        return output
    except Exception as e:
        return f"이메일 검색 중 오류 발생: {e}"

def _get_plain_text(payload):
    """이메일 payload에서 일반 텍스트 본문을 재귀적으로 추출합니다."""
    if payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode('utf-8')
    elif "parts" in payload:
        text = ""
        for part in payload["parts"]:
            text += _get_plain_text(part)
        return text
    return ""

@tool
def get_email_content(message_id: str) -> str:
    """특정 이메일의 전체 본문을 읽어옵니다.
    Args:
        message_id (str): 이메일의 고유 ID
    """
    try:
        service = get_gmail_service()
        msg_data = service.users().messages().get(userId='me', id=message_id, format='full').execute()
        
        headers = msg_data.get('payload', {}).get('headers', [])
        subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), "제목 없음")
        sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), "알 수 없는 발신자")
        
        body_text = _get_plain_text(msg_data.get('payload', {}))
        
        return f"Subject: {subject}\nFrom: {sender}\n\n[본문 내용]\n{body_text}"
    except Exception as e:
        return f"이메일 본문 읽기 중 오류 발생: {e}"

@tool
def send_email(to: str, subject: str, body: str) -> str:
    """새로운 이메일을 작성하여 발송합니다.
    Args:
        to (str): 수신자 이메일 주소
        subject (str): 이메일 제목
        body (str): 이메일 본문 내용
    """
    try:
        service = get_gmail_service()
        
        message = EmailMessage()
        message.set_content(body)
        message["To"] = to
        message["Subject"] = subject
        
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {'raw': encoded_message}
        
        service.users().messages().send(userId="me", body=create_message).execute()
        return f"'{to}'에게 이메일을 성공적으로 발송했습니다."
    except Exception as e:
        return f"이메일 발송 중 오류 발생: {e}"

@tool
def reply_to_email(message_id: str, body: str) -> str:
    """기존 수신된 메일에 쓰레드를 유지하며 회신합니다.
    Args:
        message_id (str): 회신할 원본 이메일의 ID
        body (str): 회신할 본문 내용
    """
    try:
        service = get_gmail_service()
        orig_msg = service.users().messages().get(userId='me', id=message_id, format='metadata').execute()
        headers = orig_msg.get('payload', {}).get('headers', [])
        
        orig_subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), "")
        orig_from = next((h['value'] for h in headers if h['name'].lower() == 'from'), "")
        orig_msg_id_header = next((h['value'] for h in headers if h['name'].lower() == 'message-id'), "")
        orig_references = next((h['value'] for h in headers if h['name'].lower() == 'references'), "")
        
        subject = orig_subject if orig_subject.lower().startswith('re:') else f"Re: {orig_subject}"
        
        message = EmailMessage()
        message.set_content(body)
        message["To"] = orig_from
        message["Subject"] = subject
        message["In-Reply-To"] = orig_msg_id_header
        message["References"] = f"{orig_references} {orig_msg_id_header}".strip()
        
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {'raw': encoded_message, 'threadId': orig_msg.get('threadId')}
        
        service.users().messages().send(userId="me", body=create_message).execute()
        return f"메일(ID: {message_id})에 성공적으로 회신했습니다."
    except Exception as e:
        return f"이메일 회신 중 오류 발생: {e}"

@tool
def forward_email(message_id: str, to: str, additional_body: str = "") -> str:
    """수신한 메일의 원본을 포함하여 다른 사람에게 전달합니다.
    Args:
        message_id (str): 전달할 원본 이메일의 ID
        to (str): 수신자 이메일 주소
        additional_body (str, optional): 덧붙일 내용
    """
    try:
        service = get_gmail_service()
        orig_msg = service.users().messages().get(userId='me', id=message_id, format='full').execute()
        headers = orig_msg.get('payload', {}).get('headers', [])
        
        orig_subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), "")
        orig_from = next((h['value'] for h in headers if h['name'].lower() == 'from'), "")
        orig_date = next((h['value'] for h in headers if h['name'].lower() == 'date'), "")
        
        orig_body = _get_plain_text(orig_msg.get('payload', {}))
        subject = orig_subject if orig_subject.lower().startswith('fwd:') else f"Fwd: {orig_subject}"
        
        full_body = f"{additional_body}\n\n" if additional_body else ""
        full_body += f"---------- Forwarded message ---------\nFrom: {orig_from}\nDate: {orig_date}\nSubject: {orig_subject}\n\n{orig_body}"
        
        message = EmailMessage()
        message.set_content(full_body)
        message["To"] = to
        message["Subject"] = subject
        
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {'raw': encoded_message}
        
        service.users().messages().send(userId="me", body=create_message).execute()
        return f"메일(ID: {message_id})을 '{to}'에게 성공적으로 전달했습니다."
    except Exception as e:
        return f"이메일 전달 중 오류 발생: {e}"

@tool
def trash_email(message_id: str) -> str:
    """메일을 휴지통으로 이동시킵니다.
    Args:
        message_id (str): 삭제(휴지통 이동)할 이메일의 ID
    """
    try:
        service = get_gmail_service()
        service.users().messages().trash(userId='me', id=message_id).execute()
        return f"메일(ID: {message_id})이 휴지통으로 이동되었습니다."
    except Exception as e:
        return f"이메일 삭제 중 오류 발생: {e}"
