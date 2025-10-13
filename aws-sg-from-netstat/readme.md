
# AWS Security Group Automation from Netstat Excel

## 🧠 Overview
This Python script automates the creation of **AWS Security Groups and rules** based on data extracted from a cleaned Excel netstat report.

It supports:
- Multi-sheet Excel files (`.xlsx`)
- Automatic header mapping (no strict column names)
- IPv4 and IPv6 CIDRs
- Inbound and outbound rules
- Duplicate detection (won’t reapply existing rules)
- Optional descriptions per rule

---

## ⚙️ Requirements

- Python 3.8+
- AWS CLI configured (`aws configure` or `aws sso login`)
- boto3
- pandas
- openpyxl

Install dependencies:
```bash
pip install boto3 pandas openpyxl


📘 Excel Format

Your Excel file should contain the following columns (case-insensitive):

| Type            | IpProtocol | FromPort | ToPort | IpRanges    | Description |
| --------------- | ---------- | -------- | ------ | ----------- | ----------- |
| Inbound/Ingress | TCP        | 80       | 80     | 10.0.0.0/16 | HTTP        |
| Outbound/Egress | UDP        | 53       | 53     | 0.0.0.0/0   | DNS         |
| ...             | ...        | ...      | ...    | ...         | ...         |

📝 Notes:
“Description” is optional.
“IpRanges” may contain multiple entries separated by commas or semicolons.

🚀 Usage

Run the script:
python netstat_to_sg.py

You’ll be prompted for:

Excel file (.xlsx):
VPC ID (e.g., vpc-0123abcd):
Security Group name:
Security Group description:
AWS region (blank = default):
AWS profile (blank = default):


It will:

Parse your Excel file.
Show a plan of rules to be created.
Ask for confirmation (Type 'yes' to apply).
Create the Security Group (if not exists) and add the rules.
