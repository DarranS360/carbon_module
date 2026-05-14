terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "eu-west-1"
}

data "aws_ami" "amazon_linux" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }
}

resource "aws_instance" "web" {
  ami           = data.aws_ami.amazon_linux.id
  instance_type = "t3.medium"

  tags = {
    Name    = "carbon-cost-example"
    Project = "carbon-cost-module"
  }
}

resource "aws_ebs_volume" "data" {
  availability_zone = "eu-west-1a"
  size              = 100
  type              = "gp3"

  tags = {
    Name    = "carbon-cost-example-data"
    Project = "carbon-cost-module"
  }
}

resource "aws_volume_attachment" "data" {
  device_name = "/dev/xvdf"
  volume_id   = aws_ebs_volume.data.id
  instance_id = aws_instance.web.id
}

resource "aws_instance" "web-2" {
  ami           = data.aws_ami.amazon_linux.id
  instance_type = "t3.large"

  tags = {
    Name    = "carbon-cost-example-2"
    Project = "carbon-cost-module"
  }
}

resource "aws_ebs_volume" "data-2" {
  availability_zone = "eu-west-1a"
  size              = 100
  type              = "gp3"

  tags = {
    Name    = "carbon-cost-example-data-2"
    Project = "carbon-cost-module"
  }
}

resource "aws_volume_attachment" "data-2" {
  device_name = "/dev/xvdf"
  volume_id   = aws_ebs_volume.data-2.id
  instance_id = aws_instance.web-2.id
}