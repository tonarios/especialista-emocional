---
name: docker
description: Contenedor único back+front non-root en :8000 + servicio db postgres:16-alpine stock en compose, Ollama del host vía host.docker.internal y Makefile con SOLO targets Docker (build/up/down/logs/ps). M6, D9, §11, NFR-06.
---

# docker — M6: operación local (deseable)

## Cuándo activar

- Después de `frontend`. El sistema completo corre sin Docker; esto lo hace reproducible para la demo.

## Entradas

- `Dockerfile`, `docker-compose.yml`, `Makefile` del repo base (adaptar).
- PRD §7 (diagrama), §11, D9, NFR-04/06 (no secretos en imagen; contenedor non-root).

## Pasos

1. `Dockerfile`: imagen única **back+front** escuchando en `:8000`; usuario **non-root**; sin `.env` ni secretos dentro (NFR-04/06).
2. `docker-compose.yml`: servicio `db` = `postgres:16-alpine` (**stock, sin extensiones**) con volumen persistente; servicio `app` expone `:8000`; `OLLAMA_BASE_URL=http://host.docker.internal:11434`; índice FAISS montado desde `data/index/` (mount o baked).
3. `Makefile` con **SOLO** targets Docker: `build`, `up`, `down`, `logs`, `ps` (D9). Nada más.
4. Healthcheck del app y `depends_on` con readiness de Postgres.
5. Documentar la división: `scripts/index.sh` corre en host (necesita Ollama); el contenedor consume el índice generado.

## Salidas

- `Dockerfile`, `docker-compose.yml`, `Makefile` finales.

## Exit criteria (M6)

- [ ] `make up` → app+db arriba; `GET /health` 200; el chat responde con gemma4.
- [ ] `make down` + `make up` **no pierde** usuarios ni sesiones (volumen persistente).
- [ ] `docker compose exec app whoami` → usuario non-root.

## Verificación

```bash
make build && make up
curl -s localhost:8000/health
make down && make up          # persistencia
docker compose exec app whoami
```

Registrar en heartbeat: tamaño de imagen, usuario del contenedor, resultado del ciclo down/up.
