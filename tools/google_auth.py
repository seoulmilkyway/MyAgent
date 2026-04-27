import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# 구글 캘린더 및 Gmail 전체 권한
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://mail.google.com/"
]

def get_google_credentials():
    """OAuth 인증을 거쳐 Credentials 객체를 반환합니다. (캘린더 & Gmail 공용)"""
    creds = None
    # 프로젝트 최상단 기준
    token_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "token.json")
    credentials_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "credentials.json")

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                # 리프레시 실패 시 다시 로그인 유도
                creds = None
                
        if not creds:
            if not os.path.exists(credentials_path):
                raise FileNotFoundError(f"credentials.json 파일을 찾을 수 없습니다: {credentials_path}")
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
            
            with open(token_path, "w") as token_file:
                token_file.write(creds.to_json())

    return creds
