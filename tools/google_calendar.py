import os
import datetime
from googleapiclient.discovery import build
from langchain_core.tools import tool
from tools.google_auth import get_google_credentials

def get_calendar_service():
    """OAuth 인증을 거쳐 구글 캘린더 서비스 객체를 반환합니다."""
    creds = get_google_credentials()
    return build("calendar", "v3", credentials=creds)

@tool
def get_upcoming_events(max_results: int = 10) -> str:
    """다가오는 N개의 구글 캘린더 일정을 조회합니다.
    Args:
        max_results (int): 조회할 일정의 최대 개수 (기본 10개)
    """
    try:
        service = get_calendar_service()
        # 'Z' indicates UTC time
        now = datetime.datetime.utcnow().isoformat() + "Z"
        
        events_result = service.events().list(
            calendarId="primary",
            timeMin=now,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime"
        ).execute()
        
        events = events_result.get("items", [])
        
        if not events:
            return "다가오는 일정이 없습니다."
            
        result = "다가오는 일정 목록:\n"
        for event in events:
            start = event["start"].get("dateTime", event["start"].get("date"))
            summary = event.get("summary", "제목 없음")
            event_id = event.get("id")
            result += f"- [ID: {event_id}] {start}: {summary}\n"
            
        return result
        
    except Exception as e:
        return f"캘린더 조회 중 오류 발생: {e}"

@tool
def create_calendar_event(summary: str, start_time: str, end_time: str, description: str = "") -> str:
    """새로운 일정을 구글 캘린더에 등록합니다.
    Args:
        summary (str): 일정 제목
        start_time (str): 시작 시간 (ISO-8601 포맷, 예: '2023-12-01T15:00:00+09:00')
        end_time (str): 종료 시간 (ISO-8601 포맷, 예: '2023-12-01T16:00:00+09:00')
        description (str, optional): 일정 내용/설명
    """
    try:
        service = get_calendar_service()
        
        event = {
            "summary": summary,
            "description": description,
            "start": {
                "dateTime": start_time,
                "timeZone": "Asia/Seoul",
            },
            "end": {
                "dateTime": end_time,
                "timeZone": "Asia/Seoul",
            },
        }
        
        created_event = service.events().insert(calendarId="primary", body=event).execute()
        return f"일정이 성공적으로 등록되었습니다. (링크: {created_event.get('htmlLink')})"
        
    except Exception as e:
        return f"일정 등록 중 오류 발생: {e}"

@tool
def search_calendar_events(query: str = None, time_min: str = None, time_max: str = None, max_results: int = 10) -> str:
    """구글 캘린더에서 특정 키워드나 날짜 범위로 일정을 검색합니다.
    Args:
        query (str, optional): 검색할 텍스트 키워드
        time_min (str, optional): 검색 시작 시간 (ISO-8601 포맷, 예: '2023-12-01T00:00:00+09:00')
        time_max (str, optional): 검색 종료 시간 (ISO-8601 포맷)
        max_results (int): 최대 반환 개수 (기본 10)
    """
    try:
        service = get_calendar_service()
        events_result = service.events().list(
            calendarId="primary",
            q=query,
            timeMin=time_min,
            timeMax=time_max,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime"
        ).execute()
        
        events = events_result.get("items", [])
        if not events:
            return "검색 조건에 맞는 일정이 없습니다."
            
        result = "검색된 일정 목록:\n"
        for event in events:
            start = event["start"].get("dateTime", event["start"].get("date"))
            summary = event.get("summary", "제목 없음")
            event_id = event.get("id")
            result += f"- [ID: {event_id}] {start}: {summary}\n"
            
        return result
    except Exception as e:
        return f"일정 검색 중 오류 발생: {e}"

@tool
def update_calendar_event(event_id: str, summary: str = None, start_time: str = None, end_time: str = None, description: str = None) -> str:
    """기존 구글 캘린더 일정을 수정합니다.
    Args:
        event_id (str): 수정할 일정의 고유 ID
        summary (str, optional): 변경할 제목
        start_time (str, optional): 변경할 시작 시간 (ISO-8601 포맷)
        end_time (str, optional): 변경할 종료 시간 (ISO-8601 포맷)
        description (str, optional): 변경할 설명
    """
    try:
        service = get_calendar_service()
        event = service.events().get(calendarId="primary", eventId=event_id).execute()
        
        if summary:
            event["summary"] = summary
        if description is not None:
            event["description"] = description
        if start_time:
            event["start"] = {"dateTime": start_time, "timeZone": "Asia/Seoul"}
        if end_time:
            event["end"] = {"dateTime": end_time, "timeZone": "Asia/Seoul"}
            
        updated_event = service.events().update(calendarId="primary", eventId=event_id, body=event).execute()
        return f"일정이 성공적으로 수정되었습니다. (링크: {updated_event.get('htmlLink')})"
    except Exception as e:
        return f"일정 수정 중 오류 발생: {e}"

@tool
def delete_calendar_event(event_id: str) -> str:
    """구글 캘린더에서 특정 일정을 삭제합니다.
    Args:
        event_id (str): 삭제할 일정의 고유 ID
    """
    try:
        service = get_calendar_service()
        service.events().delete(calendarId="primary", eventId=event_id).execute()
        return f"ID {event_id} 일정이 성공적으로 삭제되었습니다."
    except Exception as e:
        return f"일정 삭제 중 오류 발생: {e}"
