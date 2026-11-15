"""Deliver committed model events with publisher confirms and retry on restart."""

import json
import logging
import os
import time

import pika
from opentelemetry import context, trace
from opentelemetry.propagate import extract, inject
from sqlalchemy import text

from .db import session_factory

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("model_outbox")
EXCHANGE = "myocontrol.models.v1"


def publish_one(channel):
    with session_factory()() as session:
        with session.begin():
            event = session.execute(text("""SELECT id, payload FROM ml_experiments.outbox_events
                WHERE published_at IS NULL ORDER BY created_at, id FOR UPDATE SKIP LOCKED LIMIT 1""")).mappings().one_or_none()
            if event is None:
                return False
            payload = event["payload"]
            token = context.attach(extract(payload.get("trace_context", {})))
            try:
                with trace.get_tracer(__name__).start_as_current_span("model_event.publish"):
                    outgoing = dict(payload)
                    carrier = {}
                    inject(carrier)
                    outgoing["trace_context"] = {key: value for key, value in carrier.items() if key in {"traceparent", "tracestate"}}
                    channel.basic_publish(exchange=EXCHANGE, routing_key="", body=json.dumps(outgoing, separators=(",", ":")).encode(),
                        properties=pika.BasicProperties(content_type="application/json", delivery_mode=2, message_id=str(event["id"]),
                                                        correlation_id=payload["correlation_id"]), mandatory=True)
                    session.execute(text("UPDATE ml_experiments.outbox_events SET published_at = clock_timestamp() WHERE id = :id"), {"id": event["id"]})
                    logger.info(json.dumps({"event": "model_event_published", "event_id": str(event["id"]), "correlation_id": payload["correlation_id"]}))
            finally:
                context.detach(token)
            return True


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
            channel.confirm_delivery()
            while connection.is_open:
                if not publish_one(channel):
                    connection.process_data_events(time_limit=2)
        except Exception:
            logger.exception("model_event_publisher_unavailable")
            time.sleep(3)
        finally:
            if connection is not None and connection.is_open:
                connection.close()


if __name__ == "__main__":
    main()
