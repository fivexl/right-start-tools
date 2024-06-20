from typing import Optional

import click
from boto3.session import Session
from mypy_boto3_ec2 import EC2Client
from mypy_boto3_ec2.service_resource import SecurityGroup, Vpc

from .aws import session
from .constants import CT_EXECUTION_ROLE_NAME
from .tools import Tools

# note: Account factory for Terraform do it like
# [this](https://github.com/aws-ia/terraform-aws-control_tower_account_factory/blob/main/src/aft_lambda/aft_feature_options/aft_delete_default_vpc.py).


class EC2:
    def __init__(self, client: EC2Client):
        self.client = client

    def get_all_regions_names(self) -> list[str]:
        response = self.client.describe_regions()
        regions = []
        for region in response["Regions"]:
            if region_name := region.get("RegionName"):
                regions.append(region_name)
        return regions


def get_default_security_group(vpc: Vpc) -> Optional[SecurityGroup]:
    for sg in vpc.security_groups.filter(
        Filters=[{"Name": "group-name", "Values": ["default"]}]
    ):
        if sg.group_name == "default":
            return sg


@click.command(short_help="Process VPCs in all regions.")
@click.option("--dry-run", is_flag=True, help="Run without making changes")
def process_vpcs(dry_run: bool):
    """Process VPCs in all accounts/regions."""
    t = Tools(session)

    root_id = t.org.get_root_id()
    structure = t.org.get_org_structure(root_id)
    accounts = structure.all_accounts()
    click.echo("Dry run" if dry_run else "Processing VPCs...")
    for account in accounts:
        try:
            click.echo(f"Processing account {account}...")
            try:
                credentials = t.sts.assume_role_and_get_credentials(
                    account.id, CT_EXECUTION_ROLE_NAME
                )

            except Exception as e:
                click.echo(
                    f"Unable to assume roles for account {account}. "
                    "Either roles are missing, there is an issue with the access, "
                    "or the account is suspended."
                    f"error: {e}"
                )

            acc_session = Session(
                aws_access_key_id=credentials["aws_access_key_id"],
                aws_secret_access_key=credentials["aws_secret_access_key"],
                aws_session_token=credentials["aws_session_token"],
            )

            ec2 = EC2(acc_session.client("ec2"))
            regions = ec2.get_all_regions_names()

            for region in regions:
                ec2_resource = acc_session.resource("ec2", region_name=region)

                # Find all VPCs in the region
                vpcs = list(ec2_resource.vpcs.all())

                for vpc in vpcs:
                    if vpc.is_default:
                        # Delete all subnets
                        for subnet in vpc.subnets.all():
                            if not dry_run:
                                subnet.delete()
                            else:
                                click.echo(
                                    f"Would delete subnet {subnet.id} in region {region}"
                                )
                        # Detach and delete all internet gateways
                        for igw in vpc.internet_gateways.all():
                            if not dry_run:
                                vpc.detach_internet_gateway(InternetGatewayId=igw.id)
                                igw.delete()
                            else:
                                click.echo(
                                    f"Would detach and delete internet gateway {igw.id} in region {region}"
                                )
                        # Delete the default VPC
                        if not dry_run:
                            vpc.delete()
                        else:
                            print(
                                f"Would delete default VPC {vpc.id} in region {region}"
                            )
        except Exception as e:
            print(f"Failed to process account {account}: {e}")
            continue
