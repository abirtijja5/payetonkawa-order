"""Événements RabbitMQ écoutés par le service Commandes."""
import logging

from .models import Order
from .services import cancel_order

logger = logging.getLogger(__name__)


def on_client_deleted(data):
    """Un client est supprimé : ses commandes non expédiées sont annulées."""
    pending = Order.objects.filter(
        customer_id=data.get("id"), status__in=[Order.Status.EN_ATTENTE, Order.Status.VALIDEE],
    )
    for order in pending:
        cancel_order(order)
    logger.info("Client %s supprimé : %s commande(s) annulée(s)", data.get("id"), len(pending))


HANDLERS = {
    "client.deleted": on_client_deleted,
}
