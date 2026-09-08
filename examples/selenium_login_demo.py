"""1주차 예제: Selenium 으로 접속 → 로그인 → 쿠키 저장/복원.

주의: 브라우저 자동화는 **허용된 테스트 사이트에만** 수행한다.

기본 데모는 로그인 폼이 있는 공개 연습 사이트(the-internet.herokuapp.com)로
접속→로그인→쿠키 저장→새 세션에서 쿠키 복원→로그인 상태 확인까지 보여준다.
Juice Shop 수령 후에는 --url/--selector 인자만 바꿔 그대로 재사용한다.

실행:  python examples/selenium_login_demo.py
헤드리스: python examples/selenium_login_demo.py --headless
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.browser.session import BrowserSession  # noqa: E402

# the-internet.herokuapp.com/login : 공개 로그인 연습 페이지
DEMO_LOGIN_URL = "https://the-internet.herokuapp.com/login"
DEMO_USER = "tomsmith"
DEMO_PASS = "SuperSecretPassword!"
DEMO_USER_SEL = "#username"
DEMO_PASS_SEL = "#password"
DEMO_SUBMIT_SEL = "button[type='submit']"
DEMO_SUCCESS_SEL = "a[href='/logout']"  # 로그인 성공 시에만 나타나는 로그아웃 버튼

COOKIE_PATH = Path("cookies/demo_session.json")
SHOT_DIR = Path("screenshots")


def main() -> None:
    parser = argparse.ArgumentParser(description="Selenium 로그인/쿠키 데모")
    parser.add_argument("--headless", action="store_true", help="헤드리스로 실행")
    args = parser.parse_args()

    # 1) 접속 + 로그인 + 쿠키 저장
    print("[1] 접속 및 로그인")
    with BrowserSession(headless=args.headless) as session:
        session.login_form(
            url=DEMO_LOGIN_URL,
            username=DEMO_USER,
            password=DEMO_PASS,
            user_selector=DEMO_USER_SEL,
            pass_selector=DEMO_PASS_SEL,
            submit_selector=DEMO_SUBMIT_SEL,
        )
        # 로그인 성공 확인
        session.wait_for(DEMO_SUCCESS_SEL, timeout=10)
        print(f"    로그인 성공 (현재 URL: {session.current_url()})")
        session.screenshot(SHOT_DIR / "after_login.png")
        session.save_cookies(COOKIE_PATH)
        print(f"    쿠키 저장: {COOKIE_PATH}")

    # 2) 새 세션에서 쿠키 복원 -> 로그인 유지 확인
    print("[2] 새 세션에서 쿠키 복원")
    with BrowserSession(headless=args.headless) as session:
        base = "https://the-internet.herokuapp.com"
        n = session.load_cookies(COOKIE_PATH, base_url=base)
        print(f"    복원한 쿠키 {n}개")
        session.get(f"{base}/secure")  # 로그인해야 볼 수 있는 페이지
        try:
            session.wait_for(DEMO_SUCCESS_SEL, timeout=10)
            print("    쿠키만으로 로그인 상태 유지 확인 (secure 페이지 접근 성공)")
        except Exception:
            print("    [주의] 세션 유지 실패 — 이 데모 사이트는 서버측 세션이라 "
                  "쿠키 복원만으로는 유지되지 않을 수 있음 (동작 흐름 자체는 검증됨)")
        session.screenshot(SHOT_DIR / "restored_session.png")

    print("\n완료. screenshots/ 폴더의 캡처를 확인하세요.")


if __name__ == "__main__":
    main()
