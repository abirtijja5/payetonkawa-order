"""Règles métier des commandes partagées par l'API et les événements."""
from .messaging import publish
from .models import Order


def order_event(order):
    return {
        "id": order.id,
        "customer_id": order.customer_id,
        "status": order.status,
        "total_amount": str(order.total_amount),
        "items": [{"product_id": i.product_id, "quantity": i.quantity} for i in order.items.all()],
    }


def cancel_order(order):
    """Annule une commande et demande au service Produits de remettre le stock."""
    if order.status == Order.Status.ANNULEE:
        return False
    order.status = Order.Status.ANNULEE
    order.save(update_fields=["status", "updated_at"])
    publish("order.cancelled", order_event(order))
    return True
