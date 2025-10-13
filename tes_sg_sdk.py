#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re, sys
from ipaddress import ip_network
from typing import Dict, List, Tuple

import pandas as pd
import boto3
from botocore.exceptions import ClientError

# ===== header normalization =====
def norm_hdr(value) -> str:
    if value is None:
        s = ""
    elif isinstance(value, float):
        if pd.isna(value): s = ""
        else: s = str(int(value)) if float(value).is_integer() else str(value)
    else:
        s = str(value)
    s = s.replace("\u00A0", " ").strip().lower()
    return re.sub(r"[^a-z0-9]+", "", s)

SYNONYMS = {
    "type": {"type","direction"},
    "ipprotocol": {"ipprotocol","protocol"},
    "fromport": {"fromport","srcport","startport"},
    "toport": {"toport","dstport","endport"},
    "ipranges": {"ipranges","cidr","cidrs","source","sources","cidrblocks"},
    "description": {"description","desc","notes","comment"},
}

def try_map(cols) -> Dict[str, str] | None:
    seen = {}
    for c in cols:
        k = norm_hdr(c)
        if not k: continue
        seen.setdefault(k, c)
    out = {}
    for canon, syns in SYNONYMS.items():
        found = None
        for s in syns:
            if s in seen: found = seen[s]; break
        if found: out[canon] = found
        else:
            if canon != "description": return None
    return out

def map_headers(df: pd.DataFrame):
    m = try_map(df.columns)
    if m: return m, df.reset_index(drop=True)
    for hdr_row in range(min(10, len(df))):
        candidate = df.iloc[hdr_row].tolist()
        m = try_map(candidate)
        if m:
            new_df = df.iloc[hdr_row+1:].copy()
            new_df.columns = candidate
            m2 = try_map(new_df.columns)
            if m2: return m2, new_df.reset_index(drop=True)
    raise KeyError(f"Could not find required headers. Saw columns: {list(df.columns)}")

# ===== row helpers =====
def smart_split_ranges(cell: str) -> List[str]:
    s = ("" if cell is None else str(cell)).strip()
    out, buf, depth = [], [], 0
    for ch in s:
        if ch == "(": depth += 1
        elif ch == ")": depth = max(0, depth-1)
        if ch in [",",";"] and depth == 0:
            part = "".join(buf).strip()
            if part: out.append(part)
            buf = []
        else: buf.append(ch)
    part = "".join(buf).strip()
    if part: out.append(part)
    return out

def coerce_port(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)): return ""
    s = str(v).strip()
    try:
        f = float(s)
        if f.is_integer(): return str(int(f))
    except Exception:
        pass
    return s

def validate_cidr(c: str) -> None:
    ip_network(c, strict=False)

def canonical_rule_key(proto: str, fp: str, tp: str, cidr: str, direction: str) -> Tuple:
    fp_i = None if fp == "" else int(fp)
    tp_i = None if tp == "" else int(tp)
    return (direction, proto.lower(), fp_i, tp_i, cidr)

# ===== AWS helpers =====
def get_existing_sg(ec2, vpc_id: str, name: str):
    r = ec2.describe_security_groups(Filters=[{"Name":"vpc-id","Values":[vpc_id]},
                                              {"Name":"group-name","Values":[name]}])
    if r["SecurityGroups"]:
        sg = r["SecurityGroups"][0]
        return sg["GroupId"]
    return None

def create_sg(ec2, vpc_id: str, name: str, desc: str) -> str:
    res = ec2.create_security_group(GroupName=name, Description=desc, VpcId=vpc_id)
    return res["GroupId"]

def fetch_existing_rules(ec2, sg_id: str) -> set:
    if not sg_id:
        return set()
    resp = ec2.describe_security_group_rules(Filters=[{"Name":"group-id","Values":[sg_id]}])
    keys = set()
    for r in resp.get("SecurityGroupRules", []):
        direction = "ingress" if r.get("IsEgress") is False else "egress"
        proto = r.get("IpProtocol")
        fp = r.get("FromPort"); tp = r.get("ToPort")
        c4 = r.get("CidrIpv4"); c6 = r.get("CidrIpv6")
        if c4:
            keys.add(canonical_rule_key(proto, str(fp) if fp is not None else "", str(tp) if tp is not None else "", c4, direction))
        if c6:
            keys.add(canonical_rule_key(proto, str(fp) if fp is not None else "", str(tp) if tp is not None else "", c6, direction))
    return keys

# ===== main =====
def main():
    print("== Netstat Excel → AWS Security Group (plan → apply) ==")
    xlsx = input("Excel file (.xlsx): ").strip()
    vpc  = input("VPC ID (e.g., vpc-0123abcd): ").strip()
    name = input("Security Group name: ").strip()
    desc = input("Security Group description: ").strip() or "Created from Excel"
    region  = input("AWS region (blank = default): ").strip() or None
    profile = input("AWS profile (blank = default): ").strip() or None

    session = boto3.session.Session(region_name=region, profile_name=profile)
    ec2 = session.client("ec2")

    wb = pd.read_excel(xlsx, sheet_name=None, dtype=object)
    if not wb:
        print("No sheets found in workbook.", file=sys.stderr); sys.exit(1)

    # DO NOT create SG yet. Only detect existence so we can show a plan.
    existing_sg_id = get_existing_sg(ec2, vpc, name)
    will_create_sg = existing_sg_id is None
    sg_id_for_lookup = existing_sg_id  # None if it doesn't exist yet

    if will_create_sg:
        print(f"Target SG: {name} (will be created) in {vpc}")
        existing_rules = set()
    else:
        print(f"Target SG: {name} ({existing_sg_id}) in {vpc}")
        existing_rules = fetch_existing_rules(ec2, existing_sg_id)

    to_add_ing: List[Dict] = []
    to_add_egr: List[Dict] = []
    planned: List[Tuple] = []

    for sheet, df in wb.items():
        if df is None or df.empty: continue
        try:
            colmap, df = map_headers(df)
        except KeyError as e:
            print(f"ERROR: {e} on sheet '{sheet}'", file=sys.stderr); sys.exit(2)

        for _, row in df.iterrows():
            raw_type = row.get(colmap["type"])
            t = "" if raw_type is None or (isinstance(raw_type, float) and pd.isna(raw_type)) else str(raw_type).strip()
            if not t: continue
            tl = t.lower()
            if tl.startswith("inbound") or "ingress" in tl: direction = "ingress"
            elif tl.startswith("outbound") or "egress" in tl: direction = "egress"
            else: continue

            raw_proto = row.get(colmap["ipprotocol"])
            proto = "" if raw_proto is None or (isinstance(raw_proto, float) and pd.isna(raw_proto)) else str(raw_proto).strip().lower()
            fp = coerce_port(row.get(colmap["fromport"]))
            tp = coerce_port(row.get(colmap["toport"]))

            raw_ranges = row.get(colmap["ipranges"])
            ranges_cell = "" if raw_ranges is None or (isinstance(raw_ranges, float) and pd.isna(raw_ranges)) else str(raw_ranges).strip()

            desc_val = ""
            if "description" in colmap:
                d = row.get(colmap["description"])
                if d is not None and not (isinstance(d, float) and pd.isna(d)):
                    desc_val = str(d).strip()
            #if not desc_val:
            #    desc_val = f"{proto.upper()} {fp or '*'}-{tp or '*'}"

            if not ranges_cell: continue

            tokens = smart_split_ranges(ranges_cell)
            cidrs = [re.sub(r"\(.*\)$","", tok).strip() for tok in tokens if tok.strip()]
            if not cidrs: continue

            if proto in ("tcp","udp","6","17"):
                if fp == "" or tp == "":
                    print(f"WARN: sheet '{sheet}' missing ports for {proto}; skipping row"); continue
            elif proto in ("icmp","1"):
                if fp == "" and tp == "": fp = tp = "-1"

            perm = {"IpProtocol": proto, "IpRanges": [], "Ipv6Ranges": [], "UserIdGroupPairs": []}
            if proto in ("tcp","udp","6","17","icmp","1"):
                if fp != "": perm["FromPort"] = int(fp)
                if tp != "": perm["ToPort"]  = int(tp)

            for c in cidrs:
                try:
                    validate_cidr(c)
                except Exception as e:
                    print(f"ERROR: invalid CIDR '{c}' on sheet '{sheet}': {e}", file=sys.stderr); sys.exit(3)
                key = canonical_rule_key(proto, fp, tp, c, direction)
                if key in existing_rules:
                    continue
                entry = {}
                if desc_val:
                     entry["Description"] = desc_val[:255]
                if ":" in c:
                    entry["CidrIpv6"] = c
                    perm["Ipv6Ranges"].append(entry)
                else:
                    entry["CidrIp"] = c
                    perm["IpRanges"].append(entry)


            if perm["IpRanges"] or perm["Ipv6Ranges"]:
                planned.append((direction, proto, fp, tp,
                                [x.get("CidrIp") for x in perm["IpRanges"]] + [x.get("CidrIpv6") for x in perm["Ipv6Ranges"]],
                                desc_val))
                if direction == "ingress": to_add_ing.append(perm)
                else: to_add_egr.append(perm)

    # ---- PLAN ----
    if not planned and not will_create_sg:
        print("Nothing to add: all rules already exist.")
        return

    print("\nPlan:")
    if will_create_sg:
        print(f"  - Create Security Group '{name}' in VPC {vpc} (description: '{desc}')")
    if planned:
        print("  - Add rule blocks:")
        for d, proto, fp, tp, cidrs, desc_val in planned:
            ports = f"{fp}-{tp}" if fp and tp else "*"
            print(f"      [{d}] {proto} {ports}  {', '.join(cidrs)}  # {desc_val}")

    ans = input("\nProceed? Type 'yes' to apply, anything else to abort: ").strip().lower()
    if ans not in ("y", "yes"):
        print("Aborted. No changes made.")
        return

    # ---- APPLY ----
    # Create SG only after confirmation
    if will_create_sg:
        sg_id = create_sg(ec2, vpc, name, desc)
        print(f"Created SG: {sg_id}")
    else:
        sg_id = existing_sg_id

    if to_add_ing:
        try:
            ec2.authorize_security_group_ingress(GroupId=sg_id, IpPermissions=to_add_ing)
            print(f"Added {len(to_add_ing)} ingress permission block(s).")
        except ClientError as e:
            if e.response["Error"]["Code"] == "InvalidPermission.Duplicate":
                print("Some ingress rules were duplicates; skipped.")
            else:
                raise

    if to_add_egr:
        try:
            ec2.authorize_security_group_egress(GroupId=sg_id, IpPermissions=to_add_egr)
            print(f"Added {len(to_add_egr)} egress permission block(s).")
        except ClientError as e:
            if e.response["Error"]["Code"] == "InvalidPermission.Duplicate":
                print("Some egress rules were duplicates; skipped.")
            else:
                raise

    print("Done.")

if __name__ == "__main__":
    main()
