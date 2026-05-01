# Cloud Scheduler job that starts the spot VM if it has been preempted.
# Spot VMs are STOPPED on preemption, not auto-restarted by GCE.
# The job hits compute.instances.start every N minutes; if the instance is
# already running the API returns 400 and the job's retry policy ignores it.

resource "google_service_account" "restarter" {
  count        = var.spot_vm ? 1 : 0
  account_id   = "${var.vm_name}-restarter"
  display_name = "Auto-restart job for spot ${var.vm_name}"

  depends_on = [google_project_service.compute]
}

# Scoped to the single instance; cannot start anything else in the project.
resource "google_compute_instance_iam_member" "restarter_admin" {
  count         = var.spot_vm ? 1 : 0
  project       = var.project_id
  zone          = var.zone
  instance_name = google_compute_instance.vm.name
  role          = "roles/compute.instanceAdmin.v1"
  member        = "serviceAccount:${google_service_account.restarter[0].email}"
}

resource "google_cloud_scheduler_job" "restart_vm" {
  count       = var.spot_vm ? 1 : 0
  name        = "${var.vm_name}-auto-restart"
  description = "Starts ${var.vm_name} if preempted."
  schedule    = var.auto_restart_schedule
  region      = var.region
  time_zone   = "Etc/UTC"

  retry_config {
    retry_count = 0
  }

  http_target {
    http_method = "POST"
    uri = format(
      "https://compute.googleapis.com/compute/v1/projects/%s/zones/%s/instances/%s/start",
      var.project_id,
      var.zone,
      google_compute_instance.vm.name,
    )

    oauth_token {
      service_account_email = google_service_account.restarter[0].email
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }

  depends_on = [
    google_project_service.cloudscheduler,
    google_compute_instance_iam_member.restarter_admin,
  ]
}
