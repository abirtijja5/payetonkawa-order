from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from . import clients
from .models import Order, OrderItem


class OrderItemSerializer(serializers.ModelSerializer):
    line_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = ["product_id", "product_name", "unit_price", "quantity", "line_total"]
        read_only_fields = ["product_name", "unit_price"]


class ItemInputSerializer(serializers.Serializer):
    product_id = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1, max_value=10000)


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = ["id", "customer_id", "status", "total_amount", "items", "created_at", "updated_at"]
        read_only_fields = ["id", "customer_id", "total_amount", "created_at", "updated_at"]


class OrderCreateSerializer(serializers.Serializer):
    """
    Création d'une commande :
    {"items": [{"product_id": 1, "quantity": 2}], "customer_id": "<uuid, admin seulement>"}
    """

    customer_id = serializers.CharField(required=False, max_length=36)
    items = ItemInputSerializer(many=True, allow_empty=False)

    def validate_items(self, items):
        ids = [i["product_id"] for i in items]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("Un même produit ne peut apparaître qu'une fois.")
        return items

    def validate(self, attrs):
        request = self.context["request"]
        user = request.user
        customer_id = attrs.get("customer_id") or str(user.id)
        if customer_id != str(user.id):
            if not user.is_staff:
                raise serializers.ValidationError({"customer_id": "Vous ne pouvez commander que pour vous-même."})
            if not clients.client_exists(customer_id, request.headers.get("Authorization", "")):
                raise serializers.ValidationError({"customer_id": "Client introuvable."})
        attrs["customer_id"] = customer_id

        # Vérification de chaque produit auprès du service Produits
        lines, errors = [], []
        for item in attrs["items"]:
            product = clients.get_product(item["product_id"])
            if product is None:
                errors.append(f"Produit {item['product_id']} introuvable.")
            elif product["stock"] < item["quantity"]:
                errors.append(f"Stock insuffisant pour {product['name']} (disponible : {product['stock']}).")
            else:
                lines.append({**item, "product_name": product["name"], "unit_price": Decimal(product["price"])})
        if errors:
            raise serializers.ValidationError({"items": errors})
        attrs["lines"] = lines
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        lines = validated_data["lines"]
        order = Order.objects.create(
            customer_id=validated_data["customer_id"],
            total_amount=sum(line["unit_price"] * line["quantity"] for line in lines),
        )
        OrderItem.objects.bulk_create(OrderItem(order=order, **line) for line in lines)
        return order
