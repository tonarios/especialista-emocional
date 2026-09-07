"""Backend de nube: store de Firestore, sesiones ADK y analítica.

Firestore se prueba con un doble en memoria que reproduce el contrato que usa
el código (`document/collection/get/set/create/stream/add`). No es un mock de
llamadas: es un almacén real en un diccionario, así que las aserciones son
sobre comportamiento observable (qué queda guardado), no sobre qué método se
llamó.

Lo que de verdad importa aquí es que **el aislamiento entre usuarios y la
prohibición de guardar texto de chats se cumplen también en la nube**, no solo
en Postgres.
"""
from __future__ import annotations

import asyncio

import pytest

from especialista import analytics
from especialista.config import settings
from especialista.stores.firestore import FirestoreStore


# ── Doble de Firestore ────────────────────────────────────────────

class FakeSnapshot:
    def __init__(self, doc_id: str, data: dict | None):
        self.id = doc_id
        self._data = data
        self.exists = data is not None
        self.reference = None

    def get(self, field):
        return (self._data or {}).get(field)

    def to_dict(self):
        return dict(self._data) if self._data else None


class AlreadyExists(Exception):
    """Réplica de google.api_core.exceptions.AlreadyExists (se detecta por nombre)."""


class FakeDocument:
    def __init__(self, store: dict, path: str):
        self._store = store
        self._path = path
        self.id = path.rsplit("/", 1)[-1]

    def get(self):
        return FakeSnapshot(self.id, self._store.get(self._path))

    def set(self, data):
        self._store[self._path] = dict(data)

    def create(self, data):
        if self._path in self._store:
            raise AlreadyExists("ya existe")
        self._store[self._path] = dict(data)

    def update(self, data):
        self._store.setdefault(self._path, {}).update(data)

    def delete(self):
        self._store.pop(self._path, None)

    def collection(self, name):
        return FakeCollection(self._store, f"{self._path}/{name}")


class FakeCollection:
    def __init__(self, store: dict, path: str):
        self._store = store
        self._path = path
        self._filters: list[tuple] = []

    def document(self, doc_id):
        return FakeDocument(self._store, f"{self._path}/{doc_id}")

    def add(self, data):
        n = len([k for k in self._store if k.startswith(self._path + "/")])
        self._store[f"{self._path}/auto{n}"] = dict(data)

    def where(self, field, _op, value):
        c = FakeCollection(self._store, self._path)
        c._filters = self._filters + [(field, value)]
        return c

    def order_by(self, _field):
        return self

    def list_documents(self):
        return list(self._docs())

    def _docs(self):
        prefix = self._path + "/"
        for path in sorted(self._store):
            if not path.startswith(prefix) or "/" in path[len(prefix):]:
                continue
            yield FakeDocument(self._store, path)

    def stream(self):
        for doc in self._docs():
            snap = doc.get()
            if all(snap.get(f) == v for f, v in self._filters):
                snap.reference = doc
                yield snap


class FakeFirestore:
    def __init__(self):
        self.data: dict[str, dict] = {}

    def collection(self, name):
        return FakeCollection(self.data, name)


@pytest.fixture
def store():
    return FirestoreStore(client=FakeFirestore())


# ── Store ─────────────────────────────────────────────────────────

def test_alta_y_lectura_de_usuario(store):
    store.create_user("Ana@Demo.CO", "pbkdf2$hash")
    assert store.get_user("ana@demo.co") == {
        "email": "ana@demo.co",
        "password_hash": "pbkdf2$hash",
    }


def test_email_duplicado_se_rechaza_de_forma_atomica(store):
    """`create()` falla si el documento existe: sin carrera entre dos altas."""
    store.create_user("ana@demo.co", "h1")
    with pytest.raises(ValueError, match="ya está registrado"):
        store.create_user("ana@demo.co", "h2")
    # La segunda alta no pisó la contraseña de la primera.
    assert store.get_user("ana@demo.co")["password_hash"] == "h1"


def test_email_se_normaliza_a_un_solo_documento(store):
    """Mayúsculas y espacios no crean cuentas distintas."""
    store.create_user("  Ana@Demo.co ", "h1")
    with pytest.raises(ValueError):
        store.create_user("ana@demo.co", "h2")


def test_usuario_inexistente_es_none(store):
    assert store.get_user("nadie@demo.co") is None


def test_perfil_y_aislamiento_entre_portadores(store):
    """FR-17: el historial de A no aparece en el de B."""
    store.upsert_profile({"user_id": "a@demo.co", "consultations": [{"term": ["garganta"]}]})
    store.upsert_profile({"user_id": "b@demo.co", "consultations": []})

    assert store.get_profile("a@demo.co")["consultations"] == [{"term": ["garganta"]}]
    assert store.get_profile("b@demo.co")["consultations"] == []

    ids = {p["user_id"] for p in store.list_profiles()}
    assert ids == {"a@demo.co", "b@demo.co"}


def test_borrado_de_historial_solo_afecta_al_portador(store):
    """FR-14b."""
    store.upsert_profile({"user_id": "a@demo.co", "consultations": [{"term": ["x"]}]})
    store.upsert_profile({"user_id": "b@demo.co", "consultations": [{"term": ["y"]}]})
    store.upsert_profile({"user_id": "a@demo.co", "consultations": []})

    assert store.get_profile("a@demo.co")["consultations"] == []
    assert store.get_profile("b@demo.co")["consultations"] == [{"term": ["y"]}]


def test_config_persiste_el_secreto_de_firma(store):
    assert store.get_config("signing_secret") is None
    store.set_config("signing_secret", "b64==")
    assert store.get_config("signing_secret") == "b64=="


def test_auditoria_recorta_detalles_enormes(store):
    """La auditoría registra QUÉ pasó, no vuelca payloads (NFR-07)."""
    store.write_audit({"action": "chat", "detail": {"x": "y" * 10_000}})
    fila = next(v for k, v in store._db.data.items() if k.startswith("audit_log/"))
    assert fila["detail"] == {"truncado": True}
    assert fila["action"] == "chat"


# ── Sesiones ADK sobre Firestore ──────────────────────────────────
#
# Los métodos de ADK son async y el proyecto no trae plugin de pytest para
# async, así que cada test envuelve su cuerpo con `asyncio.run`. Es una
# dependencia menos y deja explícito dónde empieza el event loop.

@pytest.fixture
def session_service():
    from especialista.firestore_sessions import FirestoreSessionService

    return FirestoreSessionService(FakeFirestore())


async def _turno(svc, user, sid, texto, autor="user"):
    from google.adk.events import Event
    from google.genai import types as gm

    s = await svc.get_session(app_name="ah_emociones", user_id=user, session_id=sid)
    if s is None:
        s = await svc.create_session(app_name="ah_emociones", user_id=user, session_id=sid)
    role = "user" if autor == "user" else "model"
    await svc.append_event(
        s, Event(author=autor, content=gm.Content(role=role, parts=[gm.Part(text=texto)]))
    )


def test_sesion_persiste_los_turnos_en_orden(session_service):
    """FR-12: la conversación sobrevive y se relee en orden cronológico."""

    async def run():
        for i in range(3):
            await _turno(session_service, "a@demo.co", "s1", f"mensaje {i}")
        return await session_service.get_session(
            app_name="ah_emociones", user_id="a@demo.co", session_id="s1"
        )

    s = asyncio.run(run())
    assert [e.content.parts[0].text for e in s.events] == [
        "mensaje 0", "mensaje 1", "mensaje 2",
    ]


def test_listar_sesiones_aisla_por_portador(session_service):
    """FR-17: A no ve las sesiones de B."""

    async def run():
        await _turno(session_service, "a@demo.co", "s-a", "hola")
        await _turno(session_service, "b@demo.co", "s-b", "hola")
        a = await session_service.list_sessions(app_name="ah_emociones", user_id="a@demo.co")
        b = await session_service.list_sessions(app_name="ah_emociones", user_id="b@demo.co")
        return [s.id for s in a.sessions], [s.id for s in b.sessions]

    de_a, de_b = asyncio.run(run())
    assert de_a == ["s-a"]
    assert de_b == ["s-b"]


def test_num_recent_events_devuelve_los_ultimos(session_service):
    from google.adk.sessions.base_session_service import GetSessionConfig

    async def run():
        for i in range(5):
            await _turno(session_service, "a@demo.co", "s1", f"m{i}")
        return await session_service.get_session(
            app_name="ah_emociones", user_id="a@demo.co", session_id="s1",
            config=GetSessionConfig(num_recent_events=2),
        )

    s = asyncio.run(run())
    assert [e.content.parts[0].text for e in s.events] == ["m3", "m4"]


def test_borrar_sesion_elimina_tambien_sus_eventos(session_service):
    """Firestore no borra subcolecciones en cascada: hay que hacerlo a mano."""

    async def run():
        await _turno(session_service, "a@demo.co", "s1", "hola")
        await session_service.delete_session(
            app_name="ah_emociones", user_id="a@demo.co", session_id="s1"
        )

    asyncio.run(run())
    assert not [k for k in session_service._db.data if k.startswith("sessions/")]


def test_sesion_inexistente_es_none(session_service):
    s = asyncio.run(
        session_service.get_session(
            app_name="ah_emociones", user_id="a@demo.co", session_id="no-existe"
        )
    )
    assert s is None


# ── Analítica: la regla dura de NFR-07 ────────────────────────────

@pytest.fixture
def analytics_on(monkeypatch):
    monkeypatch.setattr(settings, "bq_dataset", "proj.ds")
    monkeypatch.setattr(settings, "analytics_salt", "sal-de-prueba")
    enviados: list[tuple[str, dict]] = []
    monkeypatch.setattr(analytics, "emit", lambda t, r: enviados.append((t, r)))
    return enviados


def test_sin_sal_no_se_emite_nada(monkeypatch):
    """Es preferible perder analítica a escribir un identificador reversible."""
    monkeypatch.setattr(settings, "bq_dataset", "proj.ds")
    monkeypatch.setattr(settings, "analytics_salt", "")
    assert analytics.enabled() is False


def test_el_usuario_viaja_como_hash_no_como_email(analytics_on):
    analytics.consulta(
        email="ana@demo.co", session_id="s1", symptoms=["dolor de garganta"],
        terms=["garganta-dolores-de"], risk_tier="estandar", kind="respuesta",
    )
    _, fila = analytics_on[0]
    assert "ana@demo.co" not in str(fila)
    assert fila["user_hash"] == analytics.user_hash("ana@demo.co")
    assert len(fila["user_hash"]) == 32


def test_el_hash_depende_de_la_sal(monkeypatch):
    """Con otra sal, otro hash: la sal secreta impide revertirlo por fuerza bruta."""
    monkeypatch.setattr(settings, "analytics_salt", "sal-a")
    a = analytics.user_hash("ana@demo.co")
    monkeypatch.setattr(settings, "analytics_salt", "sal-b")
    assert analytics.user_hash("ana@demo.co") != a


def test_la_consulta_del_usuario_nunca_viaja_en_claro(analytics_on):
    """FR-05b/NFR-07: a BigQuery va el hash de la consulta, jamás el texto."""
    texto = "me duele mucho la garganta desde que discutí con mi jefe"
    analytics.recuperacion(
        query=texto, k=5, hit_lexico=True, sin_cobertura=False,
        top_slugs=["garganta-dolores-de"],
    )
    _, fila = analytics_on[0]
    assert texto not in str(fila)
    assert fila["query_hash"] == analytics.text_hash(texto)


def test_guardarrail_registra_tipo_y_grupo(analytics_on):
    analytics.guardarrail(tipo="emergencia", grupo="suicidal_ideation", email="ana@demo.co")
    tabla, fila = analytics_on[0]
    assert tabla == "guardarrailes"
    assert fila["tipo"] == "emergencia"
    assert fila["grupo"] == "suicidal_ideation"
    assert "ana@demo.co" not in str(fila)
