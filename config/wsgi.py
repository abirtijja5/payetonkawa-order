"""Point d'entrée WSGI (utilisé par gunicorn en production)."""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_wsgi_application()

# Démarre l'écoute des événements RabbitMQ (uniquement quand le serveur tourne).
from orders.messaging import start_consumer  # noqa: E402
from orders.events import HANDLERS  # noqa: E402

start_consumer(queue="order-service", handlers=HANDLERS)
