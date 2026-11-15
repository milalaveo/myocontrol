"""Consume model announcements with idempotency and a dead-letter queue."""

import json
import logging
import os
import time
import uuid

import pika
from opentelemetry import context, trace
from opentelemetry.propagate import extract
from sqlalchemy import text

from .db import session_factory

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("model_events")
EXCHANGE = "myocontrol.models.v1"
QUEUE = "recognition.models.v1"
DEAD_EXCHANGE = "myocontrol.dead.v1"
DEAD_QUEUE = "recognition.models.dead.v1"


def handle(channel, method, properties, body):
    try:
        event = json.loads(body)
        if event["event_type"] != "ModelPublished" or event["schema_version"] != 1:
            raise ValueError("Unsupported model event")
        event_id, model_id, manifest_id = (uuid.UUID(event[key]) for key in ("event_id", "model_run_id", "manifest_id"))
        correlation = event["correlation_id"]
        if not isinstance(correlation, str) or not 1 <= len(correlation) <= 64:
            raise ValueError("Invalid correlation ID")
        carrier = event.get("trace_context", {})
        if not isinstance(carrier, dict) or any(key not in {"traceparent", "tracestate"} or not isinstance(value, str) or len(value) > 512 for key, value in carrier.items()):
            raise ValueError("Invalid trace context")
    except (ValueError, KeyError, TypeError):
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        return
    token = context.attach(extract(carrier))
    try:
        with trace.get_tracer(__name__).start_as_current_span("model_event.consume"):
            with session_factory()() as session:
                with session.begin():
                    session.execute(text("""INSERT INTO recognition.model_events(event_id, model_run_id, manifest_id, correlation_id)
                        VALUES (:event_id, :model_id, :manifest_id, :correlation) ON CONFLICT (event_id) DO NOTHING"""),
                        {"event_id": event_id, "model_id": model_id, "manifest_id": manifest_id, "correlation": correlation})
            channel.basic_ack(delivery_tag=method.delivery_tag)
            logger.info(json.dumps({"event": "model_event_received", "event_id": str(event_id), "correlation_id": correlation}))
    except Exception:
        logger.exception("model_event_persistence_failed")
        headers = dict(properties.headers or {}) if properties else {}
        attempts = headers.get("x-attempt", 0)
        if not isinstance(attempts, int) or attempts >= 2:
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return
        time.sleep(2 ** attempts)
        headers["x-attempt"] = attempts + 1
        try:
            channel.basic_publish(exchange="", routing_key=QUEUE, body=body, mandatory=True,
                properties=pika.BasicProperties(content_type="application/json", delivery_mode=2,
                    message_id=str(event_id), correlation_id=correlation, headers=headers))
            channel.basic_ack(delivery_tag=method.delivery_tag)
        except Exception:
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
    finally:
        context.detach(token)


def main():
    while True:
        connection = None
        try:
            connection = pika.BlockingConnection(pika.ConnectionParameters(
                host=os.environ.get("RABBITMQ_HOST", "rabbitmq"), heartbeat=30,
                credentials=pika.PlainCredentials(os.environ["RABBITMQ_USER"], os.environ["RABBITMQ_PASSWORD"]),
                socket_timeout=5, blocked_connection_timeout=5))
            channel = connection.channel()
            channel.exchange_declare(exchange=EXCHANGE, exchange_type="fanout", durable=True)
            channel.exchange_declare(exchange=DEAD_EXCHANGE, exchange_type="direct", durable=True)
            channel.queue_declare(queue=DEAD_QUEUE, durable=True)
            channel.queue_bind(queue=DEAD_QUEUE, exchange=DEAD_EXCHANGE, routing_key=QUEUE)
            channel.queue_declare(queue=QUEUE, durable=True, arguments={"x-dead-letter-exchange": DEAD_EXCHANGE, "x-dead-letter-routing-key": QUEUE})
            channel.queue_bind(queue=QUEUE, exchange=EXCHANGE)
            channel.basic_qos(prefetch_count=1)
            channel.confirm_delivery()
            channel.basic_consume(queue=QUEUE, on_message_callback=handle, auto_ack=False)
            channel.start_consuming()
        except Exception:
            logger.exception("model_event_consumer_unavailable")
            time.sleep(3)
        finally:
            if connection is not None and connection.is_open:
                connection.close()


if __name__ == "__main__":
    main()
