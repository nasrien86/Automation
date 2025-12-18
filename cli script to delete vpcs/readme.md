📝 Overview


This repository contains a Bash script that automatically deletes default VPCs across a list of non-US AWS regions.
The script is designed to be safe, targeted, and repeatable, ensuring that only the default VPC and its dependent resources are removed without touching production VPCs or US regions.
This is useful for organizations that:
Restrict usage to specific regions
Require cleanup of unused AWS defaults for security/compliance
Maintain consistent global infrastructure standards


🚀 What the Script Does
For each non-US region listed, the script:
Identifies the default VPC (isDefault=true)
Deletes dependent resources inside that VPC:
Internet Gateway (detach + delete)
Subnets
Non-main route tables
Non-default security groups
Deletes the VPC itself
Deletes custom DHCP option sets (only if not default)
All operations are scoped only to the default VPC.


🛡️ What the Script Does NOT Delete
Any VPC in US regions (us-east-1, us-east-2, us-west-1, us-west-2)
Any non-default VPCs
Any resources outside the default VPC
Default SG / main route table (AWS deletes them automatically when VPC is removed)
This makes the script extremely safe to run in environments where multiple VPCs exist.


🌍 Supported Regions
The script targets exactly the following non-US regions:
ca-central-1
eu-central-1
eu-west-1
ap-northeast-2
ap-northeast-3
ap-northeast-1
sa-east-1
ap-southeast-1
ap-southeast-2
ap-south-1
eu-west-2
eu-west-3
eu-north-1


You can modify this array as needed.

