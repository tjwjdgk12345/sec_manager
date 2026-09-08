"""NetworkCollector — CDP 로그에서 네트워크 경로 수집 (2-3주차).

BrowserSession 이 켜 둔 CDP performance 로그(goog:loggingPrefs)에서
Chrome DevTools Protocol 의 Network.* 이벤트를 읽어 다음을 추출한다.

  - 요청/응답 메타데이터: URL, 메서드, 상태코드, MIME, 헤더, 리소스 타입
  - API 경로: XHR/Fetch(또는 JSON 응답) 요청을 (메서드, 경로, 파라미터 이름) 단위로 정리
  - 파라미터: 쿼리스트링 + 요청 본문(form-urlencoded / JSON) 의 키 이름
  - JS 리소스: 로드된 스크립트 URL 목록

성능 로그는 읽을 때 비워지는 버퍼이므로, 네비게이션/조작 뒤에 collect()를 호출해
누적한다. get_response_body()는 CDP를 직접 호출해 응답 본문을 best-effort로 가져온다.

주의: **허용된 테스트 사이트에만** 실행한다.
이 결과는 PageExplorer 의 페이지 구조와 합쳐져 "웹 환경 프로파일"의 네트워크 부분이 된다.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urlsplit

from .session import BrowserSession


@dataclass
class RequestRecord:
    request_id: str
    url: str
    method: str
    resource_type: str = "Other"          # Document/Script/XHR/Fetch/Image ...
    status: int | None = None
    mime_type: str | None = None
    request_headers: dict[str, str] = field(default_factory=dict)
    response_headers: dict[str, str] = field(default_factory=dict)
    post_data: str | None = None
    query_params: list[str] = field(default_factory=list)
    body_params: list[str] = field(default_factory=list)
    failed: bool = False
    redirects: list[str] = field(default_factory=list)  # 리다이렉트로 거친 URL들

    @property
    def host(self) -> str:
        return (urlsplit(self.url).hostname or "").lower()

    @property
    def path(self) -> str:
        return urlsplit(self.url).path or "/"

    @property
    def is_api(self) -> bool:
        if self.resource_type in ("XHR", "Fetch"):
            return True
        return bool(self.mime_type and "json" in self.mime_type)


@dataclass
class NetworkProfile:
    scope_host: str | None
    requests: list[RequestRecord] = field(default_factory=list)

    def _scoped(self, records: list[RequestRecord]) -> list[RequestRecord]:
        if not self.scope_host:
            return records
        return [r for r in records if r.host == self.scope_host]

    def api_endpoints(self, scope_only: bool = True) -> list[dict[str, Any]]:
        """(메서드, 경로, 파라미터 이름) 단위 유일 API 엔드포인트."""
        pool = self._scoped(self.requests) if scope_only else self.requests
        seen: dict[tuple[str, str, tuple[str, ...]], dict[str, Any]] = {}
        for r in pool:
            if not r.is_api:
                continue
            params = tuple(sorted(set(r.query_params) | set(r.body_params)))
            key = (r.method, r.path, params)
            if key not in seen:
                seen[key] = {
                    "method": r.method,
                    "path": r.path,
                    "params": list(params),
                    "status": r.status,
                    "mime": r.mime_type,
                }
        return list(seen.values())

    def js_resources(self, scope_only: bool = False) -> list[str]:
        pool = self._scoped(self.requests) if scope_only else self.requests
        urls = {r.url for r in pool if r.resource_type == "Script"}
        return sorted(urls)

    def hosts(self) -> list[str]:
        return sorted({r.host for r in self.requests if r.host})

    def by_resource_type(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self.requests:
            counts[r.resource_type] = counts.get(r.resource_type, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: -kv[1]))

    def summary(self) -> dict[str, Any]:
        return {
            "scope_host": self.scope_host,
            "requests_total": len(self.requests),
            "hosts": self.hosts(),
            "resource_types": self.by_resource_type(),
            "api_endpoints": len(self.api_endpoints()),
            "js_resources": len(self.js_resources()),
            "failed": sum(1 for r in self.requests if r.failed),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary(),
            "api_endpoints": self.api_endpoints(),
            "js_resources": self.js_resources(),
            "requests": [asdict(r) for r in self.requests],
        }


class NetworkCollector:
    def __init__(
        self, session: BrowserSession, scope_host: str | None = None
    ) -> None:
        self.session = session
        self.scope_host = scope_host.lower() if scope_host else None
        self._records: dict[str, RequestRecord] = {}

    # --- 수집 --------------------------------------------------------------

    def collect(self) -> int:
        """현재까지 쌓인 performance 로그를 읽어 레코드에 반영. 처리한 이벤트 수 반환.

        get_log 는 버퍼를 비우므로, 네비게이션/클릭 등 조작 직후에 호출한다.
        """
        try:
            entries = self.session.driver.get_log("performance")
        except Exception:  # noqa: BLE001 - 로깅 비활성 등
            return 0

        n = 0
        for entry in entries:
            try:
                msg = json.loads(entry["message"])["message"]
            except (KeyError, json.JSONDecodeError):
                continue
            method = msg.get("method", "")
            params = msg.get("params", {})
            if not method.startswith("Network."):
                continue
            n += 1
            self._handle(method, params)
        return n

    def _rec(self, rid: str, url: str = "", http_method: str = "GET") -> RequestRecord:
        rec = self._records.get(rid)
        if rec is None:
            rec = RequestRecord(request_id=rid, url=url, method=http_method)
            self._records[rid] = rec
        return rec

    def _handle(self, method: str, params: dict[str, Any]) -> None:
        rid = params.get("requestId", "")
        if not rid:
            return

        if method == "Network.requestWillBeSent":
            req = params.get("request", {}) or {}
            # 리다이렉트인 경우: 이전 URL을 체인에 남기고 새 URL로 갱신
            redirect_prev = None
            if params.get("redirectResponse") and rid in self._records:
                redirect_prev = self._records[rid].url

            rec = self._rec(rid, req.get("url", ""), req.get("method", "GET"))
            if redirect_prev:
                rec.redirects.append(redirect_prev)
            rec.url = req.get("url", rec.url)
            rec.method = req.get("method", rec.method)
            rec.resource_type = params.get("type", rec.resource_type)
            rec.request_headers = {
                k: v for k, v in (req.get("headers", {}) or {}).items()
            }
            rec.query_params = _query_keys(rec.url)
            post = req.get("postData")
            if post is not None:
                rec.post_data = post if isinstance(post, str) else json.dumps(post)
                rec.body_params = _body_keys(rec.post_data, rec.request_headers)

        elif method == "Network.responseReceived":
            resp = params.get("response", {}) or {}
            rec = self._rec(rid, resp.get("url", ""))
            rec.status = resp.get("status", rec.status)
            rec.mime_type = resp.get("mimeType", rec.mime_type)
            rec.response_headers = {
                k: v for k, v in (resp.get("headers", {}) or {}).items()
            }
            if params.get("type"):
                rec.resource_type = params["type"]

        elif method == "Network.loadingFailed":
            rec = self._rec(rid)
            rec.failed = True

    # --- 출력 --------------------------------------------------------------

    def snapshot(self) -> NetworkProfile:
        self.collect()  # 마지막 남은 로그까지 반영
        return NetworkProfile(
            scope_host=self.scope_host, requests=list(self._records.values())
        )

    def reset(self) -> None:
        self._records.clear()

    # --- best-effort 응답 본문 (탐지기용 확장) -----------------------------

    def get_response_body(self, request_id: str) -> str | None:
        """CDP Network.getResponseBody 로 응답 본문을 시도한다.

        버퍼에서 이미 사라졌으면 실패할 수 있으므로 best-effort 다.
        (5-6주차 탐지기에서 오류 메시지/반영 확인용으로 활용 예정)
        """
        try:
            result = self.session.driver.execute_cdp_cmd(
                "Network.getResponseBody", {"requestId": request_id}
            )
            return result.get("body")
        except Exception:  # noqa: BLE001
            return None


# --- 유틸 ------------------------------------------------------------------

def _query_keys(url: str) -> list[str]:
    q = urlsplit(url).query
    keys: list[str] = []
    for part in q.split("&"):
        if not part:
            continue
        k = part.split("=", 1)[0]
        if k:
            keys.append(k)
    return keys


def _body_keys(post_data: str, headers: dict[str, str]) -> list[str]:
    """요청 본문에서 파라미터 키 이름 추출 (form-urlencoded / JSON)."""
    ctype = ""
    for k, v in headers.items():
        if k.lower() == "content-type":
            ctype = (v or "").lower()
            break

    if "application/json" in ctype or (
        not ctype and post_data.strip().startswith("{")
    ):
        try:
            obj = json.loads(post_data)
            if isinstance(obj, dict):
                return list(obj.keys())
        except json.JSONDecodeError:
            return []
        return []

    # 기본: form-urlencoded 로 간주
    keys: list[str] = []
    for part in post_data.split("&"):
        if not part:
            continue
        k = part.split("=", 1)[0]
        if k:
            keys.append(k)
    return keys
