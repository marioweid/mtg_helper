resource "google_project_iam_member" "iap_tunnel" {
  project = var.project_id
  role    = "roles/iap.tunnelResourceAccessor"
  member  = var.admin_iam_member

  depends_on = [google_project_service.iap]
}

resource "google_project_iam_member" "os_login" {
  project = var.project_id
  role    = "roles/compute.osLogin"
  member  = var.admin_iam_member

  depends_on = [google_project_service.oslogin]
}

resource "google_service_account" "vm" {
  account_id   = "${var.vm_name}-vm"
  display_name = "Service account for the ${var.vm_name} VM"

  depends_on = [google_project_service.compute]
}
