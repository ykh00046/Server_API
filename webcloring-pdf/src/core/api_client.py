"""
포털 API 클라이언트 모듈

내부 API를 호출하여 완료 문서 목록을 가져옵니다.
"""
import requests
import json

from config.settings import settings
from utils.logger import logger


def fetch_documents_by_api(session, search_keyword="", start_date="", end_date=""):
    """
    Directly calls the internal API to fetch the list of completed documents.

    Args:
        session: A requests.Session object with authentication cookies.
        search_keyword: The keyword to search for in the document title.
        start_date: The start date for the search (e.g., "2025.08.21").
        end_date: The end date for the search (e.g., "2025.11.21").

    Returns:
        A list of documents as a JSON object, or None if the request fails.
    """
    # config 기반 URL 구성 (하드코딩 제거)
    base_url = settings.portal_url.rstrip('/')
    api_url = f"{base_url}/approval/work/apprlist/readApprAllList.do"

    payload = {
        "search_folderType": "COMPLETE",
        "search_docStatus": "ALL",
        "search_listType": "USER",
        "search_searchStatus": "ALL",
        "search_sdate": start_date,
        "search_edate": end_date,
        "search_subject": search_keyword,
        "search_apprUserId": "",
        "search_draftUserId": "",
        "search_draftDeptId": "",
        "search_formId": "",
        "search_docNo": "",
        "search_searchKeyword": "",
        "search_recordCount": 50, # Fetch 50 to match the page size
        "search_currentPage": 1,
    }

    try:
        logger.info(f"🚀 Calling internal API at: {api_url}")
        
        response = session.post(api_url, data=payload)
        response.raise_for_status()

        logger.info("✅ API call successful.")
        return response.json()

    except requests.exceptions.RequestException as e:
        logger.error(f"❌ API call failed: {e}")
        return None
    except json.JSONDecodeError:
        logger.error(f"❌ Failed to decode JSON from API response. Response text: {response.text[:500]}")
        return None


if __name__ == '__main__':
    logger.info("This script is intended to be used as a module.")
