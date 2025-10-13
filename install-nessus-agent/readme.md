
🧩 AWS Systems Manager Automation: Nessus Agent Deployment

This AWS Systems Manager (SSM) Automation Runbook installs and links the Tenable Nessus Agent across all tagged SSM-managed EC2 instances (both Windows and Linux).
It detects eligible instances automatically, validates OS and architecture support, and performs installation or linking as needed.

🚀 Overview

This runbook:
Scans all EC2 instances managed by AWS Systems Manager (SSM)
Filters for instances that are:
Online in Fleet Manager
Tagged with Nessus: yes
Determines OS flavor and version
Installs the Nessus Agent (if not already installed)
Links the agent to the Tenable/Nessus Manager using your key, host, and port.

🧠 Features
✅ Cross-platform support (Windows & Linux)
✅ Tag-based targeting (Nessus=yes)
✅ Automatic OS detection (RHEL, CentOS, Alma, Rocky, Oracle, Windows Server 2012–2022)
✅ Safe: skips unsupported or offline instances
✅ Idempotent: doesn’t reinstall or re-link if already configured
✅ Works across accounts via AssumeRole


⚙️ Parameters
| Parameter    | Type   | Description                                                           |
| ------------ | ------ | --------------------------------------------------------------------- |
| `AssumeRole` | String | ARN of the IAM role that the Automation will assume during execution. |
| `key`        | String | Nessus Manager linking key.                                           |
| `port`       | String | Port used for linking (typically `8834`).                             |
| `host`       | String | Nessus Manager hostname or IP.                                        |


🪜 Execution Flow

GetOSFlavor
Collects all managed instances
Filters by PingStatus=Online and Tag Nessus=yes
Categorizes into linuxInstances and windowsInstances

InstallNessusAgent_Windows
Installs or links Nessus Agent via PowerShell (AWS-RunPowerShellScript)
Downloads the latest MSI from Tenable
Links to Nessus Manager using provided key, host, and port

InstallNessusAgent_OracleLinux_CentOS_RedHat
Installs or links Nessus Agent via Bash (AWS-RunShellScript)
Auto-detects OS major version (7, 8, 9)
Downloads correct .rpm installer

Starts and enables Nessus service


🛡️ Security Notice

Do not hardcode real keys, hostnames, or ARNs in the YAML file.
Use parameters or AWS Secrets Manager for sensitive data.
Ensure the AssumeRole has the following minimum permissions:
  ssm:DescribeInstanceInformation
  ssm:SendCommand
  ec2:DescribeInstances
  ec2:DescribeTags
