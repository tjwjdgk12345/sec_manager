"""PageExplorer — 동일 호스트 내 페이지 구조 탐색기 (2-3주차).

주어진 시작 URL에서 시작해 BFS로 같은 호스트의 페이지를 돌면서
각 페이지의 링크 / 폼 / 버튼 / 입력 필드를 구조화해 수집한다.

핵심 기능:
  - 동일 호스트 스코프 제한 (서브도메인 포함 여부 선택)
  - 중복 방문 방지 (URL 정규화 후 visited 집합)
  - 탐색 깊이(max_depth) · 페이지 수(max_pages) 상한
  - 엔드포인트당 변형 수 상한(max_per_endpoint)으로 파라미터 폭발 억제
  - SPA 해시 라우팅(#/...) 대응 옵션 (Juice Shop 대비)

주의: **허용된 테스트 사이트에만** 실행한다. 요청 간 delay로 부하를 억제한다.

출력(CrawlResult)은 이후 NetworkCollector 결과와 합쳐져
탐지기(Detector)가 쓰는 "웹 환경 프로파일"의 페이지 구조 부분이 된다.
"""

from __future__ import annotations

import time
from collections import Counter, deque
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

from .session import BrowserSession

# 페이지에서 링크/폼/버튼/입력을 한 번에 뽑아오는 브라우저측 스크립트.
# JS 렌더링이 끝난 최종 DOM을 기준으로 하므로 SPA에도 어느 정도 대응된다.
_EXTRACT_JS = r"""
const abs = (u) => { try { return new URL(u, document.baseURI).href; } catch (e) { return null; } };
const cut = (s, n) => (s || '').replace(/\s+/g, ' ').trim().slice(0, n);

const linkNodes = Array.from(document.querySelectorAll('a[href], [routerLink]'));
const links = linkNodes.map(a => {
  const raw = a.getAttribute('href') || a.getAttribute('routerLink') || '';
  return { href: abs(raw), raw: raw, text: cut(a.textContent, 80) };
}).filter(l => l.href);

const fieldOf = (i) => ({
  name: i.getAttribute('name'),
  type: (i.getAttribute('type') || i.tagName || '').toLowerCase(),
  id: i.id || null,
  placeholder: i.getAttribute('placeholder') || null,
  required: i.hasAttribute('required')
});

const forms = Array.from(document.querySelectorAll('form')).map(f => ({
  action: abs(f.getAttribute('action') || '') || abs(document.baseURI),
  method: (f.getAttribute('method') || 'get').toLowerCase(),
  id: f.id || null,
  name: f.getAttribute('name') || null,
  inputs: Array.from(f.querySelectorAll('input, textarea, select')).map(fieldOf)
}));

const buttons = Array.from(
  document.querySelectorAll('button, input[type=submit], input[type=button], [role=button]')
).map(b => cut(b.textContent || b.value, 60)).filter(Boolean);

const standalone = Array.from(document.querySelectorAll('input, textarea, select'))
  .filter(i => !i.closest('form')).map(fieldOf);

return { title: document.title || '', links, forms, buttons, inputs: standalone };
"""


@dataclass
class InputField:
    name: str | None
    type: str | None
    id: str | None = None
    placeholder: str | None = None
    required: bool = False


@dataclass
class FormInfo:
    action: str
    method: str
    inputs: list[InputField] = field(default_factory=list)
    id: str | None = None
    name: str | None = None


@dataclass
class LinkInfo:
    url: str
    text: str
    in_scope: bool


@dataclass
class PageProfile:
    url: str                 # 정규화된 방문 URL
    final_url: str           # 리다이렉트 후 실제 URL
    title: str
    depth: int
    param_names: list[str] = field(default_factory=list)   # 이 URL의 쿼리 파라미터 이름
    links: list[LinkInfo] = field(default_factory=list)
    forms: list[FormInfo] = field(default_factory=list)
    buttons: list[str] = field(default_factory=list)
    inputs: list[InputField] = field(default_factory=list)  # 폼 밖 단독 입력
    error: str | None = None


@dataclass
class CrawlResult:
    seed: str
    scope_host: str
    pages: dict[str, PageProfile] = field(default_factory=dict)

    # --- 파생 요약 -------------------------------------------------------
    def endpoints(self) -> list[dict[str, Any]]:
        """(경로, 파라미터 이름 집합) 단위로 유일한 엔드포인트 목록."""
        seen: dict[tuple[str, tuple[str, ...]], dict[str, Any]] = {}
        for prof in self.pages.values():
            key = (urlsplit(prof.url).path, tuple(sorted(prof.param_names)))
            if key not in seen:
                seen[key] = {"path": key[0], "params": list(key[1])}
        return list(seen.values())

    def all_forms(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for prof in self.pages.values():
            for fm in prof.forms:
                out.append({"page": prof.url, **asdict(fm)})
        return out

    def summary(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "scope_host": self.scope_host,
            "pages_visited": len(self.pages),
            "unique_endpoints": len(self.endpoints()),
            "forms_total": sum(len(p.forms) for p in self.pages.values()),
            "inputs_total": sum(
                len(p.inputs) + sum(len(f.inputs) for f in p.forms)
                for p in self.pages.values()
            ),
            "errors": [p.url for p in self.pages.values() if p.error],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary(),
            "endpoints": self.endpoints(),
            "pages": {u: asdict(p) for u, p in self.pages.items()},
        }


class PageExplorer:
    def __init__(
        self,
        session: BrowserSession,
        max_depth: int = 2,
        max_pages: int = 30,
        max_per_endpoint: int = 3,
        include_subdomains: bool = False,
        keep_fragment: bool = False,
        delay: float = 0.5,
        settle: float = 0.8,
        verbose: bool = True,
    ) -> None:
        """
        max_per_endpoint : 같은 (경로+파라미터이름) 조합을 몇 개까지 방문할지
                           (예: /product?id=1,2,3... 무한 크롤 방지)
        include_subdomains: True면 *.example.com 도 스코프로 인정
        keep_fragment    : True면 #/route 같은 SPA 해시 라우트를 서로 다른 페이지로 취급
                           (Juice Shop 등 Angular 앱 크롤 시 사용)
        settle           : 페이지 로드 후 JS 렌더링을 기다리는 추가 대기(초)
        """
        self.session = session
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.max_per_endpoint = max_per_endpoint
        self.include_subdomains = include_subdomains
        self.keep_fragment = keep_fragment
        self.delay = delay
        self.settle = settle
        self.verbose = verbose

    def _log(self, *a: Any) -> None:
        if self.verbose:
            print(*a)

    # --- URL 처리 ----------------------------------------------------------

    def _normalize(self, url: str) -> str:
        p = urlsplit(url)
        host = (p.hostname or "").lower()
        netloc = host + (f":{p.port}" if p.port else "")
        path = p.path or "/"
        if len(path) > 1 and path.endswith("/"):
            path = path.rstrip("/")
        fragment = p.fragment if self.keep_fragment else ""
        return urlunsplit((p.scheme.lower(), netloc, path, p.query, fragment))

    def _in_scope(self, url: str) -> bool:
        p = urlsplit(url)
        if p.scheme not in ("http", "https"):
            return False
        host = (p.hostname or "").lower()
        if host == self.scope_host:
            return True
        if self.include_subdomains and host.endswith("." + self.scope_host):
            return True
        return False

    def _endpoint_key(self, url: str) -> tuple[str, tuple[str, ...], str]:
        p = urlsplit(url)
        params = tuple(sorted(k for k, _ in _parse_qs_keys(p.query)))
        route = p.fragment if self.keep_fragment else ""
        return (p.path or "/", params, route)

    # --- 탐색 --------------------------------------------------------------

    def crawl(self, seed_url: str) -> CrawlResult:
        seed_norm = self._normalize(seed_url)
        self.scope_host = (urlsplit(seed_norm).hostname or "").lower()

        result = CrawlResult(seed=seed_norm, scope_host=self.scope_host)
        visited: set[str] = set()
        endpoint_count: Counter[tuple[str, tuple[str, ...], str]] = Counter()
        queue: deque[tuple[str, int]] = deque([(seed_norm, 0)])

        while queue and len(result.pages) < self.max_pages:
            url, depth = queue.popleft()
            if url in visited:
                continue
            visited.add(url)

            profile = self._visit(url, depth)
            result.pages[url] = profile
            self._log(
                f"[{len(result.pages):>3}] depth={depth} "
                f"forms={len(profile.forms)} links={len(profile.links)} {url}"
                + (f"  ERROR: {profile.error}" if profile.error else "")
            )

            if profile.error or depth >= self.max_depth:
                time.sleep(self.delay)
                continue

            for link in profile.links:
                if not link.in_scope:
                    continue
                nurl = self._normalize(link.url)
                if nurl in visited:
                    continue
                key = self._endpoint_key(nurl)
                if endpoint_count[key] >= self.max_per_endpoint:
                    continue
                endpoint_count[key] += 1
                queue.append((nurl, depth + 1))

            time.sleep(self.delay)

        return result

    def _visit(self, url: str, depth: int) -> PageProfile:
        try:
            self.session.get(url)
            if self.settle:
                time.sleep(self.settle)
            data = self.session.driver.execute_script(_EXTRACT_JS)
        except Exception as exc:  # noqa: BLE001 - 개별 페이지 실패는 기록만
            return PageProfile(
                url=url, final_url=url, title="", depth=depth, error=str(exc)[:200]
            )

        links = [
            LinkInfo(
                url=l["href"],
                text=l.get("text", ""),
                in_scope=self._in_scope(l["href"]),
            )
            for l in data.get("links", [])
        ]
        forms = [
            FormInfo(
                action=f.get("action") or url,
                method=f.get("method", "get"),
                id=f.get("id"),
                name=f.get("name"),
                inputs=[InputField(**_field(i)) for i in f.get("inputs", [])],
            )
            for f in data.get("forms", [])
        ]
        inputs = [InputField(**_field(i)) for i in data.get("inputs", [])]

        return PageProfile(
            url=url,
            final_url=self.session.current_url(),
            title=data.get("title", ""),
            depth=depth,
            param_names=[k for k, _ in _parse_qs_keys(urlsplit(url).query)],
            links=links,
            forms=forms,
            buttons=data.get("buttons", []),
            inputs=inputs,
        )


# --- 작은 유틸 -------------------------------------------------------------

def _field(raw: dict[str, Any]) -> dict[str, Any]:
    """JS에서 온 필드 dict를 InputField 인자로 정리."""
    return {
        "name": raw.get("name"),
        "type": raw.get("type"),
        "id": raw.get("id"),
        "placeholder": raw.get("placeholder"),
        "required": bool(raw.get("required")),
    }


def _parse_qs_keys(query: str) -> list[tuple[str, str]]:
    """빈 값도 보존하며 (key, value) 쌍 목록 반환."""
    pairs: list[tuple[str, str]] = []
    for part in query.split("&"):
        if not part:
            continue
        k, _, v = part.partition("=")
        pairs.append((k, v))
    return pairs
