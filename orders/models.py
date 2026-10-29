"""Modèle de données du service Commandes."""
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models


class Order(models.Model):
    class Status(models.TextChoices):
        EN_ATTENTE = "en_attente", "En attente"
        VALIDEE = "validee", "Validée"
        EXPEDIEE = "expediee", "Expédiée"
        LIVREE = "livree", "Livrée"
        ANNULEE = "annulee", "Annulée"

    # Identifiant du client (UUID venant du service Clients : pas de clé étrangère
    # entre services, chaque micro-service a sa propre base).
    customer_id = models.CharField(max_length=36, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.EN_ATTENTE)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Commande {self.pk} ({self.get_status_display()})"


class OrderItem(models.Model):
    """Une ligne de commande. Le nom et le prix sont copiés au moment de la commande
    pour garder l'historique même si le catalogue change ensuite."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product_id = models.PositiveIntegerField()
    product_name = models.CharField(max_length=150)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])

    class Meta:
        constraints = [models.UniqueConstraint(fields=["order", "product_id"], name="unique_product_per_order")]

    @property
    def line_total(self):
        return self.unit_price * self.quantity
