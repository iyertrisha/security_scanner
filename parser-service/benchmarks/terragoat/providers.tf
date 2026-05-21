
provider "aws" {
  profile = var.profile
  region  = var.region
}

provider "aws" {
  alias      = "plain_text_access_keys_provider"
  region     = "us-west-1"
  access_key = "PLACEHOLDER_ACCESS_KEY"
  secret_key = "PLACEHOLDER_SECRET_KEY"
}

terraform {
  backend "s3" {
    encrypt = true
  }
}
