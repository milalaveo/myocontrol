import argparse
from contextlib import redirect_stdout
import json
import sys
import threading

from .engine import Engine


def main():
    parser = argparse.ArgumentParser(description="MyoControl private stdio runtime")
    parser.add_argument("--data-dir", required=True)
    args = parser.parse_args()
    output = sys.stdout
    lock = threading.Lock()

    def write(value):
        line = json.dumps(value, allow_nan=False, separators=(",", ":"))
        with lock:
            output.write(line + "\n")
            output.flush()

    def emit(event, data):
        write({"event": event, "data": data})

    with redirect_stdout(sys.stderr):
        engine = Engine(args.data_dir, emit)
        commands = {
            "status": engine.status,
            "start_capture": engine.start_capture,
            "start_replay": engine.start_replay,
            "stop": engine.stop,
            "pause": engine.pause,
            "resume": engine.resume,
            "recordings": engine.recordings,
            "import_recording": engine.import_recording,
            "export_recording": engine.store.export,
            "load_model": engine.load_model,
            "clear_model": engine.clear_model,
            "cloud_login": engine.cloud_login,
            "cloud_logout": engine.cloud_logout,
            "cloud_restore": lambda credentials: engine.sync.configure(credentials),
            "sync_status": engine.sync.status,
            "queue_upload": engine.queue_upload,
            "retry_sync": lambda: engine.sync.configure(engine.sync.credentials),
        }
        try:
            emit("ready", {"protocol": 1})
            for line in sys.stdin:
                request = None
                try:
                    if len(line) > 65536:
                        raise ValueError("Runtime command is too large")
                    request = json.loads(line)
                    if (
                        not isinstance(request, dict)
                        or not isinstance(request.get("id"), str)
                        or len(request["id"]) > 64
                    ):
                        raise ValueError("Invalid runtime request")
                    method = request.get("method")
                    if method == "shutdown":
                        engine.close()
                        write({"id": request["id"], "result": {"closed": True}})
                        break
                    if method not in commands or not isinstance(
                        request.get("params", {}), dict
                    ):
                        raise ValueError("Unknown runtime command")
                    result = commands[method](**request.get("params", {}))
                    write({"id": request["id"], "result": result})
                except (ValueError, TypeError, KeyError, OSError) as error:
                    write(
                        {
                            "id": (
                                request.get("id") if isinstance(request, dict) else None
                            ),
                            "error": {"message": str(error)[:300]},
                        }
                    )
                except Exception as error:
                    from .sync.client import CloudError

                    message = (
                        str(error)
                        if isinstance(error, CloudError)
                        else "Local operation failed; the recording remains on this device"
                    )
                    write(
                        {
                            "id": (
                                request.get("id") if isinstance(request, dict) else None
                            ),
                            "error": {"message": message[:300]},
                        }
                    )
        finally:
            engine.close()


if __name__ == "__main__":
    main()
