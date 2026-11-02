"""HTTP client shared by all Api* repositories: auth, timeout, retry/backoff, 429 handling,
client-side rate limit, pagination, TTL cache (stale-if-error) and logging. Secrets are never logged."""
import logging
import threading
import time
import httpx

log = logging.getLogger("superchat.api")
RETRY_STATUS = {429, 500, 502, 503, 504}
ITEM_KEYS = ("items", "results", "data")


class ApiError(Exception):
    """Data source unavailable or returned an unusable response (message is safe to log, never has secrets)."""


class ApiClient:
    def __init__(self, name, base_url, api_key="", auth_header="Authorization", timeout=5.0, retries=3,
                 cache_ttl=60.0, max_rps=0.0, page_size=100, transport=None, sleep=time.sleep):
        if not base_url:
            raise ApiError(f"{name}: base URL is not configured")
        self.name, self.page_size, self.retries, self.cache_ttl = name, page_size, retries, cache_ttl
        self._sleep, self._min_gap, self._last_call = sleep, (1.0 / max_rps if max_rps > 0 else 0.0), 0.0
        headers = {"Accept": "application/json"}
        if api_key:
            headers[auth_header] = f"Bearer {api_key}" if auth_header.lower() == "authorization" else api_key
        self._http = httpx.Client(base_url=base_url.rstrip("/"), headers=headers, timeout=timeout, transport=transport)
        self._cache, self._lock = {}, threading.Lock()

    def _throttle(self):
        if self._min_gap:
            with self._lock:
                wait = self._last_call + self._min_gap - time.monotonic()
                if wait > 0:
                    self._sleep(wait)
                self._last_call = time.monotonic()

    def request(self, method, path, **kw):
        """Returns the httpx.Response (any non-retryable status, incl. 404/409). Raises ApiError when exhausted."""
        last = "unknown error"
        for attempt in range(self.retries):
            self._throttle()
            t0 = time.monotonic()
            try:
                r = self._http.request(method, path, **kw)
            except httpx.HTTPError as e:
                last = type(e).__name__
                log.warning("%s %s %s failed (%s) attempt %d/%d", self.name, method, path, last, attempt + 1, self.retries)
                r = None
            else:
                log.info("%s %s %s -> %d in %dms", self.name, method, path, r.status_code, (time.monotonic() - t0) * 1000)
                if r.status_code not in RETRY_STATUS:
                    return r
                last = f"HTTP {r.status_code}"
            if attempt < self.retries - 1:
                delay = 0.5 * 2 ** attempt
                if r is not None and r.headers.get("Retry-After", "").isdigit():
                    delay = min(int(r.headers["Retry-After"]), 5)
                self._sleep(delay)
        raise ApiError(f"{self.name}: {last} after {self.retries} attempts")

    def _json(self, r):
        if r.status_code >= 400:
            raise ApiError(f"{self.name}: HTTP {r.status_code}")
        try:
            return r.json()
        except ValueError:
            raise ApiError(f"{self.name}: invalid JSON response")

    @staticmethod
    def _items(body):
        if isinstance(body, list):
            return body
        if isinstance(body, dict):
            for k in ITEM_KEYS:
                if isinstance(body.get(k), list):
                    return body[k]
        raise ApiError("unexpected list response shape")

    def get_all(self, path, max_pages=50):
        """Follows ?page=N&page_size=M until a short/empty page."""
        out = []
        for page in range(1, max_pages + 1):
            items = self._items(self._json(self.request("GET", path, params={"page": page, "page_size": self.page_size})))
            out += items
            if len(items) < self.page_size:
                break
        return out

    def get_one(self, path):
        r = self.request("GET", path)
        return None if r.status_code == 404 else self._json(r)

    def cached(self, key, loader):
        """TTL cache; on loader failure serve stale data if we have any (latency/outage resilience)."""
        now = time.monotonic()
        with self._lock:
            hit = self._cache.get(key)
        if hit and now - hit[0] < self.cache_ttl:
            return hit[1]
        try:
            val = loader()
        except ApiError:
            if hit:
                log.warning("%s serving stale cache for %s", self.name, key)
                return hit[1]
            raise
        with self._lock:
            self._cache[key] = (time.monotonic(), val)
        return val

    def peek(self, key):
        """Fresh cached value or None (never calls the API)."""
        with self._lock:
            hit = self._cache.get(key)
        return hit[1] if hit and time.monotonic() - hit[0] < self.cache_ttl else None

    def invalidate(self):
        with self._lock:
            self._cache.clear()
