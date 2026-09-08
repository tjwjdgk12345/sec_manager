"""2-3주차 마무리 예제: 웹 환경 프로파일 결합.

PageExplorer + NetworkCollector 를 한 번의 정찰로 묶어, 탐지기가 쓸
통합 프로파일(입력 지점 목록 포함)을 만들고 reports/ 에 저장한다.

허용된 테스트 사이트에만 실행한다.

실행:
    python examples/webprofile_demo.py --headless --depth 1 --max-pages 12
    python examples/webprofile_demo.py --url https://httpbin.org --headless
    # Juice Shop 수령 후:
    python examples/webprofile_demo.py --url http://localhost:3000 --spa --depth 2
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

from src.recon.profile import ReconRunner  # noqa: E402

DEFAULT_URL = "https://the-internet.herokuapp.com"


def main() -> None:
    parser = argparse.ArgumentParser(description="웹 환경 프로파일 결합 데모")
    parser.add_argument("--url", default=DEFAULT_URL, help="대상 URL")
    parser.add_argument("--depth", type=int, default=1, help="최대 탐색 깊이")
    parser.add_argument("--max-pages", type=int, default=12, help="최대 방문 페이지 수")
    parser.add_argument("--spa", action="store_true", help="SPA 해시 라우팅 취급")
    parser.add_argument("--subdomains", action="store_true", help="서브도메인 포함")
    parser.add_argument("--headless", action="store_true", help="헤드리스 실행")
    parser.add_argument(
        "--out", default="reports/web_profile.json", help="결과 저장 경로"
    )
    args = parser.parse_args()

    print(f"대상: {args.url} (depth={args.depth}, max_pages={args.max_pages})")
    print("주의: 허용된 테스트 사이트에만 실행하세요.\n")

    runner = ReconRunner(
        headless=args.headless,
        max_depth=args.depth,
        max_pages=args.max_pages,
        keep_fragment=args.spa,
        include_subdomains=args.subdomains,
    )
    profile = runner.run(args.url)

    summary = profile.summary()
    print("\n=== 웹 환경 프로파일 요약 ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    print(f"\n=== 입력 지점(공격 표면) {len(profile.input_points)}개 (상위 20) ===")
    for ip in profile.input_points[:20]:
        t = f":{ip.input_type}" if ip.input_type else ""
        print(
            f"  [{ip.kind}] [{ip.method}] {ip.location}  "
            f"param={ip.param}{t}  hint={','.join(ip.vuln_hint)}"
        )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(profile.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n프로파일 저장: {out}")


if __name__ == "__main__":
    main()
