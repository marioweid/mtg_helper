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

