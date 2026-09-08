"""웹 환경 프로파일 결합 (2-3주차 마무리).

PageExplorer(페이지 구조)와 NetworkCollector(네트워크 경로)의 결과를 하나로 합쳐
탐지기(XSS/SQLi/IDOR Detector)가 그대로 순회할 수 있는 통합 프로파일을 만든다.

핵심 산출물은 **입력 지점(InputPoint) 목록** — 공격 표면(injection surface)이다.
각 입력 지점은 "어디에(location) 어떤 방법으로(method) 어떤 값을(param) 넣을 수 있는가"를
정규화해, 이후 각 Detector가 vuln_type 에 맞춰 페이로드를 주입할 대상이 된다.

  - query      : URL 쿼리 파라미터 (GET)
  - form       : HTML 폼 필드 (method/action 기준)
  - api_param  : XHR/Fetch API 의 쿼리/본문 파라미터
  - path_id    : 경로에 박힌 식별자(숫자/UUID) — 주로 IDOR 후보

ReconRunner 는 세션 하나에서 크롤 + 네트워크 수집 + 프로파일 결합을 한 번에 수행한다.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urlsplit

from ..browser.explorer import CrawlResult, PageExplorer
from ..browser.network import NetworkCollector, NetworkProfile
from ..browser.session import BrowserSession

# 경로 세그먼트가 식별자(IDOR 후보)로 보이는지 판단하는 패턴
_NUMERIC_RE = re.compile(r"^\d+$")
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_HEXID_RE = re.compile(r"^[0-9a-fA-F]{16,}$")


@dataclass
class InputPoint:
    kind: str                 # query | form | api_param | path_id
    method: str               # GET | POST | ...
    location: str             # 대상 경로/URL (path 우선)
    param: str                # 파라미터/필드 이름 또는 식별자 위치 표기
    input_type: str | None = None  # 폼 필드 타입(text/password/hidden 등)
    source: str = ""          # 어디서 발견했는지 (디버그/증거용)
    vuln_hint: list[str] = field(default_factory=list)  # 우선 시도할 취약점 유형

    def key(self) -> tuple[str, str, str, str]:
        return (self.kind, self.method, self.location, self.param)


@dataclass
class WebProfile:
    target: str
    scope_host: str
    crawl: CrawlResult
    network: NetworkProfile
    input_points: list[InputPoint] = field(default_factory=list)

    def input_points_by_kind(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for ip in self.input_points:
            counts[ip.kind] = counts.get(ip.kind, 0) + 1
        return counts

    def summary(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "scope_host": self.scope_host,
            "pages_visited": len(self.crawl.pages),
            "unique_page_endpoints": len(self.crawl.endpoints()),
            "api_endpoints": len(self.network.api_endpoints()),
            "forms": len(self.crawl.all_forms()),
            "input_points": len(self.input_points),
            "input_points_by_kind": self.input_points_by_kind(),
            "hosts_contacted": self.network.hosts(),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary(),
            "input_points": [asdict(ip) for ip in self.input_points],
            "page_structure": self.crawl.to_dict(),
            "network": self.network.to_dict(),
        }


def _looks_like_id(segment: str) -> bool:
    return bool(
        _NUMERIC_RE.match(segment)
        or _UUID_RE.match(segment)
        or _HEXID_RE.match(segment)
    )


def build_web_profile(
    target: str,
    crawl: CrawlResult,
    network: NetworkProfile,
) -> WebProfile:
    """크롤 결과 + 네트워크 결과 → 통합 프로파일(입력 지점 목록 포함)."""
    scope_host = crawl.scope_host
    points: dict[tuple[str, str, str, str], InputPoint] = {}

    def add(ip: InputPoint) -> None:
        points.setdefault(ip.key(), ip)

    # 1) 폼 필드 → form 입력 지점
    for fm in crawl.all_forms():
        method = (fm.get("method") or "get").upper()
        action = fm.get("action") or fm.get("page") or ""
        loc = urlsplit(action).path or action
        for i in fm.get("inputs", []):
            name = i.get("name")
            if not name:
                continue
            itype = (i.get("type") or "").lower()
            # 값을 담는 필드만 (버튼/서브밋 제외)
            if itype in ("submit", "button", "reset", "image"):
                continue
            hint = ["xss", "sqli"] if method == "POST" else ["xss", "sqli"]
            add(
                InputPoint(
                    kind="form",
                    method=method,
                    location=loc,
                    param=name,
                    input_type=itype or None,
                    source=f"page:{fm.get('page','')} form#{fm.get('id') or '-'}",
                    vuln_hint=hint,
                )
            )

    # 2) 페이지 URL 쿼리 파라미터 → query 입력 지점
    for prof in crawl.pages.values():
        path = urlsplit(prof.url).path or "/"
        for pname in prof.param_names:
            add(
                InputPoint(
                    kind="query",
                    method="GET",
                    location=path,
                    param=pname,
                    source=f"page:{prof.url}",
                    vuln_hint=["xss", "sqli", "idor"],
                )
            )

    # 3) API 엔드포인트 파라미터 → api_param 입력 지점
    for ep in network.api_endpoints():
        for pname in ep.get("params", []):
            add(
                InputPoint(
                    kind="api_param",
                    method=ep.get("method", "GET"),
                    location=ep.get("path", ""),
                    param=pname,
                    source=f"api:{ep.get('method')} {ep.get('path')}",
                    vuln_hint=["sqli", "idor", "xss"],
                )
            )

    # 4) 경로 식별자 → path_id 입력 지점 (IDOR 후보)
    #    페이지 URL + API 경로 모두에서 숫자/UUID 세그먼트를 찾는다.
    api_paths = [ep.get("path", "") for ep in network.api_endpoints()]
    page_paths = [urlsplit(p.url).path for p in crawl.pages.values()]
    for path in set(api_paths) | set(page_paths):
        segs = [s for s in path.split("/") if s]
        for idx, seg in enumerate(segs):
            if _looks_like_id(seg):
                # 식별자 위치를 템플릿으로 표기 (예: /rest/user/{id})
                templated = "/" + "/".join(
                    ("{id}" if j == idx else s) for j, s in enumerate(segs)
                )
                add(
                    InputPoint(
                        kind="path_id",
                        method="GET",
                        location=templated,
                        param=f"seg[{idx}]={seg}",
                        source=f"path:{path}",
                        vuln_hint=["idor"],
                    )
                )

    return WebProfile(
        target=target,
        scope_host=scope_host,
        crawl=crawl,
        network=network,
        input_points=list(points.values()),
    )


class ReconRunner:
    """세션 하나로 크롤 + 네트워크 수집 + 프로파일 결합을 수행하는 오케스트레이터."""

    def __init__(
        self,
        headless: bool = True,
        max_depth: int = 2,
        max_pages: int = 30,
        keep_fragment: bool = False,
        include_subdomains: bool = False,
        verbose: bool = True,
    ) -> None:
        self.headless = headless
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.keep_fragment = keep_fragment
        self.include_subdomains = include_subdomains
        self.verbose = verbose

    def run(self, target_url: str) -> WebProfile:
        scope = (urlsplit(target_url).hostname or "").lower()
        with BrowserSession(headless=self.headless) as session:
            collector = NetworkCollector(session, scope_host=scope)
            explorer = PageExplorer(
                session,
                max_depth=self.max_depth,
                max_pages=self.max_pages,
                keep_fragment=self.keep_fragment,
                include_subdomains=self.include_subdomains,
                verbose=self.verbose,
                # 각 페이지 방문 직후 네트워크 로그를 수집해 크롤과 동기화
                after_visit=lambda _p: collector.collect(),
            )
            crawl = explorer.crawl(target_url)
            network = collector.snapshot()
        return build_web_profile(target_url, crawl, network)
