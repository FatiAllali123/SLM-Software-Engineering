FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# pytest, pour lancer les tests generes par les agents.
# Installe a la construction seulement : le conteneur d'execution n'a aucun acces a Internet.
RUN pip install --no-cache-dir --root-user-action=ignore pytest==8.3.4

# Utilisateur sans droits d'administrateur
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin sandbox
USER 10001:10001

WORKDIR /tmp