"""
Appels REST synchrones vers les autres micro-services.

Chaque appel a un délai maximum (timeout) : si un service ne répond pas,
on renvoie une erreur 503 claire au lieu de bloquer (tolérance aux pannes).
"""
import logging

import requests
from django.conf import settings
from rest_framework.exceptions import APIException

logger = logging.getLogger(__name__)


class ServiceUnavailable(APIException):
    status_code = 503
    default_detail = "Un service dépendant est momentanément indisponible. Réessayez plus tard."
    default_code = "service_unavailable"


def _get(url, headers=None):
    try:
        return requests.get(url, headers=headers or {}, timeout=settings.SERVICE_TIMEOUT)
    except requests.RequestException as exc:
        logger.error("Service injoignable : %s (%s)", url, exc)
        raise ServiceUnavailable()


def get_product(product_id):
    """Renvoie le produit (dict) ou None s'il n'existe pas."""
    response = _get(f"{settings.PRODUCT_SERVICE_URL}/api/products/{product_id}/")
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise ServiceUnavailable()
    return response.json()


def client_exists(customer_id, auth_header):
    """Vérifie auprès du service Clients que le client existe (avec le jeton de l'appelant)."""
    response = _get(
        f"{settings.CLIENT_SERVICE_URL}/api/clients/{customer_id}/",
        headers={"Authorization": auth_header},
    )
    if response.status_code == 200:
        return True
    if response.status_code in (400, 404):
        return False
    raise ServiceUnavailable()
