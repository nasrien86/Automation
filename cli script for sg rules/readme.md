
This Python script automates the creation of AWS Security Groups (SGs) from Excel files.
It converts an .xlsx spreadsheet containing inbound/outbound rule definitions into a ready-to-run Bash deployment script that uses the AWS CLI to create or update security groups.

🚀 Features

Reads Excel workbook of cleaned netstat report
Automatically detects and normalizes header names (even if messy or inconsistent)
Supports multiple header synonyms (e.g., Direction or Type, CIDR or Source)
Handles multiple CIDR blocks per cell (10.0.0.0/24; 10.0.1.0/24)
Supports both IPv4 and IPv6 ranges

Generates Bash script:
Applies all ingress and egress rules
Auto-generates rule descriptions if missing
Skips invalid/empty rows gracefully

📦 Requirements

Python 3.8+
Packages:
  pip install pandas openpyxl
AWS CLI configured (either via profile or environment)

Each sheet in the workbook represents a set of rules (e.g., “Ingress”, “Egress”).
Headers can vary slightly — the script auto-detects them using synonyms.

| Type     | Protocol | FromPort | ToPort | IpRanges    | Description |
| -------- | -------- | -------- | ------ | ----------- | ----------- |
| Inbound  | TCP      | 22       | 22     | 10.0.0.0/24 | SSH access  |
| Outbound | ALL      |          |        | 0.0.0.0/0   | Allow all   |
