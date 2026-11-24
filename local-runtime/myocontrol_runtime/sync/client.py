import json
import urllib.error
import urllib.parse
import urllib.request


class CloudError(Exception):
    def __init__(self, message, status=0, retry_after=None):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


def validate_url(value):
    parsed = urllib.parse.urlsplit(value)
    loopback = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or (parsed.scheme == "http" and not loopback)
    ):
        raise ValueError("Use HTTPS for a remote cloud, or HTTP on localhost")
    return value.rstrip("/")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class CloudClient:
    def __init__(self, base, token=None):
        self.base = validate_url(base)
        self.token = token
        self.opener = urllib.request.build_opener(NoRedirect)

    def call(self, method, path, body=None):
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        payload = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            payload = json.dumps(body, allow_nan=False).encode()
        request = urllib.request.Request(
            self.base + path, data=payload, headers=headers, method=method
        )
        try:
            with self.opener.open(request, timeout=5) as response:
                raw = response.read(8 * 1024 * 1024 + 1)
                if len(raw) > 8 * 1024 * 1024:
                    raise CloudError("Cloud response exceeded the size limit", 502)
                try:
                    return json.loads(raw) if raw else None
                except ValueError:
                    raise CloudError(
                        "Cloud returned an invalid response", 502
                    ) from None
        except urllib.error.HTTPError as error:
            raw = error.read(8192)
            try:
                detail = json.loads(raw).get("detail")
            except (ValueError, AttributeError):
                detail = None
            message = (
                detail
                if isinstance(detail, str)
                else f"Cloud request failed ({error.code})"
            )
            retry_after = error.headers.get("Retry-After", "")
            raise CloudError(
                message,
                error.code,
                min(int(retry_after), 3600) if retry_after.isdigit() else None,
            ) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise CloudError("Cloud unavailable; local work is preserved") from None
