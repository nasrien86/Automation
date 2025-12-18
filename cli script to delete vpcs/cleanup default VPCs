clean_default_vpc() {
  REGION="$1"
  VPC_ID="$2"

  echo ">>> Cleaning default VPC $VPC_ID in $REGION"

  # Capture DHCP options set ID
  DHCP_ID=$(aws ec2 describe-vpcs \
    --region "$REGION" \
    --vpc-ids "$VPC_ID" \
    --query 'Vpcs[0].DhcpOptionsId' \
    --output text)

  echo "  DHCP options set: $DHCP_ID"

  # 1. Detach + delete Internet Gateway
  IGW_ID=$(aws ec2 describe-internet-gateways \
    --region "$REGION" \
    --filters Name=attachment.vpc-id,Values="$VPC_ID" \
    --query 'InternetGateways[0].InternetGatewayId' \
    --output text)

  if [ -n "$IGW_ID" ] && [ "$IGW_ID" != "None" ]; then
    echo "  Detaching & Deleting IGW $IGW_ID"
    aws ec2 detach-internet-gateway --internet-gateway-id "$IGW_ID" --vpc-id "$VPC_ID" --region "$REGION"
    aws ec2 delete-internet-gateway --internet-gateway-id "$IGW_ID" --region "$REGION"
  fi

  # 2. Delete subnets
  SUBNET_IDS=$(aws ec2 describe-subnets \
    --region "$REGION" \
    --filters Name=vpc-id,Values="$VPC_ID" \
    --query 'Subnets[].SubnetId' \
    --output text)

  for SUBNET_ID in $SUBNET_IDS; do
    echo "  Deleting Subnet $SUBNET_ID"
    aws ec2 delete-subnet --subnet-id "$SUBNET_ID" --region "$REGION"
  done

  # 3. Delete non-main route tables
  RTB_IDS=$(aws ec2 describe-route-tables \
    --region "$REGION" \
    --filters Name=vpc-id,Values="$VPC_ID" \
    --query 'RouteTables[].RouteTableId' \
    --output text)

  for RTB_ID in $RTB_IDS; do
    IS_MAIN=$(aws ec2 describe-route-tables \
      --region "$REGION" \
      --route-table-ids "$RTB_ID" \
      --query 'RouteTables[0].Associations[?Main==`true`]' \
      --output text)

    if [ -z "$IS_MAIN" ]; then
      echo "  Deleting Route Table $RTB_ID"
      aws ec2 delete-route-table --route-table-id "$RTB_ID" --region "$REGION"
    else
      echo "  Skipping main route table $RTB_ID"
    fi
  done

  # 4. Delete non-default security groups
  SG_IDS=$(aws ec2 describe-security-groups \
    --region "$REGION" \
    --filters Name=vpc-id,Values="$VPC_ID" \
    --query 'SecurityGroups[?GroupName!=`default`].GroupId' \
    --output text)

  for SG_ID in $SG_IDS; do
    echo "  Deleting Security Group $SG_ID"
    aws ec2 delete-security-group --group-id "$SG_ID" --region "$REGION"
  done

  # 5. Delete the VPC itself
  echo "  Deleting VPC $VPC_ID"
  aws ec2 delete-vpc --vpc-id "$VPC_ID" --region "$REGION"

  # 6. Delete DHCP options (ONLY if custom)
  if [ -n "$DHCP_ID" ] && [ "$DHCP_ID" != "default" ]; then
    echo "  Deleting custom DHCP options set $DHCP_ID"
    aws ec2 delete-dhcp-options --dhcp-options-id "$DHCP_ID" --region "$REGION"
  fi

  echo ">>> Default VPC $VPC_ID cleanup complete."
}

# Add your regions
REGIONS=("ca-central-1" "eu-central-1" "eu-west-1" "ap-northeast-2" "ap-northeast-3" "ap-northeast-1" "sa-east-1" "ap-southeast-1" "ap-southeast-2" "ap-south-1" "eu-west-2" "eu-west-3" "eu-north-1")

for REGION in "${REGIONS[@]}"; do
  echo "=== Region: $REGION ==="
  VPC_ID=$(aws ec2 describe-vpcs \
    --region "$REGION" \
    --filters "Name=isDefault,Values=true" \
    --query 'Vpcs[0].VpcId' \
    --output text)

  if [ "$VPC_ID" = "None" ] || [ -z "$VPC_ID" ]; then
    echo "  No default VPC in $REGION, skipping."
    continue
  fi

  echo "  Found default VPC: $VPC_ID"
  clean_default_vpc "$REGION" "$VPC_ID"
done
