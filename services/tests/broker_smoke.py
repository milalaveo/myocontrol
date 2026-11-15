"""Verify invalid messages reach the recognition dead-letter queue."""

import os
import time

import pika

credentials = pika.PlainCredentials(os.environ["RABBITMQ_USER"], os.environ["RABBITMQ_PASSWORD"])
connection = pika.BlockingConnection(pika.ConnectionParameters(host=os.environ["RABBITMQ_HOST"], credentials=credentials, socket_timeout=5))
channel = connection.channel()
channel.confirm_delivery()
queue = "recognition.models.v1"
dead_queue = "recognition.models.dead.v1"
before = channel.queue_declare(queue=dead_queue, passive=True).method.message_count
channel.basic_publish(exchange="", routing_key=queue, body=b"invalid-event-for-test", mandatory=True,
                      properties=pika.BasicProperties(delivery_mode=2, content_type="application/json"))
deadline = time.monotonic() + 15
while time.monotonic() < deadline:
    after = channel.queue_declare(queue=dead_queue, passive=True).method.message_count
    if after > before:
        print("Invalid message reached the dead-letter queue.")
        break
    time.sleep(0.2)
else:
    raise RuntimeError("Invalid event did not reach the dead-letter queue")
connection.close()
