output "vm_name" {
  value = google_compute_instance.vm.name
}

output "vm_zone" {
  value = google_compute_instance.vm.zone
}

output "vm_external_ip" {
  description = "Ephemeral external IP (rotates on stop/start)."
  value       = google_compute_instance.vm.network_interface[0].access_config[0].nat_ip
}

output "ssh_command" {
  value = "gcloud compute ssh ${google_compute_instance.vm.name} --zone=${google_compute_instance.vm.zone} --tunnel-through-iap"
}

output "snapshot_policy" {
  description = "Resource policy attached to the data disk; lists auto snapshots via gcloud compute snapshots list."
  value       = google_compute_resource_policy.daily_snapshot.name
}

output "deployer_service_account" {
  description = "Email of the SA the GitHub Actions workflow impersonates."
  value       = google_service_account.deployer.email
}

output "workload_identity_provider" {
  description = "Full provider resource name to put in the GitHub workflow's `workload_identity_provider` input."
  value       = google_iam_workload_identity_pool_provider.github.name
}
