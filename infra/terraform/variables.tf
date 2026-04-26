variable "project_id" {
  description = "GCP project that hosts the mtg-helper VM."
  type        = string
}

variable "region" {
  description = "GCP region."
  type        = string
  default     = "europe-west1"
}

variable "zone" {
  description = "GCP zone for the VM and data disk."
  type        = string
  default     = "europe-west1-b"
}

variable "vm_name" {
  description = "Compute Engine instance name (also used as firewall target tag)."
  type        = string
  default     = "mtg-helper"
}

variable "machine_type" {
  description = "VM machine type."
  type        = string
  default     = "e2-medium"
}

variable "data_disk_gb" {
  description = "Size in GB of the persistent data disk mounted at /srv/mtg-helper/data."
  type        = number
  default     = 50
}

variable "admin_iam_member" {
  description = "IAM member that receives roles/iap.tunnelResourceAccessor + roles/compute.osLogin (e.g. \"user:you@example.com\")."
  type        = string
}

variable "snapshot_start_time" {
  description = "UTC start window (HH:00) for the daily data-disk snapshot."
  type        = string
  default     = "03:00"
}

variable "snapshot_retention_days" {
  description = "Days to keep auto-created snapshots before deletion."
  type        = number
  default     = 7
}

variable "github_repository" {
  description = "GitHub repository allowed to assume the deployer SA via WIF (format: \"owner/repo\")."
  type        = string
}

variable "github_branch" {
  description = "Branch ref allowed to deploy (e.g. \"main\"). Other refs are denied by the WIF condition."
  type        = string
  default     = "main"
}
