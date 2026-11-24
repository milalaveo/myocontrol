"""Create private development settings without committing or printing credentials."""

from pathlib import Path
import secrets


def main():
    destination = Path(__file__).resolve().parents[1] / ".env"
    values = {
        key: secrets.token_urlsafe(36)
        for key in (
            "POSTGRES_PASSWORD",
            "DATA_DB_PASSWORD",
            "ML_DB_PASSWORD",
            "RECOGNITION_DB_PASSWORD",
            "IDENTITY_DB_PASSWORD",
            "CLOUD_INTERNAL_KEY",
            "RABBITMQ_PASSWORD",
            "REDIS_PASSWORD",
            "GATEWAY_PASSWORD",
            "GRAFANA_PASSWORD",
        )
    }
    values["GATEWAY_USERNAME"] = "development"
    values["RABBITMQ_USER"] = "myocontrol"
    try:
        with destination.open("x", encoding="utf-8") as output:
            output.write("".join(f"{key}={value}\n" for key, value in values.items()))
    except FileExistsError:
        raise SystemExit(
            ".env already exists; no credentials were changed. Use the existing configuration."
        ) from None
    print("Created ignored .env with private random credentials. Do not commit or share this file.")


if __name__ == "__main__":
    main()
