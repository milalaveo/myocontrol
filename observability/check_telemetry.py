"""Check local Prometheus, Jaeger and Loki after running the synthetic flow."""

import datetime
import json
import time
import urllib.parse
import urllib.request


def get_json(base, query=None):
    if query:
        base += "?" + urllib.parse.urlencode(query)
    with urllib.request.urlopen(base, timeout=5) as response:
        return json.load(response)


def wait_for(check, description):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            if check():
                print(f"Verified {description}", flush=True)
                return
        except (OSError, ValueError, KeyError):
            pass
        time.sleep(1)
    raise RuntimeError(f"Could not verify {description}")


def metrics_ready():
    result = get_json("http://prometheus:9090/api/v1/query", {"query": 'up{job="myocontrol-services"}'})
    values = result["data"]["result"]
    return len(values) == 4 and all(item["value"][1] == "1" for item in values)


def traces_ready():
    names = get_json("http://jaeger:16686/api/v3/services")["services"]
    if not {"gateway", "data-protocol", "ml-experiments", "ml-worker", "ml-outbox", "recognition", "recognition-events"}.issubset(names):
        return False
    now = datetime.datetime.now(datetime.timezone.utc)
    query = {"query.service_name": "ml-worker", "query.start_time_min": (now - datetime.timedelta(hours=1)).isoformat(),
             "query.start_time_max": (now + datetime.timedelta(minutes=1)).isoformat(), "query.search_depth": "100"}
    url = "http://jaeger:16686/api/v3/traces?" + urllib.parse.urlencode(query)
    with urllib.request.urlopen(url, timeout=5) as response:
        content = response.read().decode("utf-8")
    return any(all(name in line for name in ("gateway", "ml-experiments", "ml-worker", "data-protocol", "ml-outbox", "recognition-events"))
               for line in content.splitlines())


def logs_ready():
    result = get_json("http://loki:3100/loki/api/v1/query_range", {"query": '{service_name="gateway"}', "limit": "1"})
    return bool(result["data"]["result"])


wait_for(metrics_ready, "four service metrics endpoints")
wait_for(traces_ready, "distributed traces")
wait_for(logs_ready, "centralized gateway logs")
