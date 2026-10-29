# PayeTonKawa – API Commandes

Micro-service de prise et suivi des commandes. Django 5.2 + Django REST Framework, base PostgreSQL dédiée (SQLite en développement).

## Lancer seul (développement)

```bash
python -m venv .venv && source .venv/bin/activate   # Windows : .venv\Scripts\activate
pip install -r requirements-dev.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:8003
```

Documentation interactive : http://localhost:8003/api/docs/ (via la passerelle : http://localhost:8080/order/api/docs/)

La plateforme complète (3 services, RabbitMQ, PostgreSQL, passerelle, supervision) se lance depuis le dépôt **payetonkawa-infra**.

## Endpoints

| Méthode | URL | Accès |
|---|---|---|
| GET, POST | `/api/orders/` (`?status=`, `?customer_id=` pour l'admin) | client connecté |
| GET | `/api/orders/{id}/` | propriétaire ou admin |
| POST | `/api/orders/{id}/cancel/` | propriétaire (si en attente) ou admin |
| PATCH | `/api/orders/{id}/status/` | admin |
| DELETE | `/api/orders/{id}/` | admin |

Authentification : en-tête `Authorization: Bearer <jeton>` (jeton obtenu sur le service Clients).

## Événements RabbitMQ

Publie `order.created`, `order.cancelled`, `order.status_changed`. Écoute `client.deleted` (annule les commandes non expédiées). Appelle en REST les services Clients et Produits (délai max 3 s, erreur 503 si indisponible).

## Tests

```bash
python manage.py test                       # tests unitaires et d'intégration
coverage run manage.py test && coverage report
flake8 .
```


## Variables d'environnement

| Variable | Rôle |
|---|---|
| `DJANGO_SECRET_KEY`, `DJANGO_DEBUG` | sécurité Django |
| `JWT_SIGNING_KEY` | clé partagée de signature des jetons |
| `DB_ENGINE=postgres`, `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | base de données |
| `RABBITMQ_ENABLED`, `RABBITMQ_HOST`, `RABBITMQ_USER`, `RABBITMQ_PASSWORD` | message broker |
| `URL_PREFIX` | préfixe derrière la passerelle (`/order`) |
