#!/usr/bin/env python
# gen_tf_backend.py
#
# Generate *one* .tf file containing S3-backend configs
# for every ACTIVE AWS account in the Organization.

from __future__ import annotations

import hashlib
import pathlib
from typing import List

import boto3
import click
from mypy_boto3_organizations import OrganizationsClient
from mypy_boto3_sts import STSClient


def get_management_account_id(sts: STSClient) -> str:
    """Return the AWS account ID for the caller (should be the management account)."""
    return sts.get_caller_identity()["Account"]


def list_active_account_ids(org: OrganizationsClient) -> List[str]:
    """Return all ACTIVE account IDs in the org."""
    account_ids: List[str] = []
    for page in org.get_paginator("list_accounts").paginate():
        for acct in page["Accounts"]:
            if acct["Status"] == "ACTIVE":
                account_ids.append(acct["Id"])
    return account_ids


def sha1(text: str) -> str:
    """SHA-1 hash as 40-char hex string (stable bucket suffix)."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def render_backend_block(region: str, env_hash: str, acct_id: str) -> str:
    """Return one backend block, prefixed with a helpful comment."""
    return f"""\
# ---------------------------------------------------------------------------
# Account: {acct_id}
# ---------------------------------------------------------------------------
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


def write_single_tf_file(output_path: pathlib.Path, blocks: List[str]) -> None:
    """Concatenate all backend blocks into one .tf file."""
    output_path.write_text("".join(blocks), encoding="utf-8")


# ---------------------------------------------------------------------------#
# CLI
# ---------------------------------------------------------------------------#


@click.command(short_help="Generate one .tf file with backends for all org accounts.")
@click.option(
    "--region",
    "-r",
    help="AWS region where the state buckets live (will prompt if omitted).",
)
@click.option(
    "--output-file",
    "-o",
    type=click.Path(dir_okay=False, writable=True, path_type=pathlib.Path),
    default="backend_all_accounts.tf",
    show_default=True,
    help="Filename to write all backend blocks into.",
)
def gen_tf_backend(region: str | None, output_file: pathlib.Path) -> None:  # noqa: N802
    """
    Enumerate every ACTIVE account in the AWS Organization and write **all**
    S3-backend blocks into a single Terraform file.
    """
    sess = boto3.Session()
    sts_client: STSClient = sess.client("sts")
    org_client: OrganizationsClient = sess.client("organizations")

    if not region:
        default_region = sess.region_name or "us-east-1"
        region = click.prompt(
            "Enter AWS region for the backends", default=default_region, type=str
        )

    mgmt_id = get_management_account_id(sts_client)
    click.echo(f"Managing account: {mgmt_id}")

    acct_ids = list_active_account_ids(org_client)
    click.echo(f"Found {len(acct_ids)} ACTIVE accounts…")

    backend_blocks: List[str] = []
    for acct_id in acct_ids:
        env_hash = sha1(f"{acct_id}-{region}")
        backend_blocks.append(render_backend_block(region, env_hash, acct_id))

    write_single_tf_file(output_file, backend_blocks)
    click.echo(f"✔ All backend blocks written to {output_file}")


if __name__ == "__main__":
    gen_tf_backend()