"""Seguridad de la infraestructura GCP (M9), verificada sobre el `terraform plan` REAL.

No se auditan los `.tf` como texto —eso se engaña con un comentario— sino el
plan resuelto (`outputs/evidence/tfplan.json`), que es lo que Terraform crearía
de verdad: variables interpoladas, defaults aplicados y valores calculados.

Regenerar la evidencia:
    scripts/infra_audit.sh

Los tests se saltan (no fallan) si no hay plan: no todo el mundo que corre la
suite tiene credenciales de GCP. En CI con credenciales, `infra_audit.sh` lo
genera antes de pytest.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "outputs" / "evidence" / "tfplan.json"

# Roles que jamás debe tener el runtime: dan poder muy por encima de lo que la
# app necesita y convierten cualquier RCE en compromiso del proyecto.
ROLES_PROHIBIDOS = {
    "roles/owner",
    "roles/editor",
    "roles/iam.securityAdmin",
    "roles/iam.serviceAccountKeyAdmin",
    "roles/datastore.owner",
    "roles/bigquery.admin",
    "roles/bigquery.dataOwner",
    "roles/secretmanager.admin",
    "roles/storage.admin",
    "roles/aiplatform.admin",
}

# Campos que NO pueden existir en el dataset analítico: contendrían texto libre
# del usuario, que es dato de salud (NFR-07) y no debe salir del almacén
# operacional. La analítica es de metadatos.
CAMPOS_PROHIBIDOS_BQ = {
    "message", "mensaje", "text", "texto", "query", "consulta", "prompt",
    "response", "respuesta", "content", "contenido", "answer", "chat",
    "email", "correo", "user_id", "password", "token",
}


def _plan() -> dict:
    if not PLAN.exists():
        pytest.skip(f"sin plan en {PLAN}; corre scripts/infra_audit.sh")
    return json.loads(PLAN.read_text(encoding="utf-8"))


def _recursos(tipo: str) -> list[dict]:
    res = _plan()["planned_values"]["root_module"]["resources"]
    return [r["values"] for r in res if r["type"] == tipo]


def _uno(tipo: str) -> dict:
    rs = _recursos(tipo)
    assert len(rs) == 1, f"se esperaba exactamente un {tipo}, hay {len(rs)}"
    return rs[0]


# ── IAM: mínimo privilegio ────────────────────────────────────────────────

def test_runtime_sin_roles_privilegiados():
    """El service account del contenedor no tiene roles de administración."""
    roles = {r["role"] for r in _recursos("google_project_iam_member")}
    prohibidos = roles & ROLES_PROHIBIDOS
    assert not prohibidos, f"roles prohibidos concedidos al runtime: {prohibidos}"


def test_roles_de_proyecto_son_los_esperados():
    """Ningún rol a nivel proyecto que no esté justificado explícitamente."""
    esperados = {
        "roles/aiplatform.user",
        "roles/datastore.user",
        "roles/bigquery.jobUser",
        "roles/logging.logWriter",
    }
    roles = {r["role"] for r in _recursos("google_project_iam_member")}
    assert roles == esperados, f"roles de proyecto inesperados: {roles ^ esperados}"


def test_secretos_y_dataset_con_alcance_por_recurso():
    """Secret Manager y BigQuery se conceden sobre el recurso, no sobre el proyecto."""
    roles_proyecto = {r["role"] for r in _recursos("google_project_iam_member")}
    assert "roles/secretmanager.secretAccessor" not in roles_proyecto, \
        "el acceso a secretos está a nivel proyecto: debe acotarse a cada secreto"
    assert "roles/bigquery.dataEditor" not in roles_proyecto, \
        "el acceso a datos de BQ está a nivel proyecto: debe acotarse al dataset"

    secretos = _recursos("google_secret_manager_secret_iam_member")
    assert len(secretos) == 2, "cada secreto necesita su propia concesión acotada"
    assert all(s["role"] == "roles/secretmanager.secretAccessor" for s in secretos)

    ds = _uno("google_bigquery_dataset_iam_member")
    assert ds["role"] == "roles/bigquery.dataEditor", \
        "sobre el dataset basta dataEditor; dataOwner permitiría borrarlo"


def test_no_se_crean_claves_de_service_account():
    """Una clave descargable es un secreto que se filtra. Cloud Run usa la identidad."""
    res = _plan()["planned_values"]["root_module"]["resources"]
    claves = [r for r in res if r["type"] == "google_service_account_key"]
    assert not claves, "no debe crearse ninguna clave de service account"


def test_vertex_sin_clave_de_api():
    """Vertex se autentica por service account: no hay API key que rotar ni filtrar."""
    ids = {s["secret_id"] for s in _recursos("google_secret_manager_secret")}
    assert not any("api" in i and "key" in i for i in ids), \
        f"hay un secreto que parece una clave de API: {ids}"
    assert "roles/aiplatform.user" in {r["role"] for r in _recursos("google_project_iam_member")}


# ── Exposición pública ────────────────────────────────────────────────────

def test_solo_cloud_run_es_publico():
    """`allUsers` únicamente sobre el invoker de Cloud Run, en ningún otro sitio."""
    res = _plan()["planned_values"]["root_module"]["resources"]
    publicos = [
        r for r in res
        if "allUsers" in json.dumps(r.get("values", {}))
        or "allAuthenticatedUsers" in json.dumps(r.get("values", {}))
    ]
    tipos = {r["type"] for r in publicos}
    assert tipos <= {"google_cloud_run_v2_service_iam_member"}, \
        f"acceso público concedido fuera de Cloud Run: {tipos}"

    run_iam = _uno("google_cloud_run_v2_service_iam_member")
    assert run_iam["role"] == "roles/run.invoker", \
        "a allUsers solo se le da invoker, nunca admin ni developer"


def test_bucket_de_estado_es_privado():
    """El tfstate lleva el JWT_SECRET en claro: no puede ser público."""
    b = _uno("google_storage_bucket")
    assert b["public_access_prevention"] == "enforced", \
        "el bucket del estado debe tener public_access_prevention=enforced"
    assert b["uniform_bucket_level_access"] is True, \
        "sin acceso uniforme, una ACL por objeto puede exponer el estado"
    assert b["versioning"][0]["enabled"] is True, \
        "el estado necesita versionado para poder recuperarse"


# ── Datos de salud (NFR-07) ───────────────────────────────────────────────

def test_bigquery_no_admite_texto_de_chats():
    """El esquema analítico no tiene NINGÚN campo capaz de guardar la conversación."""
    for t in _recursos("google_bigquery_table"):
        campos = {c["name"].lower() for c in json.loads(t["schema"])}
        prohibidos = campos & CAMPOS_PROHIBIDOS_BQ
        assert not prohibidos, (
            f"la tabla {t['table_id']} tiene campos que podrían llevar texto de "
            f"chats o PII: {prohibidos} (NFR-07)"
        )


def test_bigquery_identifica_por_hash():
    """El usuario en analítica es un hash con sal, nunca el email."""
    tablas = {t["table_id"]: json.loads(t["schema"]) for t in _recursos("google_bigquery_table")}
    campos_consultas = {c["name"] for c in tablas["consultas"]}
    assert "user_hash" in campos_consultas
    assert "email" not in campos_consultas and "user_id" not in campos_consultas

    # La sal tiene que ser un secreto: si fuera pública, el hash de un email se
    # revierte por fuerza bruta sobre el espacio de direcciones conocidas.
    ids = {s["secret_id"] for s in _recursos("google_secret_manager_secret")}
    assert any("salt" in i for i in ids), "la sal del hash debe vivir en Secret Manager"


def test_tablas_analiticas_particionadas_por_dia():
    """Sin partición, cada consulta escanea la tabla entera y el free tier se va."""
    sin_particion = [
        t["table_id"] for t in _recursos("google_bigquery_table")
        if t["table_id"] != "eval" and not t.get("time_partitioning")
    ]
    assert not sin_particion, f"tablas de eventos sin partición diaria: {sin_particion}"


# ── Coste y disponibilidad ────────────────────────────────────────────────

def test_cloud_run_escala_a_cero():
    """La restricción del owner: sin tráfico, cero compute facturado."""
    svc = _uno("google_cloud_run_v2_service")
    tpl = svc["template"][0]
    assert tpl["scaling"][0]["min_instance_count"] == 0, "debe escalar a cero"
    assert tpl["containers"][0]["resources"][0]["cpu_idle"] is True, \
        "cpu_idle=false factura CPU fuera de las peticiones"


def test_cloud_run_tiene_tope_de_escalado():
    """Sin tope, una ráfaga (o un bucle) se come el free tier."""
    svc = _uno("google_cloud_run_v2_service")
    maximo = svc["template"][0]["scaling"][0]["max_instance_count"]
    assert 0 < maximo <= 10, f"max_instance_count fuera de rango razonable: {maximo}"


def test_existe_presupuesto_con_alertas():
    """La red de seguridad contra un gasto inesperado de Vertex."""
    b = _uno("google_billing_budget")
    umbrales = {r["threshold_percent"] for r in b["threshold_rules"]}
    assert umbrales >= {0.5, 0.9, 1.0}, f"faltan umbrales de alerta: {umbrales}"
    assert any(r.get("spend_basis") == "FORECASTED_SPEND" for r in b["threshold_rules"]), \
        "hace falta una alerta sobre el gasto previsto, no solo el incurrido"


def test_registry_tiene_politica_de_limpieza():
    """Sin limpieza, cada push acumula GB facturables indefinidamente."""
    repo = _uno("google_artifact_registry_repository")
    pols = repo.get("cleanup_policies") or []
    assert pols, "el repositorio de imágenes necesita política de limpieza"
    assert {p["action"] for p in pols} >= {"KEEP", "DELETE"}


def test_no_hay_cloud_sql_ni_vpc():
    """La arquitectura elegida (opción A) no lleva nada que corra 24/7."""
    tipos = {r["type"] for r in _plan()["planned_values"]["root_module"]["resources"]}
    caros = {t for t in tipos if "sql_database_instance" in t or "vpc_access_connector" in t}
    assert not caros, f"recursos que no escalan a cero en el plan: {caros}"


# ── Secretos ──────────────────────────────────────────────────────────────

def test_secretos_marcados_como_sensibles_en_el_plan():
    """Los valores generados no aparecen en claro en el JSON del plan."""
    crudo = PLAN.read_text(encoding="utf-8") if PLAN.exists() else pytest.skip("sin plan")
    plan = json.loads(crudo)
    after_unknown = plan.get("resource_changes", [])
    versiones = [
        c for c in after_unknown
        if c["type"] == "google_secret_manager_secret_version"
    ]
    assert versiones, "no hay versiones de secreto en el plan"
    for v in versiones:
        sensibles = v["change"].get("after_sensitive") or {}
        assert sensibles.get("secret_data") is True, (
            f"{v['address']}: secret_data no está marcado como sensible; "
            "podría acabar impreso en un log de CI"
        )


def test_secreto_jwt_se_inyecta_por_referencia():
    """El JWT_SECRET llega como referencia a Secret Manager, no como valor literal."""
    svc = _uno("google_cloud_run_v2_service")
    envs = svc["template"][0]["containers"][0]["env"]
    jwt = next(e for e in envs if e["name"] == "JWT_SECRET")
    assert jwt.get("value") in (None, ""), "JWT_SECRET no puede ir como valor literal"
    assert jwt["value_source"][0]["secret_key_ref"][0]["secret"], \
        "JWT_SECRET debe venir de Secret Manager"
