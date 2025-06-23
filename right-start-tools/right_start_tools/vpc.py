from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import click
from boto3.session import Session
from botocore.exceptions import BotoCoreError, ClientError
from mypy_boto3_ec2 import EC2Client
from mypy_boto3_ec2.service_resource import SecurityGroup, Vpc

from .aws import session
from .constants import CT_EXECUTION_ROLE_NAME
from .tools import Tools

# note: Account factory for Terraform do it like
# [this](https://github.com/aws-ia/terraform-aws-control_tower_account_factory/blob/main/src/aft_lambda/aft_feature_options/aft_delete_default_vpc.py).


class EC2:
    def __init__(self, client: EC2Client) -> None:
        self.client = client

    def get_all_regions_names(self) -> list[str]:
        response = self.client.describe_regions(AllRegions=False)
        return [r["RegionName"] for r in response["Regions"] if r.get("RegionName")]


def get_default_security_group(vpc: Vpc) -> Optional[SecurityGroup]:
    for sg in vpc.security_groups.filter(
        Filters=[{"Name": "group-name", "Values": ["default"]}]
    ):
        if sg.group_name == "default":
            return sg
    return None

def _process_region_for_account(
    account_id: str,
    boto_session: Session,
    region: str,
    destructive: bool,  # True == actually delete; False == dry-run
) -> None:
    ec2_resource = boto_session.resource("ec2", region_name=region)

    for vpc in list(ec2_resource.vpcs.all()):
        if not vpc.is_default:
            continue

        if not destructive:
            click.echo(
                f"[DRY-RUN] Would delete default VPC {vpc.id} "
                f"in {region} for account {account_id}"
            )
            continue

        # Skip if the VPC still has ENIs (common if AWS has recreated resources)
        enis = list(
            ec2_resource.network_interfaces.filter(
                Filters=[{"Name": "vpc-id", "Values": [vpc.id]}]
            )
        )
        if enis:
            click.echo(
                f"{region}: {vpc.id} still has {len(enis)} ENIs – "
                f"first one: {enis[0].description}"
            )
            continue

        # Delete subnets
        for subnet in vpc.subnets.all():
            subnet.delete()
            click.echo(f"Deleted subnet {subnet.id} in {region} ({account_id})")

        # Detach & delete IGWs
        for igw in vpc.internet_gateways.all():
            vpc.detach_internet_gateway(InternetGatewayId=igw.id)
            igw.delete()
            click.echo(f"Deleted IGW {igw.id} in {region} ({account_id})")

        # Finally, delete the VPC
        vpc.delete()
        click.echo(f"Deleted default VPC {vpc.id} in {region} ({account_id})")


# ───────────────────────────────────────────────────────────────────────────────
# Account-level work
# ───────────────────────────────────────────────────────────────────────────────


def _boto_session_for_account(
    tools: Tools,
    account_id: str,
    management_account_id: str,
) -> Optional[Session]:
    """Return a boto3.Session for the given account, or None on error."""
    if account_id == management_account_id:
        # We’re **already** running under credentials for the management account.
        return session

    try:
        creds = tools.sts.assume_role_and_get_credentials(
            account_id, CT_EXECUTION_ROLE_NAME
        )
    except Exception as exc:
        click.echo(f"❌  Can’t assume role in {account_id}: {exc!s}")
        return None

    return Session(
        aws_access_key_id=creds["aws_access_key_id"],
        aws_secret_access_key=creds["aws_secret_access_key"],
        aws_session_token=creds["aws_session_token"],
    )


def _process_account(
    account,
    tools: Tools,
    management_account_id: str,
    destructive: bool,
    region_workers: int,
) -> None:
    boto_sess = _boto_session_for_account(tools, account.id, management_account_id)
    if boto_sess is None:
        return  # already logged

    ec2_client = boto_sess.client("ec2")
    try:
        regions = EC2(ec2_client).get_all_regions_names()
    except (ClientError, BotoCoreError) as exc:
        click.echo(f"❌  Failed to list Regions for {account.id}: {exc!s}")
        return

    with ThreadPoolExecutor(max_workers=region_workers) as reg_pool:
        futures = [
            reg_pool.submit(
                _process_region_for_account,
                account.id,
                boto_sess,
                region,
                destructive,
            )
            for region in regions
        ]
        for fut in as_completed(futures):
            try:
                fut.result()
            except Exception as exc:
                click.echo(f"⚠️  Error in {account.id}: {exc!s}")


# ───────────────────────────────────────────────────────────────────────────────
# CLI
# ───────────────────────────────────────────────────────────────────────────────


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Actually **delete** default VPCs. "
    "Without this flag the script runs in DRY-RUN mode and makes NO changes.",
)
@click.option(
    "--workers",
    type=int,
    default=10,
    metavar="N",
    help="Concurrent threads per level (accounts & regions)",
)
def process_vpcs(force: bool, workers: int) -> None:
    """Delete default VPCs everywhere.

    • **SAFE BY DEFAULT:** Without --force the script only prints what would be deleted.
    • Supply --force to make irreversible changes.
    """

    tools = Tools(session)

    # Who are we? → management/payer account ID
    management_account_id: str = session.client("sts").get_caller_identity()["Account"]

    root_id = tools.org.get_root_id()
    structure = tools.org.get_org_structure(root_id)
    accounts = structure.all_accounts()

    click.echo(f"Mgmt account: {management_account_id}")
    click.echo(f"Total accounts to process: {len(accounts)}")
    if not force:
        click.echo("⚠️  DRY-RUN mode – nothing will be deleted\n")

    with ThreadPoolExecutor(max_workers=workers) as acc_pool:
        acc_futures = [
            acc_pool.submit(
                _process_account,
                acct,
                tools,
                management_account_id,
                destructive=force,
                region_workers=workers,
            )
            for acct in accounts
        ]
        for fut in as_completed(acc_futures):
            try:
                fut.result()
            except Exception as exc:
                click.echo(f"⚠️  Account-level error: {exc!s}")

    click.echo("\n✅  Finished default-VPC cleanup.")


if __name__ == "__main__":
    process_vpcs()
