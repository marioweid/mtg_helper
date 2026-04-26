resource "google_compute_disk" "data" {
  name = "${var.vm_name}-data"
  type = "pd-balanced"
  zone = var.zone
  size = var.data_disk_gb

  depends_on = [google_project_service.compute]
}

resource "google_compute_instance" "vm" {
  name         = var.vm_name
  machine_type = var.machine_type
  zone         = var.zone
  tags         = [var.vm_name]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 20
      type  = "pd-balanced"
    }
  }

  attached_disk {
    source      = google_compute_disk.data.id
    device_name = "data"
  }

  network_interface {
    network = "default"

    access_config {}
  }

  metadata = {
    enable-oslogin = "TRUE"
    startup-script = file("${path.module}/startup-script.sh")
  }

  service_account {
    email  = google_service_account.vm.email
    scopes = ["cloud-platform"]
  }

  depends_on = [
    google_project_service.compute,
    google_project_service.oslogin,
  ]
}
