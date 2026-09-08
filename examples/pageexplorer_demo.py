"""2-3주차 예제: PageExplorer 로 사이트 구조 탐색.

허용된 테스트 사이트에서만 실행한다. 기본 대상은 공개 연습 사이트다.
결과(웹 환경 프로파일 초안)를 reports/ 아래 JSON 으로 저장한다.

실행:
    python examples/pageexplorer_demo.py
    python examples/pageexplorer_demo.py --url https://the-internet.herokuapp.com --depth 1 --max-pages 12
    # Juice Shop(SPA) 수령 후:
    python examples/pageexplorer_demo.py --url http://localhost:3000 --spa --depth 2
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.browser.explorer import PageExplorer  # noqa: E402
from src.browser.session import BrowserSession  # noqa: E402

DEFAULT_URL = "https://the-internet.herokuapp.com"


def main() -> None:
    parser = argparse.ArgumentParser(description="PageExplorer 데모")
    parser.add_argument("--url", default=DEFAULT_URL, help="탐색 시작 URL")
    parser.add_argument("--depth", type=int, default=1, help="최대 탐색 깊이")
    parser.add_argument("--max-pages", type=int, default=12, help="최대 방문 페이지 수")
    parser.add_argument(
        "--spa",
        action="store_true",
        help="SPA 해시 라우팅(#/route)을 개별 페이지로 취급 (Juice Shop 등)",
    )
    parser.add_argument("--subdomains", action="store_true", help="서브도메인 포함")
    parser.add_argument("--headless", action="store_true", help="헤드리스 실행")
    parser.add_argument(
        "--out", default="reports/site_profile.json", help="결과 저장 경로"
    )
    args = parser.parse_args()

    print(f"대상: {args.url} (depth={args.depth}, max_pages={args.max_pages})")
    print("주의: 허용된 테스트 사이트에만 실행하세요.\n")

    with BrowserSession(headless=args.headless) as session:
        explorer = PageExplorer(
            session,
            max_depth=args.depth,
            max_pages=args.max_pages,
            include_subdomains=args.subdomains,
            keep_fragment=args.spa,
        )
        result = explorer.crawl(args.url)

    summary = result.summary()
    print("\n=== 탐색 요약 ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    print(f"\n유일 엔드포인트 {len(result.endpoints())}개 (상위 10):")
    for ep in result.endpoints()[:10]:
        params = f"?{','.join(ep['params'])}" if ep["params"] else ""
        print(f"  {ep['path']}{params}")

    forms = result.all_forms()
    print(f"\n발견한 폼 {len(forms)}개:")
    for fm in forms[:10]:
        fields = ", ".join(
            f"{i['name']}:{i['type']}" for i in fm["inputs"] if i.get("name")
        )
        print(f"  [{fm['method'].upper()}] {fm['action']}  ({fields})")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n프로파일 저장: {out}")


if __name__ == "__main__":
    main()
