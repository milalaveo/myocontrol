# MyoControl API documentation

This is the entry point for the API-documentation assessment. It covers the implemented operator/cloud APIs and the existing private development Data, ML and Recognition APIs. It does not claim that remote training, Electron synchronization or live acquisition APIs already exist.

## Start here

1. Follow [Getting Started](GETTING_STARTED.md) to generate private settings, start Docker Compose and create an operator.
2. Open **[Swagger UI](http://127.0.0.1:8000/docs)** or **[ReDoc](http://127.0.0.1:8000/redoc)**. No deployment on an external server is required to review the saved files below.
3. Follow [operator and client integration](tutorials/CLOUD_ACCESS.md), then optionally [synthetic research integration](tutorials/SYNTHETIC_RESEARCH.md).
4. Use [error handling and access boundaries](ERRORS.md) when implementing a client.

## Versioned OpenAPI specifications

All files use **OpenAPI 3.1.0 JSON** and contain typed models, operation descriptions, sample requests/responses, status/error responses, security schemes and response headers.

| Contract | Stored file | Coverage |
| --- | --- | --- |
| Public gateway | [gateway/openapi.json](../gateway/gateway/openapi.json) | 49 operations, including concrete bearer-authenticated cloud routes, Basic-authenticated development proxy routes, health and metrics. |
| Data & Protocol | [data/openapi.json](../services/data_protocol/data_protocol/openapi.json) | 24 private service operations. |
| ML Experiments | [ml/openapi.json](../services/ml_experiments/ml_experiments/openapi.json) | 10 private service operations, including internal owner-scoped registry access. |
| Recognition | [recognition/openapi.json](../services/recognition/recognition/openapi.json) | 6 private service operations for development recording replay and operations. |

The gateway document is the primary client specification. It expands proxy routes into their real operations and omits the internal ML registry routes that the Basic proxy blocks. Domain specifications describe the service-network interfaces and must not be interpreted as permission to expose their ports publicly. Cloud and private service operations overlap; the operation counts are not additive.

`/docs`, `/redoc` and `/openapi.json` are documentation infrastructure. `/metrics/` is operational text, not a research endpoint. Examples use synthetic UUIDs, digests and visibly non-live tokens/passwords. An empty operator registry is a valid response, not a failed installation.

## Validation and regeneration

With Python 3.12, install the application dependencies plus the documentation validators:

```powershell
python -m pip install -r gateway/requirements.txt -r services/recognition/requirements.txt -r api/requirements.txt
python api/build_specs.py --check
python -m unittest discover -s api/tests -p "test_*.py" -v
```

No database, Docker or secrets are required for these checks. `build_specs.py` generates models from the FastAPI routes, adds explicit examples/semantics from `api/examples.py` and `api/catalog.py`, and composes the public gateway contract. It validates OpenAPI structure and validates every body example against its JSON Schema, including UUID/date-time formats. `--check` fails if a saved file differs from the generated contract or a new operation lacks documentation. Live Swagger/ReDoc serve these same versioned files.

After an intentional contract change, run `python api/build_specs.py` to regenerate, review the diff and commit the JSON files with the code. The `api-documentation` GitHub Actions job repeats validation and contract tests independently of PostgreSQL.

## Assessment evidence

| Requirement | Evidence |
| --- | --- |
| Complete, validated specification saved as YAML/JSON | The four versioned OpenAPI JSON files above, checked by `api/build_specs.py --check`. |
| Requests, responses, status codes, errors and models for every operation | Swagger/ReDoc generated from those files; explicit operation metadata and examples, checked by schema validation. |
| Getting Started and a step-by-step integration tutorial | [Setup guide](GETTING_STARTED.md), [cloud tutorial](tutorials/CLOUD_ACCESS.md), [research tutorial](tutorials/SYNTHETIC_RESEARCH.md), executable `api/tutorial.py`. |
| Developer-accessible publication | Structured Markdown in this directory, stored JSON, gateway Swagger UI and ReDoc. |

Backend behaviour is also checked by the existing service and [cloud gateway tests](../gateway/tests/test_cloud_access.py). Documentation validation does not substitute for database integration, scientific model validation or production deployment.
