"""Tests unitaires et d'intégration du service Commandes.
Les services Clients et Produits sont simulés (mock) : on teste ce service isolément."""
from decimal import Decimal
from unittest.mock import MagicMock, patch

import requests
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from . import clients, messaging
from .events import HANDLERS
from .models import Order, OrderItem

ALICE = "11111111-1111-1111-1111-111111111111"
BOB = "22222222-2222-2222-2222-222222222222"
CATALOGUE = {
    1: {"id": 1, "name": "Moka Sidamo", "price": "12.50", "stock": 40},
    2: {"id": 2, "name": "Santos", "price": "8.90", "stock": 2},
}


def jwt_for(user_id, is_staff=False):
    token = AccessToken()
    token["user_id"] = user_id
    token["is_staff"] = is_staff
    return f"Bearer {token}"


def fake_get_product(product_id):
    return CATALOGUE.get(product_id)


@patch("orders.services.publish")
@patch("orders.views.publish")
@patch("orders.clients.get_product", side_effect=fake_get_product)
class OrderCreationTests(APITestCase):
    url = reverse("order-list")

    def setUp(self):
        self.client.credentials(HTTP_AUTHORIZATION=jwt_for(ALICE))

    def test_creation_calcule_le_total_et_publie(self, _get, pub_views, pub_services):
        data = {"items": [{"product_id": 1, "quantity": 2}, {"product_id": 2, "quantity": 1}]}
        response = self.client.post(self.url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["total_amount"], "33.90")
        self.assertEqual(response.data["customer_id"], ALICE)
        self.assertEqual(response.data["items"][0]["product_name"], "Moka Sidamo")
        event_name, payload = pub_views.call_args[0]
        self.assertEqual(event_name, "order.created")
        self.assertEqual(len(payload["items"]), 2)

    def test_sans_jeton(self, *_):
        self.client.credentials()
        response = self.client.post(self.url, {"items": [{"product_id": 1, "quantity": 1}]}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_commande_vide(self, *_):
        response = self.client.post(self.url, {"items": []}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_quantite_invalide(self, *_):
        response = self.client.post(self.url, {"items": [{"product_id": 1, "quantity": 0}]}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_produit_en_double(self, *_):
        items = [{"product_id": 1, "quantity": 1}, {"product_id": 1, "quantity": 2}]
        response = self.client.post(self.url, {"items": items}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_produit_inexistant(self, *_):
        response = self.client.post(self.url, {"items": [{"product_id": 99, "quantity": 1}]}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("introuvable", response.data["items"][0])

    def test_stock_insuffisant(self, _get, pub_views, _pub):
        response = self.client.post(self.url, {"items": [{"product_id": 2, "quantity": 5}]}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Stock insuffisant", response.data["items"][0])
        self.assertEqual(Order.objects.count(), 0)
        pub_views.assert_not_called()

    def test_un_client_ne_commande_pas_pour_un_autre(self, *_):
        data = {"customer_id": BOB, "items": [{"product_id": 1, "quantity": 1}]}
        response = self.client.post(self.url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("orders.clients.client_exists", return_value=True)
    def test_admin_commande_pour_un_client(self, mock_exists, *_):
        self.client.credentials(HTTP_AUTHORIZATION=jwt_for("admin", is_staff=True))
        data = {"customer_id": BOB, "items": [{"product_id": 1, "quantity": 1}]}
        response = self.client.post(self.url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["customer_id"], BOB)

    @patch("orders.clients.client_exists", return_value=False)
    def test_admin_client_inconnu(self, mock_exists, *_):
        self.client.credentials(HTTP_AUTHORIZATION=jwt_for("admin", is_staff=True))
        data = {"customer_id": BOB, "items": [{"product_id": 1, "quantity": 1}]}
        self.assertEqual(self.client.post(self.url, data, format="json").status_code, 400)


@patch("orders.clients._get", side_effect=clients.ServiceUnavailable())
class FaultToleranceTests(APITestCase):
    def test_service_produits_en_panne_renvoie_503(self, _):
        self.client.credentials(HTTP_AUTHORIZATION=jwt_for(ALICE))
        response = self.client.post(reverse("order-list"), {"items": [{"product_id": 1, "quantity": 1}]},
                                    format="json")
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)


class ServiceClientTests(APITestCase):
    """Tests des appels HTTP vers les autres services (requests simulé)."""

    def fake_response(self, code, data=None):
        response = MagicMock(status_code=code)
        response.json.return_value = data
        return response

    @patch("orders.clients.requests.get")
    def test_get_product(self, mock_get):
        mock_get.return_value = self.fake_response(200, CATALOGUE[1])
        self.assertEqual(clients.get_product(1)["name"], "Moka Sidamo")
        mock_get.return_value = self.fake_response(404)
        self.assertIsNone(clients.get_product(1))
        mock_get.return_value = self.fake_response(500)
        with self.assertRaises(clients.ServiceUnavailable):
            clients.get_product(1)

    @patch("orders.clients.requests.get", side_effect=requests.ConnectionError())
    def test_timeout(self, _):
        with self.assertRaises(clients.ServiceUnavailable):
            clients.get_product(1)

    @patch("orders.clients.requests.get")
    def test_client_exists(self, mock_get):
        mock_get.return_value = self.fake_response(200)
        self.assertTrue(clients.client_exists(BOB, "Bearer x"))
        self.assertEqual(mock_get.call_args.kwargs["headers"], {"Authorization": "Bearer x"})
        mock_get.return_value = self.fake_response(404)
        self.assertFalse(clients.client_exists(BOB, "Bearer x"))
        mock_get.return_value = self.fake_response(502)
        with self.assertRaises(clients.ServiceUnavailable):
            clients.client_exists(BOB, "Bearer x")


@patch("orders.services.publish")
@patch("orders.views.publish")
class OrderManagementTests(APITestCase):
    def setUp(self):
        self.order_alice = self.make_order(ALICE)
        self.order_bob = self.make_order(BOB)

    def make_order(self, customer):
        order = Order.objects.create(customer_id=customer, total_amount=Decimal("25.00"))
        OrderItem.objects.create(order=order, product_id=1, product_name="Moka", unit_price=Decimal("12.50"),
                                 quantity=2)
        return order

    def as_user(self, user_id, staff=False):
        self.client.credentials(HTTP_AUTHORIZATION=jwt_for(user_id, staff))

    def test_un_client_ne_voit_que_ses_commandes(self, *_):
        self.as_user(ALICE)
        response = self.client.get(reverse("order-list"))
        self.assertEqual([o["id"] for o in response.data], [self.order_alice.id])
        detail = reverse("order-detail", kwargs={"pk": self.order_bob.id})
        self.assertEqual(self.client.get(detail).status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_voit_tout_et_filtre(self, *_):
        self.as_user("admin", staff=True)
        self.assertEqual(len(self.client.get(reverse("order-list")).data), 2)
        self.assertEqual(len(self.client.get(reverse("order-list"), {"customer_id": BOB}).data), 1)
        self.assertEqual(len(self.client.get(reverse("order-list"), {"status": "livree"}).data), 0)

    def test_changement_de_statut(self, pub_views, _):
        self.as_user("admin", staff=True)
        url = reverse("order-change-status", kwargs={"pk": self.order_alice.id})
        response = self.client.patch(url, {"status": "validee"}, format="json")
        self.assertEqual(response.data["status"], "validee")
        self.assertEqual(pub_views.call_args[0][0], "order.status_changed")

    def test_transition_interdite(self, *_):
        self.as_user("admin", staff=True)
        url = reverse("order-change-status", kwargs={"pk": self.order_alice.id})
        self.assertEqual(self.client.patch(url, {"status": "livree"}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(url, {"status": "nimporte"}, format="json").status_code, 400)

    def test_annulation_par_admin_via_statut(self, _, pub_services):
        self.as_user("admin", staff=True)
        url = reverse("order-change-status", kwargs={"pk": self.order_alice.id})
        self.client.patch(url, {"status": "annulee"}, format="json")
        self.assertEqual(pub_services.call_args[0][0], "order.cancelled")

    def test_client_ne_change_pas_le_statut(self, *_):
        self.as_user(ALICE)
        url = reverse("order-change-status", kwargs={"pk": self.order_alice.id})
        self.assertEqual(self.client.patch(url, {"status": "livree"}, format="json").status_code, 403)

    def test_client_annule_sa_commande_en_attente(self, _, pub_services):
        self.as_user(ALICE)
        response = self.client.post(reverse("order-cancel", kwargs={"pk": self.order_alice.id}))
        self.assertEqual(response.data["status"], "annulee")
        event_name, payload = pub_services.call_args[0]
        self.assertEqual(event_name, "order.cancelled")
        self.assertEqual(payload["items"], [{"product_id": 1, "quantity": 2}])

    def test_client_ne_peut_pas_annuler_une_commande_validee(self, *_):
        Order.objects.filter(pk=self.order_alice.pk).update(status="validee")
        self.as_user(ALICE)
        response = self.client.post(reverse("order-cancel", kwargs={"pk": self.order_alice.id}))
        self.assertEqual(response.status_code, 400)

    def test_commande_livree_non_annulable(self, *_):
        Order.objects.filter(pk=self.order_alice.pk).update(status="livree")
        self.as_user("admin", staff=True)
        response = self.client.post(reverse("order-cancel", kwargs={"pk": self.order_alice.id}))
        self.assertEqual(response.status_code, 400)

    def test_suppression_reservee_admin(self, _, pub_services):
        self.as_user(ALICE)
        url = reverse("order-detail", kwargs={"pk": self.order_alice.id})
        self.assertEqual(self.client.delete(url).status_code, 403)
        self.as_user("admin", staff=True)
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertFalse(Order.objects.filter(pk=self.order_alice.pk).exists())
        self.assertEqual(pub_services.call_args[0][0], "order.cancelled")

    def test_evenement_client_supprime_annule_ses_commandes(self, _, pub_services):
        HANDLERS["client.deleted"]({"id": BOB})
        self.order_bob.refresh_from_db()
        self.order_alice.refresh_from_db()
        self.assertEqual(self.order_bob.status, "annulee")
        self.assertEqual(self.order_alice.status, "en_attente")


RABBIT_ON = {"ENABLED": True, "HOST": "x", "PORT": 1, "USER": "g", "PASSWORD": "g", "EXCHANGE": "e"}


class MessagingTests(APITestCase):
    """Publication RabbitMQ : activée, désactivée, et en panne (tolérance aux pannes)."""

    @override_settings(RABBITMQ={"ENABLED": False})
    def test_publication_desactivee(self):
        self.assertFalse(messaging.publish("test.event", {"id": 1}))
        self.assertIsNone(messaging.start_consumer("q", {"a": print}))

    @override_settings(RABBITMQ=RABBIT_ON)
    @patch("orders.messaging._connection", side_effect=ConnectionError("RabbitMQ en panne"))
    def test_rabbitmq_en_panne_ne_bloque_pas(self, _):
        with self.assertLogs("orders.messaging", level="ERROR"):
            self.assertFalse(messaging.publish("test.event", {"id": 1}))

    @override_settings(RABBITMQ=RABBIT_ON)
    @patch("orders.messaging._connection")
    def test_publication_ok(self, mock_connection):
        self.assertTrue(messaging.publish("test.event", {"id": 1}))
        channel = mock_connection.return_value.channel.return_value
        body = channel.basic_publish.call_args.kwargs["body"]
        self.assertIn('"type": "test.event"', body)

    @override_settings(RABBITMQ=RABBIT_ON)
    @patch("orders.messaging.threading.Thread")
    def test_demarrage_du_consommateur(self, mock_thread):
        messaging.start_consumer("q", {"a.b": print})
        mock_thread.return_value.start.assert_called_once()

    @override_settings(RABBITMQ=RABBIT_ON)
    @patch("orders.messaging._connection")
    def test_consommateur_traite_et_acquitte(self, mock_connection):
        channel = mock_connection.return_value.channel.return_value
        received = []

        def fake_consume():
            on_message = channel.basic_consume.call_args.kwargs["on_message_callback"]
            method = type("M", (), {"routing_key": "a.b", "delivery_tag": 1})()
            on_message(channel, method, None, b'{"data": {"x": 1}}')
            on_message(channel, method, None, b"pas du json")
            raise KeyboardInterrupt  # sort de la boucle infinie pour le test

        channel.start_consuming.side_effect = fake_consume
        with self.assertRaises(KeyboardInterrupt), self.assertLogs("orders.messaging", level="ERROR"):
            messaging._consume_forever("q", {"a.b": received.append})
        self.assertEqual(received, [{"x": 1}])
        channel.basic_ack.assert_called_once_with(delivery_tag=1)
        channel.basic_nack.assert_called_once_with(delivery_tag=1, requeue=False)


class ModelTests(APITestCase):
    def test_affichage_et_total_ligne(self):
        order = Order.objects.create(customer_id=ALICE)
        item = OrderItem(order=order, product_id=1, product_name="Moka", unit_price=Decimal("2.50"), quantity=4)
        self.assertEqual(item.line_total, Decimal("10.00"))
        self.assertEqual(str(order), f"Commande {order.pk} (En attente)")
