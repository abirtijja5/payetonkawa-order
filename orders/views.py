"""Endpoints REST du service Commandes."""
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .messaging import publish
from .models import Order
from .permissions import IsStaffOrOwner
from .serializers import OrderCreateSerializer, OrderSerializer
from .services import cancel_order, order_event

# Changements de statut autorisés (machine à états)
TRANSITIONS = {
    Order.Status.EN_ATTENTE: {Order.Status.VALIDEE, Order.Status.ANNULEE},
    Order.Status.VALIDEE: {Order.Status.EXPEDIEE, Order.Status.ANNULEE},
    Order.Status.EXPEDIEE: {Order.Status.LIVREE},
    Order.Status.LIVREE: set(),
    Order.Status.ANNULEE: set(),
}


class OrderViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                   mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """
    Commandes.
    - POST   /api/orders/                 créer une commande (client connecté)
    - GET    /api/orders/                 mes commandes (toutes pour un admin) ?status=  ?customer_id=
    - GET    /api/orders/{id}/            détail
    - PATCH  /api/orders/{id}/status/     changer le statut (admin)
    - POST   /api/orders/{id}/cancel/     annuler (client propriétaire si en attente, ou admin)
    - DELETE /api/orders/{id}/            supprimer (admin)
    """

    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated, IsStaffOrOwner]
    ordering_fields = ["created_at", "total_amount"]
    search_fields = ["items__product_name"]

    def get_queryset(self):
        queryset = Order.objects.prefetch_related("items")
        user = self.request.user
        if not user.is_staff:
            queryset = queryset.filter(customer_id=str(user.id))
        elif self.request.query_params.get("customer_id"):
            queryset = queryset.filter(customer_id=self.request.query_params["customer_id"])
        if self.request.query_params.get("status"):
            queryset = queryset.filter(status=self.request.query_params["status"])
        return queryset.distinct()

    def get_permissions(self):
        if self.action in ("destroy", "change_status"):
            return [permissions.IsAdminUser()]
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        serializer = OrderCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        publish("order.created", order_event(order))  # le service Produits décrémente le stock
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch"], url_path="status")
    def change_status(self, request, pk=None):
        order = self.get_object()
        new_status = request.data.get("status")
        if new_status not in Order.Status.values:
            return Response({"status": f"Valeurs possibles : {', '.join(Order.Status.values)}"}, status=400)
        if new_status not in TRANSITIONS[order.status]:
            return Response({"status": f"Passage de '{order.status}' à '{new_status}' interdit."}, status=400)
        if new_status == Order.Status.ANNULEE:
            cancel_order(order)
        else:
            order.status = new_status
            order.save(update_fields=["status", "updated_at"])
            publish("order.status_changed", order_event(order))
        return Response(OrderSerializer(order).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        order = self.get_object()
        if not request.user.is_staff and order.status != Order.Status.EN_ATTENTE:
            return Response({"detail": "Seule une commande en attente peut être annulée."}, status=400)
        if Order.Status.ANNULEE not in TRANSITIONS[order.status]:
            return Response({"detail": "Cette commande ne peut plus être annulée."}, status=400)
        cancel_order(order)
        return Response(OrderSerializer(order).data)

    def perform_destroy(self, instance):
        cancel_order(instance)  # remet le stock si besoin
        instance.delete()
