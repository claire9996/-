#!/usr/bin/env python3
"""
쿠팡 공급업체 포털 발주리스트 모니터링 → 노션 알림
GitHub Actions에서 1시간마다 실행됩니다.

필요한 GitHub Secrets:
  COUPANG_ID       : 쿠팡 공급업체 포털 아이디
  COUPANG_PW       : 쿠팡 공급업체 포털 비밀번호
  NOTION_TOKEN     : 노션 Integration 토큰 (ntn_xxx...)
  NOTION_DB_ID     : 노션 데이터베이스 ID
  NOTION_USER_ID   : 담당자 노션 사용자 ID
"""

import json
import os
import time
import logging
import requests
from pathlib import Path
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# ── 설정 (환경변수에서 읽기) ────────────────────────────────────────────
COUPANG_ID     = os.environ["COUPANG_ID"]
COUPANG_PW     = os.environ["COUPANG_PW"]
NOTION_TOKEN   = os.environ["NOTION_TOKEN"]
NOTION_DB_ID   = os.environ["NOTION_DB_ID"]
NOTION_USER_ID = os.environ["NOTION_USER_ID"]

PO_LIST_URL = "https://supplier.coupang.com/scm/purchase/order/list"
STATE_FILE  = Path("known_po_numbers.json")
KST         = timezone(timedelta(hours=9))

# ── 로깅 ───────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


# ── 상태 관리 ──────────────────────────────────────────────────────────
def load_known_po() -> set:
    if STATE_FILE.exists():
        try:
            return set(json.loads(STATE_FILE.read_text()).get("po_numbers", []))
        except Exception as e:
            logger.warning(f"상태 파일 로드 실패: {e}")
    return set()


def save_known_po(po_numbers: set):
    STATE_FILE.write_text(json.dumps({
        "po_numbers": sorted(list(po_numbers)),
        "updated_at": datetime.now(KST).isoformat()
    }, ensure_ascii=False, indent=2))
    logger.info(f"발주번호 {len(po_numbers)}개 저장")


# ── 쿠팡 발주번호 크롤링 (Playwright) ──────────────────────────────────
def get_po_numbers() -> list:
    logger.info("Playwright 브라우저 시작")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="ko-KR"
        )
        page = context.new_page()

        try:
            # ── 1. 로그인 페이지 접속 ──────────────────────────────────
            logger.info("로그인 페이지 접속")
            page.goto(
                "https://supplier.coupang.com/dashboard/KR",
                wait_until="domcontentloaded",
                timeout=30000
            )
            time.sleep(3)

            # ── 2. 아이디 / 비밀번호 입력 ─────────────────────────────
            # 아이디 필드
            page.wait_for_selector(
                'input[name="username"], input[type="text"], input[id*="id"], input[placeholder*="ID"]',
                timeout=10000
            )
            id_input = page.locator(
                'input[name="username"], input[type="text"][autocomplete], input[id*="id"]'
            ).first
            id_input.fill(COUPANG_ID)

            # 비밀번호 필드
            pw_input = page.locator('input[type="password"]').first
            pw_input.fill(COUPANG_PW)

            # 로그인 버튼 클릭
            page.locator(
                'button[type="submit"], button:has-text("로그인"), button:has-text("Login"), button:has-text("Sign in")'
            ).first.click()
            time.sleep(4)

            # ── 3. 2단계 인증 확인 ────────────────────────────────────
            current_url = page.url
            logger.info(f"로그인 후 URL: {current_url}")

            if any(kw in current_url.lower() for kw in ["verification", "mfa", "otp", "2fa", "auth"]):
                logger.error(
                    "2단계 인증 페이지 감지. "
                    "쿠팡 포털에서 '이 기기 30일 동안 인증 안 함'을 선택하거나, "
                    "인증 없이 로그인되는 환경에서 실행하세요."
                )
                browser.close()
                return []

            # ── 4. 발주리스트 페이지 이동 ─────────────────────────────
            logger.info("발주리스트 페이지 이동")
            page.goto(PO_LIST_URL, wait_until="networkidle", timeout=30000)
            time.sleep(5)

            # 로그인 실패 확인 (다시 로그인 페이지로 돌아온 경우)
            if "login" in page.url.lower() or "dashboard" in page.url.lower():
                logger.error("로그인 실패 또는 세션 만료")
                browser.close()
                return []

            # ── 5. 발주번호 추출 ──────────────────────────────────────
            po_numbers = page.evaluate("""
                () => {
                    var links = document.querySelectorAll('table tbody tr td a');
                    var result = [];
                    var seen = {};
                    for (var i = 0; i < links.length; i++) {
                        var text = links[i].innerText.trim();
                        if (/^[0-9]{9,}$/.test(text) && !seen[text]) {
                            seen[text] = true;
                            result.push(text);
                        }
                    }
                    return result;
                }
            """)

            logger.info(f"발주번호 {len(po_numbers)}개 추출: {po_numbers[:5]}")
            browser.close()
            return po_numbers

        except PlaywrightTimeout as e:
            logger.error(f"타임아웃: {e}")
            try:
                browser.close()
            except Exception:
                pass
            return []
        except Exception as e:
            logger.error(f"크롤링 오류: {e}")
            try:
                browser.close()
            except Exception:
                pass
            return []


# ── 노션 알림 생성 ─────────────────────────────────────────────────────
def create_notion_alert(new_po_numbers: list) -> bool:
    now_dt  = datetime.now(KST)
    now_iso = now_dt.strftime("%Y-%m-%dT%H:%M:%S.000+09:00")
    count   = len(new_po_numbers)

    po_display = ", ".join(new_po_numbers[:10])
    if count > 10:
        po_display += f" 외 {count - 10}건"

    payload = {
        "parent": {"database_id": NOTION_DB_ID},
        "properties": {
            "이름": {
                "title": [{"type": "text", "text": {"content": "로켓 발주를 확인하세요❤️"}}]
            },
            "날짜": {
                "date": {"start": now_iso}
            },
            "담당자": {
                "people": [{"id": NOTION_USER_ID}]
            }
        },
        "children": [
            {
                "object": "block",
                "type": "callout",
                "callout": {
                    "icon": {"type": "emoji", "emoji": "❤️"},
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {"content": "로켓 발주를 확인하세요❤️"},
                            "annotations": {"bold": True}
                        }
                    ],
                    "color": "red_background"
                }
            },
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": (
                                    f"감지 시각: {now_dt.strftime('%Y-%m-%d %H:%M:%S')} KST\n"
                                    f"새 발주번호: {po_display}"
                                )
                            }
                        }
                    ]
                }
            },
            {
                "object": "block",
                "type": "bookmark",
                "bookmark": {"url": PO_LIST_URL}
            }
        ]
    }

    try:
        resp = requests.post(
            "https://api.notion.com/v1/pages",
            headers={
                "Authorization": f"Bearer {NOTION_TOKEN}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=30
        )
        if resp.status_code == 200:
            logger.info("노션 알림 생성 성공: 로켓 발주를 확인하세요❤️")
            return True
        else:
            logger.error(f"노션 알림 실패: {resp.status_code} - {resp.text[:300]}")
            return False
    except Exception as e:
        logger.error(f"노션 API 오류: {e}")
        return False


# ── 메인 ───────────────────────────────────────────────────────────────
def main():
    logger.info("=" * 60)
    logger.info(f"모니터링 시작: {datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S KST')}")

    known = load_known_po()
    logger.info(f"기존 발주번호: {len(known)}개")

    current_list = get_po_numbers()
    if not current_list:
        logger.warning("발주번호 조회 실패 - 이번 실행 건너뜀")
        return

    current = set(current_list)

    if not known:
        logger.info("최초 실행: 현재 발주번호를 기준으로 저장 (알림 없음)")
        save_known_po(current)
        return

    new_po = sorted(list(current - known))
    if new_po:
        logger.info(f"새 발주 {len(new_po)}건 감지: {new_po}")
        if create_notion_alert(new_po):
            save_known_po(current)
            logger.info("노션 알림 전송 및 상태 업데이트 완료")
        else:
            logger.error("노션 알림 실패 - 상태 미업데이트")
    else:
        logger.info("새 발주 없음")
        save_known_po(current)

    logger.info(f"모니터링 완료: {datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S KST')}")


if __name__ == "__main__":
    main()
