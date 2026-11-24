"""Generate, validate and compare the published contracts without a running database."""

import argparse
from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys

from fastapi.openapi.utils import get_openapi
from jsonschema import Draft202012Validator, FormatChecker
from openapi_spec_validator import validate

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))
from catalog import CATALOG
from examples import HASH, MODELS, uid

SERVICES = {
    "data": ("services/data_protocol", "data_protocol", 8001),
    "ml": ("services/ml_experiments", "ml_experiments", 8002),
    "recognition": ("services/recognition", "recognition", 8003),
    "gateway": ("gateway", "gateway", 8000),
}
METHODS = {"get", "post", "put", "patch", "delete"}
ERROR_SCHEMA = {
    "type": "object",
    "properties": {"detail": {"type": "string"}, "correlation_id": {"type": "string"}},
    "required": ["detail"],
}
PARAMETER_EXAMPLES = {
    "participant_id": uid(1),
    "recording_id": uid(2),
    "manifest_id": uid(4),
    "subset_id": uid(7),
    "item_id": uid(9),
    "client_id": uid(14),
    "split_id": uid(16),
    "job_id": uid(17),
    "run_id": uid(18),
    "model_run_id": uid(18),
    "session_id": uid(19),
    "x-operator-id": uid(11),
}
DESCRIPTION = "Implemented MyoControl API. Cloud registries are read-only. General training belongs to a local workstation; live acquisition/calibration belongs to Electron. Legacy Data/ML/replay operations are private single-host development APIs. Examples are synthetic; passwords/tokens/UUIDs/digests shown here are not live credentials or measured results."


def example(schema, spec):
    if "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[1]
        if name not in MODELS:
            raise ValueError(f"Missing explicit model example: {name}")
        return deepcopy(MODELS[name])
    if schema.get("type") == "array":
        return [example(schema["items"], spec)]
    if "anyOf" in schema:
        return example(schema["anyOf"][0], spec)
    raise ValueError(f"Missing typed response/request: {schema}")


def error_response(status, message):
    result = {
        "description": message,
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/ApiError"},
                "example": {"detail": message},
            }
        },
    }
    if status == 429:
        result["headers"] = {
            "Retry-After": {
                "description": "Seconds until the current rate-limit window resets.",
                "schema": {"type": "string"},
                "example": "30",
            }
        }
    if status == 401:
        result["headers"] = {
            "WWW-Authenticate": {
                "description": "Bearer for operator routes; Basic for development proxy routes when a challenge is returned.",
                "schema": {"type": "string"},
                "example": "Bearer",
            }
        }
    return result


def decorate(name, spec):
    spec["info"]["description"] = DESCRIPTION
    spec["info"]["contact"] = {
        "name": "MyoControl repository",
        "url": "https://github.com/milalaveo/myocontrol",
    }
    spec["servers"] = [
        {
            "url": f"http://127.0.0.1:{SERVICES[name][2]}",
            "description": "Local development; domain-service ports are internal in Compose. Use the gateway contract for host access.",
        }
    ]
    spec.setdefault("components", {}).setdefault("schemas", {})[
        "ApiError"
    ] = ERROR_SCHEMA
    for path, item in spec["paths"].items():
        for method, operation in item.items():
            if method not in METHODS:
                continue
            key = method.upper() + " " + path
            if path.startswith("/health/"):
                summary = (
                    "Check process liveness"
                    if path.endswith("live")
                    else "Check database readiness"
                )
                description = (
                    "Liveness does not require database access."
                    if path.endswith("live")
                    else "Executes a read-only database query. A successful liveness response alone does not prove readiness."
                )
                errors = (
                    {} if path.endswith("live") else {503: "Database operation failed"}
                )
            else:
                if key not in CATALOG[name]:
                    raise ValueError(f"Undocumented operation: {name} {key}")
                summary, description, errors = CATALOG[name][key]
            operation["summary"], operation["description"] = summary, description
            operation["tags"] = (
                ["health"]
                if path.startswith("/health/")
                else operation.get("tags", [name])
            )
            operation.setdefault("responses", {})["500"] = error_response(
                500, "Internal server error"
            )
            if not path.startswith("/health/"):
                operation["responses"].setdefault(
                    "503",
                    error_response(
                        503,
                        (
                            "Operator access unavailable"
                            if name == "gateway"
                            else "Database operation failed"
                        ),
                    ),
                )
            for status, message in errors.items():
                if status != 422:
                    operation["responses"][str(status)] = error_response(
                        status, message
                    )
            if name == "gateway" and not path.startswith("/health/"):
                operation["responses"]["429"] = error_response(
                    429, "Rate limit exceeded"
                )
            for parameter in operation.get("parameters", []):
                field = parameter["name"]
                if field in {"collection"}:
                    parameter["schema"]["enum"] = ["runs", "models", "results"]
                    parameter["example"] = "runs"
                elif (
                    field in PARAMETER_EXAMPLES
                    or parameter["schema"].get("format") == "uuid"
                    or field.endswith("_id")
                ):
                    parameter["example"] = PARAMETER_EXAMPLES.get(field, uid(1))
                elif field.lower() == "idempotency-key":
                    parameter["example"] = "tutorial-lda-submission-1"
                    parameter["description"] = (
                        "Optional 1–100 character [A-Za-z0-9._:-] key. Reusing a key with changed inputs returns 409."
                    )
                elif field in {"limit", "offset"}:
                    parameter["example"] = 25 if field == "limit" else 0
            for media in operation.get("requestBody", {}).get("content", {}).values():
                media["example"] = example(media["schema"], spec)
            for status, response in operation["responses"].items():
                response.setdefault("headers", {})["X-Correlation-ID"] = {
                    "description": "Request correlation identifier, generated when no valid incoming identifier is supplied.",
                    "schema": {"type": "string"},
                    "example": "tutorial-request-1",
                }
                if status == "422":
                    response["description"] = (
                        "Input validation failed. Framework validation uses a detail array; explicit application validation can return a detail string."
                    )
                    validation_example = {
                        "detail": [
                            {
                                "loc": ["query", "limit"],
                                "msg": "Input should be less than or equal to 100",
                                "type": "less_than_equal",
                            }
                        ]
                    }
                    uuid_parameter = next(
                        (
                            p
                            for p in operation.get("parameters", [])
                            if p["schema"].get("format") == "uuid"
                        ),
                        None,
                    )
                    if uuid_parameter:
                        validation_example = {
                            "detail": [
                                {
                                    "loc": [
                                        uuid_parameter["in"],
                                        uuid_parameter["name"],
                                    ],
                                    "msg": "Input should be a valid UUID",
                                    "type": "uuid_parsing",
                                }
                            ]
                        }
                    elif "requestBody" in operation:
                        schema = operation["requestBody"]["content"][
                            "application/json"
                        ]["schema"]
                        model = spec["components"]["schemas"][
                            schema["$ref"].rsplit("/", 1)[1]
                        ]
                        validation_example = {
                            "detail": [
                                {
                                    "loc": ["body", model["required"][0]],
                                    "msg": "Field required",
                                    "type": "missing",
                                }
                            ]
                        }
                    response["content"] = {
                        "application/json": {
                            "schema": {
                                "anyOf": [
                                    {
                                        "$ref": "#/components/schemas/HTTPValidationError"
                                    },
                                    {"$ref": "#/components/schemas/ApiError"},
                                ]
                            },
                            "examples": {
                                "validation": {"value": validation_example},
                                **(
                                    {"application": {"value": {"detail": errors[422]}}}
                                    if 422 in errors
                                    else {}
                                ),
                            },
                        }
                    }
                elif status.startswith("2"):
                    if name == "gateway" and path.startswith("/cloud/"):
                        continue
                    for media in response.get("content", {}).values():
                        media["example"] = example(media["schema"], spec)
                        if path.endswith("/freeze"):
                            media["example"]["state"] = "frozen"
                            if "checksum" in media["example"]:
                                media["example"]["checksum"] = HASH
                        if path.endswith("/health/ready"):
                            media["example"]["status"] = "ready"
                    if status == "204":
                        response["description"] = (
                            "Revoked successfully; no response body."
                        )
            if key == "POST /v1/source-lda-experiments":
                operation["responses"]["202"]["headers"]["Location"] = {
                    "schema": {"type": "string"},
                    "example": f"/v1/source-lda-experiments/{uid(18)}",
                    "description": "Status resource for the accepted job.",
                }
            if key == "GET /v1/source-lda-experiments/{run_id}/model":
                operation["responses"]["200"]["headers"]["X-Artifact-SHA256"] = {
                    "schema": {"type": "string"},
                    "example": HASH,
                    "description": "SHA-256 of exact response bytes; verify before parsing or reserialization.",
                }
    spec["paths"]["/metrics/"] = {
        "get": {
            "operationId": name + "_metrics",
            "summary": "Read Prometheus metrics",
            "description": "Operational text endpoint. No account or research record payloads. Domain-service metrics stay on the private service network.",
            "tags": ["operations"],
            "responses": {
                "200": {
                    "description": "Prometheus exposition format; metric values vary.",
                    "content": {
                        "text/plain": {
                            "schema": {"type": "string"},
                            "example": "# HELP process_cpu_seconds_total Total user and system CPU time spent in seconds.\n# TYPE process_cpu_seconds_total counter\nprocess_cpu_seconds_total 0.1\n",
                        }
                    },
                }
            },
        }
    }
    return spec


def namespaced(spec, prefix):
    spec = deepcopy(spec)

    def rewrite(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "$ref" and item.startswith("#/components/schemas/"):
                    value[key] = (
                        "#/components/schemas/" + prefix + item.rsplit("/", 1)[1]
                    )
                else:
                    rewrite(item)
        elif isinstance(value, list):
            for item in value:
                rewrite(item)

    rewrite(spec)
    spec["components"]["schemas"] = {
        prefix + key: value for key, value in spec["components"]["schemas"].items()
    }
    return spec


def public_contract(gateway, services):
    result = deepcopy(gateway)
    result["info"]["title"] = "MyoControl Gateway API"
    result["servers"] = [
        {
            "url": "/",
            "description": "Same-origin gateway; normally http://127.0.0.1:8000",
        }
    ]
    ml = namespaced(services["ml"], "Ml_")
    result["components"]["schemas"].update(ml["components"]["schemas"])
    data = namespaced(services["data"], "Data_")
    result["components"]["schemas"].update(data["components"]["schemas"])
    for suffix, method, status, model in (
        ("", "post", "201", "PublicationReceipt"),
        ("", "get", "200", "OwnedRecordingPage"),
        ("/{recording_id}/signal", "get", "200", "OwnedSignal"),
    ):
        operation = result["paths"]["/cloud/v1/recordings" + suffix][method]
        operation["responses"][status]["content"] = {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/Data_" + model},
                "example": deepcopy(MODELS[model]),
            }
        }
        if method == "post":
            operation["requestBody"] = {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {
                            "$ref": "#/components/schemas/Data_ClientRecordingCreate"
                        },
                        "example": deepcopy(MODELS["ClientRecordingCreate"]),
                    }
                },
            }
            operation["responses"]["422"] = deepcopy(
                data["paths"]["/v1/client-recordings"]["post"]["responses"]["422"]
            )
    for suffix, model_names in (
        ("", ["RunPage", "ModelPage", "ResultPage"]),
        ("/{item_id}", ["RegistryRun", "PublishedModel", "EvaluationDetail"]),
    ):
        template = result["paths"].pop("/cloud/v1/{collection}" + suffix)
        for collection, model in zip(["runs", "models", "results"], model_names):
            concrete = deepcopy(template)
            operation = concrete["get"]
            operation["parameters"] = [
                p for p in operation.get("parameters", []) if p["name"] != "collection"
            ]
            for parameter in operation["parameters"]:
                if parameter["name"] == "item_id":
                    parameter["example"] = MODELS[model]["id"]
            operation["operationId"] = (
                "cloud_" + collection + ("_detail" if suffix else "_list")
            )
            operation["summary"] = (
                "Read your " if suffix else "List your "
            ) + collection
            operation["responses"]["200"]["content"] = {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/Ml_" + model},
                    "example": deepcopy(MODELS[model]),
                }
            }
            result["paths"]["/cloud/v1/" + collection + suffix] = concrete
    for name, prefix in (
        ("data", "data"),
        ("ml", "experiments"),
        ("recognition", "recognition"),
    ):
        spec = namespaced(services[name], name.title() + "_")
        result["components"]["schemas"].update(spec["components"]["schemas"])
        for path, item in spec["paths"].items():
            if (
                path.startswith(("/v1/registry/", "/v1/client-recordings"))
                or path == "/metrics/"
            ):
                continue
            item = deepcopy(item)
            for method, operation in item.items():
                if method not in METHODS:
                    continue
                operation["operationId"] = prefix + "_" + operation["operationId"]
                operation["security"] = [{"HTTPBasic": []}]
                operation["description"] = (
                    "Development-only proxy route. Requires separate shared Basic credentials; it has no per-operator ownership checks. "
                    + operation["description"]
                )
                for code, message in {
                    401: "Invalid credentials",
                    413: "Request body is too large",
                    429: "Rate limit exceeded",
                    502: "Service unavailable",
                    503: "Service address is not configured",
                    504: "Service request timed out",
                }.items():
                    operation["responses"].setdefault(
                        str(code), error_response(code, message)
                    )
                operation["responses"]["401"]["headers"]["WWW-Authenticate"][
                    "example"
                ] = "Basic"
                for response in operation["responses"].values():
                    location = response.get("headers", {}).get("Location")
                    if location:
                        location["example"] = "/" + prefix + location["example"]
            result["paths"]["/" + prefix + path] = item
    result["components"].setdefault("securitySchemes", {})["HTTPBasic"] = {
        "type": "http",
        "scheme": "basic",
        "description": "Shared development gateway credentials. This is separate from operator bearer access.",
    }
    return result


def validate_contract(spec):
    validate(spec)
    count = 0
    for path, item in spec["paths"].items():
        for method, operation in item.items():
            if method not in METHODS:
                continue
            count += 1
            assert operation.get("summary") and operation.get("description"), (
                method,
                path,
            )
            media_sets = [operation.get("requestBody", {}).get("content", {})]
            media_sets += [
                r.get("content", {}) for r in operation["responses"].values()
            ]
            for media_set in media_sets:
                for media in media_set.values():
                    assert media.get("schema"), (method, path, "empty schema")
                    examples = (
                        [media["example"]]
                        if "example" in media
                        else [e["value"] for e in media.get("examples", {}).values()]
                    )
                    assert examples, (method, path, "missing example")
                    validator = Draft202012Validator(
                        {"components": spec["components"], **media["schema"]},
                        format_checker=FormatChecker(),
                    )
                    for value in examples:
                        validator.validate(value)
    return count


def build():
    specs = {}
    paths = {}
    for name, (directory, package, _port) in SERVICES.items():
        sys.path.insert(0, str(ROOT / directory))
        app = importlib.import_module(package + ".main").app
        spec = get_openapi(
            title=app.title,
            version=app.version,
            openapi_version="3.1.0",
            routes=app.routes,
        )
        specs[name] = decorate(name, spec)
        paths[name] = ROOT / directory / package / "openapi.json"
    specs["gateway"] = public_contract(specs["gateway"], specs)
    return {paths[name]: spec for name, spec in specs.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if stored specifications differ from source contracts",
    )
    args = parser.parse_args()
    changed = []
    for path, spec in build().items():
        count = validate_contract(spec)
        content = json.dumps(spec, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                changed.append(str(path.relative_to(ROOT)))
        else:
            path.write_text(content, encoding="utf-8")
        print(
            f"Validated {path.relative_to(ROOT)}: {count} operations, schemas and examples",
            flush=True,
        )
    if changed:
        raise SystemExit("Regenerate changed contracts: " + ", ".join(changed))


if __name__ == "__main__":
    main()
