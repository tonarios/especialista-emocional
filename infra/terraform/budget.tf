# Presupuesto con alertas — la red de seguridad de todo el diseño.
#
# El gasto previsto es ~USD 0.54/mes (docs/presupuesto-gcp.md). Lo único que
# escala con el uso es Vertex, así que un bucle de reintentos es el riesgo real.
# Este budget cuesta $0 y avisa al 50/90/100% de USD 5.
#
# Requiere roles/billing.costsManager sobre la cuenta de facturación. Si no se
# tiene, se deja `billing_account = ""` y el recurso no se crea (pero entonces
# hay que ponerlo a mano en la consola: no dejar el proyecto sin alerta).

resource "google_billing_budget" "monthly" {
  provider = google.billing
  count    = var.billing_account != "" ? 1 : 0

  billing_account = var.billing_account
  display_name    = "Presupuesto ${var.service_name}"

  budget_filter {
    projects               = ["projects/${data.google_project.this.number}"]
    calendar_period        = "MONTH"
    credit_types_treatment = "INCLUDE_ALL_CREDITS"
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(var.budget_amount_usd)
    }
  }

  threshold_rules {
    threshold_percent = 0.5
  }
  threshold_rules {
    threshold_percent = 0.9
  }
  threshold_rules {
    threshold_percent = 1.0
  }
  # Aviso también sobre el gasto PREVISTO, no solo el ya incurrido: avisa antes
  # de gastarlo, que es cuando sirve.
  threshold_rules {
    threshold_percent = 1.0
    spend_basis       = "FORECASTED_SPEND"
  }

  depends_on = [google_project_service.services]
}
