"""Selenium 기반 브라우저 세션.

1주차 목표인 "접속 / 로그인 / 쿠키 유지"를 담당한다.
Selenium 4의 내장 Selenium Manager가 ChromeDriver를 자동 관리하므로
드라이버를 수동으로 내려받을 필요가 없다.

쿠키를 파일로 저장/복원해 로그인 세션을 재사용할 수 있게 한다.
이후 PageExplorer / NetworkCollector가 이 세션 위에서 동작한다.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


class BrowserSession:
    def __init__(
        self,
        headless: bool = False,
        window_size: tuple[int, int] = (1280, 900),
        page_load_timeout: int = 30,
        enable_cdp_logging: bool = True,
    ) -> None:
        options = Options()
        if headless:
            options.add_argument("--headless=new")
        options.add_argument(f"--window-size={window_size[0]},{window_size[1]}")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        if enable_cdp_logging:
            # CDP performance 로그(네트워크 요청 메타데이터) 수집용.
            # NetworkCollector(2-3주차)에서 driver.get_log("performance") 로 읽는다.
            options.set_capability(
                "goog:loggingPrefs", {"performance": "ALL", "browser": "ALL"}
            )

        self.driver = webdriver.Chrome(options=options)
        self.driver.set_page_load_timeout(page_load_timeout)

    # --- 기본 탐색 ---------------------------------------------------------

    def get(self, url: str) -> None:
        self.driver.get(url)

    def current_url(self) -> str:
        return self.driver.current_url

    def wait_for(self, css_selector: str, timeout: int = 15):
        return WebDriverWait(self.driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, css_selector))
        )

    # --- 로그인 (폼 기반 범용 헬퍼) ---------------------------------------

    def login_form(
        self,
        url: str,
        username: str,
        password: str,
        user_selector: str,
        pass_selector: str,
        submit_selector: str,
        settle_seconds: float = 1.5,
    ) -> None:
        """CSS 셀렉터로 지정한 폼에 자격증명을 입력하고 제출한다.

        대상별로 셀렉터만 바꾸면 재사용 가능(Juice Shop 포함).
        """
        self.driver.get(url)
        self.wait_for(user_selector).send_keys(username)
        self.driver.find_element(By.CSS_SELECTOR, pass_selector).send_keys(password)
        self.driver.find_element(By.CSS_SELECTOR, submit_selector).click()
        time.sleep(settle_seconds)  # 리다이렉트/토큰 저장 정착 대기

    # --- 쿠키 저장/복원으로 세션 유지 -------------------------------------

    def save_cookies(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.driver.get_cookies(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load_cookies(self, path: str | Path, base_url: str | None = None) -> int:
        """저장한 쿠키를 현재 세션에 주입한다.

        쿠키는 같은 도메인에서만 설정되므로, base_url이 주어지면 먼저 방문한다.
        반환값은 주입에 성공한 쿠키 수.
        """
        path = Path(path)
        cookies: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
        if base_url:
            self.driver.get(base_url)

        added = 0
        for cookie in cookies:
            cookie.pop("sameSite", None)  # 일부 값은 add_cookie가 거부함
            try:
                self.driver.add_cookie(cookie)
                added += 1
            except Exception:  # noqa: BLE001 - 개별 쿠키 실패는 건너뜀
                continue
        return added

    def screenshot(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.driver.save_screenshot(str(path))

    # --- 정리 --------------------------------------------------------------

    def quit(self) -> None:
        try:
            self.driver.quit()
        except Exception:  # noqa: BLE001
            pass

    def __enter__(self) -> "BrowserSession":
        return self

    def __exit__(self, *exc: object) -> None:
        self.quit()
