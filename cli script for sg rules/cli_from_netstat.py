#!/usr/bin/env python3
import re
from pathlib import Path
import pandas as pd

# ---------- helpers ----------
def esc(s: str) -> str:
    return (str(s) if s is not None else "").replace('"', r'\"')

def smart_split_ranges(cell: str):
    s = ("" if cell is None else str(cell)).strip()
    out, buf, depth = [], [], 0
    for ch in s:
        if ch == "(":
            depth += 1; buf.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1); buf.append(ch)
        elif ch in [",", ";"] and depth == 0:
            part = "".join(buf).strip()
            if part: out.append(part)
            buf = []
        else:
            buf.append(ch)
    part = "".join(buf).strip()
    if part: out.append(part)
    return out

def norm(s):
    """Normalize a header/token: strip, fix NBSP, lowercase, remove non-alnum."""
    return re.sub(r"[^a-z0-9]+", "", str(s).replace("\u00A0", " ").strip().lower())

# Accepted synonyms (normalized)
SYNONYMS = {
    "type": {"type", "direction"},
    "ipprotocol": {"ipprotocol", "protocol"},
    "fromport": {"fromport", "srcport", "startport"},
    "toport": {"toport", "dstport", "endport"},
    "ipranges": {"ipranges", "cidr", "cidrs", "source", "sources", "cidrblocks"},
    "description": {"description", "desc", "notes", "comment"},
}

def map_headers(df):
    """Return a dict of canonical->actual column names. Auto-detect header row if needed."""
    # First try current header row
    mapping = try_map(df.columns)
    if mapping: 
        return mapping, df.reset_index(drop=True)

    # Try to find the header row within first ~10 rows
    for hdr_row in range(min(10, len(df))):
        candidate = df.iloc[hdr_row].tolist()
        mapping = try_map(candidate)
        if mapping:
            # Use this row as header
            new_df = df.iloc[hdr_row+1:].copy()
            new_df.columns = candidate
            return map_headers(new_df)  # re-run once to normalize names
    # If we get here, print what we saw to help debugging
    raise KeyError(f"Could not find required headers. Saw columns: {list(df.columns)}")

def try_map(cols):
    """Try to map a list of column labels to required canonical names."""
    seen = {norm(c): c for c in cols}
    out = {}
    for canon, syns in SYNONYMS.items():
        found = None
        for s in syns:
            if s in seen:
                found = seen[s]; break
        if found:
            out[canon] = found
        else:
            # 'description' is optional; others are required
            if canon != "description":
                return None
    return out

def iter_rows(df, colmap):
    """Yield normalized rows with required fields present."""
    c = colmap
    for _, r in df.iterrows():
        t  = ("" if pd.isna(r[c["type"]]) else str(r[c["type"]])).strip()
        if not t:
            continue
        proto = ("" if pd.isna(r[c["ipprotocol"]]) else str(r[c["ipprotocol"]])).strip().lower()

        # Ports may come in as floats; coerce to int-like strings where possible
        def to_str(v):
            if pd.isna(v) or v == "": return ""
            try:
                fv = float(v)
                if fv.is_integer(): return str(int(fv))
            except Exception:
                pass
            return str(v).strip()

        fp = to_str(r[c["fromport"]])
        tp = to_str(r[c["toport"]])

        ranges_cell = ("" if pd.isna(r[c["ipranges"]]) else str(r[c["ipranges"]])).strip()
        if not ranges_cell:
            continue

        desc = ""
        if "description" in c:
            dv = r[c["description"]]
            if not pd.isna(dv):
                desc = str(dv).strip()
        if not desc:
            desc = f"{proto.upper()} {fp or '*'}-{tp or '*'}"

        yield {
            "Type": t,
            "Proto": proto,
            "FromPort": fp,
            "ToPort": tp,
            "IpRanges": ranges_cell,
            "Description": desc,
        }

# ---------- main ----------
def main():
    xlsx_path = input("Enter Excel (.xlsx) filename: ").strip()
    vpc_id    = input("Enter VPC ID: ").strip()
    sg_name   = input("Enter Security Group name: ").strip()
    sg_desc   = input("Enter SG description: ").strip() or "Created from Excel"
    region    = input("Enter AWS region (blank=default): ").strip()
    profile   = input("Enter AWS profile (blank=default): ").strip()
    out_file  = input("Output bash script filename [deploy_sg.sh]: ").strip() or "deploy_sg.sh"

    region_flag  = f" --region {region}" if region else ""
    profile_flag = f" --profile {profile}" if profile else ""

    # Read all sheets
    wb = pd.read_excel(xlsx_path, sheet_name=None, dtype=object)
    if not wb:
        raise RuntimeError("No sheets found in workbook")

    lines = []
    lines += [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        "",
        f'VPC_ID="{vpc_id}"',
        f'SG_NAME="{sg_name}"',
        f'SG_DESC="{esc(sg_desc)}"',
        "",
        # Find or create SG
        'SG_ID=$(aws ec2 describe-security-groups'
        f'{profile_flag}{region_flag} '
        '--filters "Name=vpc-id,Values=$VPC_ID" "Name=group-name,Values=$SG_NAME" '
        "--query 'SecurityGroups[0].GroupId' --output text || true)",
        'if [[ "$SG_ID" == "None" || -z "${SG_ID}" ]]; then',
        '  echo "Creating security group..."',
        '  SG_ID=$(aws ec2 create-security-group'
        f'{profile_flag}{region_flag} '
        ' --group-name "$SG_NAME" --description "$SG_DESC" --vpc-id "$VPC_ID" '
        ' --tag-specifications "ResourceType=security-group,Tags=[{Key=Name,Value=$SG_NAME}]" '
        " --query 'GroupId' --output text)",
        '  echo "Created SG: $SG_ID"',
        'else',
        '  echo "Reusing SG: $SG_ID"',
        'fi',
        "",
    ]

    ingress_ct = 0
    egress_ct  = 0

    for sheet_name, df in wb.items():
        if df is None or df.empty:
            continue

        # Auto-detect/normalize headers for this sheet
        colmap, df_norm = map_headers(df)
        lines.append(f'echo "Processing sheet: {esc(sheet_name)}"')

        for row in iter_rows(df_norm, colmap):
            t, proto, fp, tp, ranges, desc = (
                row["Type"].lower(),
                row["Proto"],
                row["FromPort"],
                row["ToPort"],
                row["IpRanges"],
                row["Description"],
            )

            tokens = smart_split_ranges(ranges)
            cidrs = [re.sub(r"\(.*\)$", "", tok).strip() for tok in tokens if tok.strip()]
            if not cidrs:
                continue

            parts = [f"IpProtocol={proto}"]
            if proto in ("tcp", "udp", "6", "17"):
                if fp: parts.append(f"FromPort={fp}")
                if tp: parts.append(f"ToPort={tp}")
            elif proto in ("icmp", "1"):
                parts.append(f"FromPort={fp or -1}")
                parts.append(f"ToPort={tp or -1}")
            # else -1/all protocols => no ports

            ip4 = [f'{{CidrIp={c},Description="{esc(desc)}"}}' for c in cidrs if ":" not in c]
            ip6 = [f'{{CidrIpv6={c},Description="{esc(desc)}"}}' for c in cidrs if ":" in c]
            if ip4: parts.append(f'IpRanges=[{",".join(ip4)}]')
            if ip6: parts.append(f'Ipv6Ranges=[{",".join(ip6)}]')

            ip_permissions = ",".join(parts)

            if t.startswith("inbound") or "ingress" in t:
                ingress_ct += 1
                lines.append(
                    "aws ec2 authorize-security-group-ingress"
                    f"{profile_flag}{region_flag} "
                    '--group-id "$SG_ID" '
                    f"--ip-permissions '{ip_permissions}'"
                )
            elif t.startswith("outbound") or "egress" in t:
                egress_ct += 1
                lines.append(
                    "aws ec2 authorize-security-group-egress"
                    f"{profile_flag}{region_flag} "
                    '--group-id "$SG_ID" '
                    f"--ip-permissions '{ip_permissions}'"
                )
            else:
                lines.append(f'echo "WARN: Unknown Type on sheet {esc(sheet_name)}; row skipped" 1>&2')

        lines.append("")

    lines.append(f'echo "Prepared {ingress_ct} ingress and {egress_ct} egress rule block(s) for $SG_NAME ($SG_ID)"')

    Path(out_file).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Generated {out_file}. Run it with: bash {out_file}")

if __name__ == "__main__":
    main()

