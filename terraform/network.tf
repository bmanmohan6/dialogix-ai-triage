# 1. Create the VPC (The main secure network bubble)
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16" # Gives us 65,000 internal IP addresses
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "dialogix-vpc"
  }
}

# 2. Create Subnet 1 (in Availability Zone A)
resource "aws_subnet" "public_1" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = "us-east-1a"
  map_public_ip_on_launch = true # Automatically gives our servers public IPs so they can reach the internet

  tags = {
    Name                     = "dialogix-public-1"
    "kubernetes.io/role/elb" = "1" # This tag is strictly required by EKS to create load balancers
  }
}

# 3. Create Subnet 2 (in Availability Zone B)
resource "aws_subnet" "public_2" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.2.0/24"
  availability_zone       = "us-east-1b"
  map_public_ip_on_launch = true

  tags = {
    Name                     = "dialogix-public-2"
    "kubernetes.io/role/elb" = "1"
  }
}

# 4. Create an Internet Gateway (The "Front Door" to the internet)
resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "dialogix-igw"
  }
}

# 5. Create a Route Table (The GPS directions for network traffic)
resource "aws_route_table" "public_rt" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0" # "0.0.0.0/0" means "any IP on the internet"
    gateway_id = aws_internet_gateway.igw.id
  }

  tags = {
    Name = "dialogix-public-rt"
  }
}

# 6. Associate the Route Table with our Subnets
resource "aws_route_table_association" "public_1_assoc" {
  subnet_id      = aws_subnet.public_1.id
  route_table_id = aws_route_table.public_rt.id
}

resource "aws_route_table_association" "public_2_assoc" {
  subnet_id      = aws_subnet.public_2.id
  route_table_id = aws_route_table.public_rt.id
}