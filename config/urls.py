"""Routes principales du service order."""
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView


def health(request):
    """Sonde de vie utilisée par Docker et le monitoring."""
    return JsonResponse({"status": "ok", "service": "order"})


urlpatterns = [
    path("health/", health, name="health"),
    path("api/", include("orders.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("", include("django_prometheus.urls")),  # expose /metrics pour Prometheus
]
