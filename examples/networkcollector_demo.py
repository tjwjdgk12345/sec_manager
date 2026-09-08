"""2-3주차 예제: NetworkCollector 로 네트워크 경로 수집.

허용된 테스트 사이트에서만 실행한다. 기본 대상 httpbin.org 의 첫 화면은
Swagger UI 라서 로드 시 OpenAPI 스펙을 XHR 로 받아온다 → API/XHR 캡처를 보여주기 좋다.

실행:
    python examples/networkcollector_demo.py
    python examples/networkcollector_demo.py --url https://httpbin.org --headless
    # Juice Shop(REST API) 수령 후:
    python examples/networkcollector_demo.py --url http://localhost:3000 --spa
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.browser.network import NetworkCollector  # noqa: E402
from src.browser.session import BrowserSession  # noqa: E402

DEFAULT_URL = "https://httpbin.org"


def main() -> None:
    parser = argparse.ArgumentParser(description="NetworkCollector 데모")
    parser.add_argument("--url", default=DEFAULT_URL, help="방문할 URL")
    parser.add_argument("--headless", action="store_true", help="헤드리스 실행")
    parser.add_argument("--settle", type=float, default=2.5, help="로드 후 대기(초)")
    parser.add_argument(
        "--out", default="reports/network_profile.json", help="결과 저장 경로"
    )
    args = parser.parse_args()

    scope = (urlsplit(args.url).hostname or "").lower()
    print(f"대상: {args.url} (scope_host={scope})")
    print("주의: 허용된 테스트 사이트에만 실행하세요.\n")

    with BrowserSession(headless=args.headless) as session:
        collector = NetworkCollector(session, scope_host=scope)
        session.get(args.url)
        time.sleep(args.settle)          # XHR/리소스 로드 대기
        collector.collect()              # 성능 로그 수집
        profile = collector.snapshot()

    summary = profile.summary()
    print("=== 네트워크 요약 ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    print("\n=== 리소스 타입별 요청 수 ===")
    for rtype, cnt in profile.by_resource_type().items():
        print(f"  {rtype}: {cnt}")

    apis = profile.api_endpoints()
    print(f"\n=== API 엔드포인트 {len(apis)}개 (스코프 내 XHR/Fetch/JSON) ===")
    for ep in apis[:15]:
        params = f"  params={ep['params']}" if ep["params"] else ""
        print(f"  [{ep['method']}] {ep['path']}  ({ep['status']}, {ep['mime']}){params}")

    js = profile.js_resources()
    print(f"\n=== JS 리소스 {len(js)}개 (상위 10) ===")
    for u in js[:10]:
        print(f"  {u}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(profile.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n프로파일 저장: {out}")


if __name__ == "__main__":
    main()
