# Orquestación local con Docker (D9: SOLO targets de Docker).
#
# El índice FAISS se genera en el HOST con `scripts/index.sh` (necesita Ollama);
# el contenedor lo consume montando ./data/index en modo lectura (§11).

# Contraseña local de desarrollo (no es un secreto de producción; cámbiala con
# `export LOCAL_DB_PASSWORD=...` o desde un .env del shell).
LOCAL_DB_PASSWORD ?= emociones_dev

.PHONY: build up down logs ps

build:
	docker compose build

up:
	LOCAL_DB_PASSWORD=$(LOCAL_DB_PASSWORD) docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

ps:
	docker compose ps
