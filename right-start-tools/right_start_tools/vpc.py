import click
from mypy_boto3_ec2 import EC2Client
from typing import Optional
from mypy_boto3_ec2.service_resource import Vpc, SecurityGroup
from boto3.session import Session

# note: Account factory for Terraform do it like 
# [this](https://github.com/aws-ia/terraform-aws-control_tower_account_factory/blob/main/src/aft_lambda/aft_feature_options/aft_delete_default_vpc.py).

class EC2:
    def __init__(self, client: EC2Client):
        self.client = client
    
    def get_all_regions_names(self) -> list[str]:
        response = self.client.describe_regions()
        regions = []
        for region in response['Regions']:
            if region_name := region.get('RegionName'):
                regions.append(region_name)
        return regions

def get_default_security_group(vpc: Vpc) -> Optional[SecurityGroup]:
    for sg in vpc.security_groups.filter(Filters=[{'Name': 'group-name', 'Values': ['default']}]):
        if sg.group_name == 'default':
            return sg



@click.command(short_help='Process VPCs in all regions.')
@click.option('--dry-run', is_flag=True, help='Run without making changes')
def process_vpcs(
    session: Session,
    dry_run: bool
):
    """Process VPCs in all regions."""
    default_regions_list=["us-east-1", "us-east-2", "us-west-1", "us-west-2"]

    ec2 = EC2(session.client('ec2'))
    regions = ec2.get_all_regions_names()
    click.echo(f"Default Regions - {default_regions_list}")
    click.echo("Dry run" if dry_run else "Processing VPCs...")
    return

    for region in regions:
        ec2_resource = session.resource('ec2', region_name=region)

        # Find all VPCs in the region
        vpcs = list(ec2_resource.vpcs.all())

        for vpc in vpcs:
            default_security_group = get_default_security_group(vpc)

            if not default_security_group:
                continue

            # For default regions, delete ingress and egress rules from the default security group
            if region in default_regions_list:
                # Revoke all ingress rules
                for rule in default_security_group.ip_permissions:
                    if not dry_run:
                        default_security_group.revoke_ingress(IpPermissions=[rule])
                    else:
                        print(f'Would revoke ingress rule {rule} in region {region}')

                # Revoke all egress rules
                for rule in default_security_group.ip_permissions_egress:
                    if not dry_run:
                        default_security_group.revoke_egress(IpPermissions=[rule])
                    else:
                        print(f'Would revoke egress rule {rule} in region {region}')


            # For non-default regions, delete the default VPC if it exists
            else:
                if vpc.is_default:
                    # Delete all subnets
                    for subnet in vpc.subnets.all():
                        if not dry_run:
                            subnet.delete()
                        else:
                            print(f'Would delete subnet {subnet.id} in region {region}')

                    # Detach and delete all internet gateways
                    for igw in vpc.internet_gateways.all():
                        if not dry_run:
                            vpc.detach_internet_gateway(InternetGatewayId=igw.id)
                            igw.delete()
                        else:
                            print(f'Would detach and delete internet gateway {igw.id} in region {region}')

                    # Delete the default VPC
                    if not dry_run:
                        vpc.delete()
                    else:
                        print(f'Would delete default VPC {vpc.id} in region {region}')

