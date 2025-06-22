#!/usr/bin/env python
# gen_tf_backend.py
#
# Generate *one* .tf file containing S3-backend configs
# for every ACTIVE AWS account in the Organization.

from __future__ import annotations

import hashlib
import pathlib
from typing import List, Tuple

import boto3
import click
from mypy_boto3_organizations import OrganizationsClient
from mypy_boto3_sts import STSClient


def get_management_account_id(sts: STSClient) -> str:
    """Return the AWS account ID of the caller (should be the management account)."""
    return sts.get_caller_identity()["Account"]


def list_active_accounts(org: OrganizationsClient) -> List[Tuple[str, str]]:
    """
    Return (account_id, account_name) for every ACTIVE account in the org.
    """
    accounts: List[Tuple[str, str]] = []
    paginator = org.get_paginator("list_accounts")

    for page in paginator.paginate():
        for acct in page["Accounts"]:
            if acct["Status"] == "ACTIVE":
                accounts.append((acct["Id"], acct["Name"]))

    return accounts


def sha1(text: str) -> str:
    """Stable 40-char SHA-1 hex digest used to suffix bucket / table names."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def render_backend_block(region: str, env_hash: str, acct_id: str, acct_name: str) -> str:
    """Return a backend block preceded by an informative comment."""
    return f"""\
# ─────────────────────────────────────────────────────────────────────────────
# Account: {acct_name} ({acct_id})
# ─────────────────────────────────────────────────────────────────────────────
terraform {{
  backend "s3" {{
    bucket         = "terraform-state-{env_hash}"
    key            = "terraform/main/main.tfstate"
    region         = "{region}"
    encrypt        = true
    dynamodb_table = "terraform-state-lock-{env_hash}"
  }}
}}

"""


def write_tf_file(path: pathlib.Path, blocks: List[str]) -> None:
    """Write all backend blocks into a single .tf file."""
    path.write_text("".join(blocks), encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────
@click.command(short_help="Generate one .tf file with backends for all org accounts.")
@click.option(
    "--region",
    "-r",
    help="AWS region where the state buckets live (prompted if omitted).",
)
@click.option(
    "--output-file",
    "-o",
    type=click.Path(dir_okay=False, writable=True, path_type=pathlib.Path),
    default="backend_all_accounts.tf",
    show_default=True,
    help="Filename to write the combined backend blocks into.",
)
def gen_tf_backend(region: str | None, output_file: pathlib.Path) -> None:  # noqa: N802
    """
    Enumerate every ACTIVE account in the AWS Organization and write **all**
    backend blocks—annotated with account *name* and *ID*—into a single file.
    """
    session = boto3.Session()
    sts_client: STSClient = session.client("sts")
    org_client: OrganizationsClient = session.client("organizations")

    if region is None:
        region = click.prompt(
            "AWS region for the backends",
            default=session.region_name or "us-east-1",
            type=str,
        )

    mgmt_id = get_management_account_id(sts_client)
    click.echo(f"Management account: {mgmt_id}")

    accounts = list_active_accounts(org_client)
    click.echo(f"Discovered {len(accounts)} ACTIVE accounts.")

    blocks: List[str] = []
    for acct_id, acct_name in accounts:
        env_hash = sha1(f"{acct_id}-{region}")
        blocks.append(render_backend_block(region, env_hash, acct_id, acct_name))

    write_tf_file(output_file, blocks)
    click.echo(f"✔ Backend snippets written to {output_file}")


if __name__ == "__main__":
    gen_tf_backend()