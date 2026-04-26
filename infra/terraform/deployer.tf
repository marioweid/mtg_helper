# GitHub Actions deployer: Workload Identity Federation, no static keys.
# GitHub OIDC token → STS → impersonate SA → SSH via IAP → docker compose pull/up.

resource "google_service_account" "deployer" {
  account_id   = "${var.vm_name}-deployer"
  display_name = "GitHub Actions deployer for ${var.vm_name}"

  depends_on = [google_project_service.compute]
}

resource "google_project_iam_member" "deployer_iap_tunnel" {
  project = var.project_id
  role    = "roles/iap.tunnelResourceAccessor"
  member  = "serviceAccount:${google_service_account.deployer.email}"

  depends_on = [google_project_service.iap]
}

resource "google_project_iam_member" "deployer_os_login" {
  project = var.project_id
  role    = "roles/compute.osLogin"
  member  = "serviceAccount:${google_service_account.deployer.email}"

  depends_on = [google_project_service.oslogin]
}

# Lets gcloud compute ssh resolve the instance + use IAP.
resource "google_project_iam_member" "deployer_compute_viewer" {
  project = var.project_id
  role    = "roles/compute.viewer"
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "${var.vm_name}-github"
  display_name              = "GitHub Actions"

  depends_on = [
    google_project_service.iam_credentials,
    google_project_service.sts,
  ]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github"
  display_name                       = "GitHub OIDC"

  attribute_condition = "assertion.repository == \"${var.github_repository}\" && assertion.ref == \"refs/heads/${var.github_branch}\""

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "deployer_wif_binding" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repository}"
}
