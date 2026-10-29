"""
Communication asynchrone avec RabbitMQ.

- publish()        : envoie un événement métier (ex. "order.created")
- start_consumer() : écoute en tâche de fond les événements qui intéressent ce service

Un "exchange" de type topic distribue chaque message aux files (queues)
abonnées à sa clé de routage. Si RabbitMQ est indisponible, l'API continue de
répondre : l'erreur est journalisée (tolérance aux pannes).
"""
import json
import logging
import threading
import time
import uuid
from datetime import datetime, timezone

from django.conf import settings

logger = logging.getLogger(__name__)


def _connection():
    import pika

    cfg = settings.RABBITMQ
    credentials = pika.PlainCredentials(cfg["USER"], cfg["PASSWORD"])
    params = pika.ConnectionParameters(
        host=cfg["HOST"], port=cfg["PORT"], credentials=credentials, heartbeat=30,
    )
    return pika.BlockingConnection(params)


def publish(routing_key, payload):
    """Publie un événement. Retourne True si le message est parti."""
    cfg = settings.RABBITMQ
    event = {
        "event_id": str(uuid.uuid4()),
        "type": routing_key,
        "source": settings.SERVICE_NAME,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "data": payload,
    }
    if not cfg["ENABLED"]:
        logger.info("RabbitMQ désactivé, événement non envoyé : %s", routing_key)
        return False
    try:
        import pika

        connection = _connection()
        channel = connection.channel()
        channel.exchange_declare(exchange=cfg["EXCHANGE"], exchange_type="topic", durable=True)
        channel.basic_publish(
            exchange=cfg["EXCHANGE"],
            routing_key=routing_key,
            body=json.dumps(event, default=str),
            properties=pika.BasicProperties(content_type="application/json", delivery_mode=2),
        )
        connection.close()
        logger.info("Événement publié : %s", routing_key)
        return True
    except Exception:  # RabbitMQ en panne : on ne bloque pas l'API
        logger.exception("Échec de publication de l'événement %s", routing_key)
        return False


def _consume_forever(queue, handlers):
    cfg = settings.RABBITMQ
    while True:
        try:
            connection = _connection()
            channel = connection.channel()
            channel.exchange_declare(exchange=cfg["EXCHANGE"], exchange_type="topic", durable=True)
            channel.queue_declare(queue=queue, durable=True)
            for routing_key in handlers:
                channel.queue_bind(exchange=cfg["EXCHANGE"], queue=queue, routing_key=routing_key)

            def on_message(ch, method, properties, body):
                try:
                    event = json.loads(body)
                    handlers[method.routing_key](event.get("data", {}))
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                except Exception:
                    logger.exception("Erreur de traitement du message %s", method.routing_key)
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

            channel.basic_qos(prefetch_count=10)
            channel.basic_consume(queue=queue, on_message_callback=on_message)
            logger.info("En écoute sur la file %s (%s)", queue, ", ".join(handlers))
            channel.start_consuming()
        except Exception:
            logger.warning("Connexion RabbitMQ perdue, nouvelle tentative dans 5 s")
            time.sleep(5)


def start_consumer(queue, handlers):
    """Lance l'écoute dans un thread séparé (si RabbitMQ est activé)."""
    if not settings.RABBITMQ["ENABLED"] or not handlers:
        return None
    thread = threading.Thread(target=_consume_forever, args=(queue, handlers), daemon=True)
    thread.start()
    return thread
