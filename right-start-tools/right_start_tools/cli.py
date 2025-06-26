# source: https://aws.amazon.com/blogs/architecture/field-notes-enroll-existing-aws-accounts-into-aws-control-tower/
# file: https://raw.githubusercontent.com/aws-samples/aws-control-tower-reference-architectures/master/customizations/AccountFactory/EnrollAccount/enroll_account.py

import click
from boto3.session import Session
from .cross_account_vpc_tagger import copy_vpc_subnet_tags_cross_account
from right_start_tools.main import Account
from right_start_tools import backend, show, vpc

from .tools import Tools

session = Session()
t = Tools(session)


@click.group()
def cli() -> None:
    """This is a command line tool to get the weather."""
    pass


cli.add_command(vpc.process_vpcs)
cli.add_command(show.show_org_structure)
cli.add_command(backend.gen_tf_backend)

if __name__ == "__main__":
    cli()


@cli.command(
    short_help="Check if the RightStart account baseline is deployed to all accounts."
)
def check_baseline() -> None:
    """Check if the RightStart account baseline is deployed to all accounts."""
    root_id = t.org.get_root_id()
    structure = t.org.get_org_structure(root_id)
    accounts = structure.all_accounts()
    for account in accounts:
        tf_state_bucket_exists = t.check_tf_state_bucket(account)
        if not tf_state_bucket_exists:
            click.echo(f"TF state bucket for account '{account}' does not exist.")


@click.command(
    short_help="Check if 'OrganizationAccountAccessRole' and 'AWSControlTowerExecution' are deployed to all accounts and create them if needed."
)
@click.option("--dry-run", is_flag=True, help="Run without making changes")
def create_roles(dry_run: bool) -> None:
    """Check if the roles are deployed to all accounts."""
    # https://github.com/aws-samples/aws-control-tower-automate-account-creation/blob/master/functions/source/account_create.py
    root_id = t.org.get_root_id()
    structure = t.org.get_org_structure(root_id)
    accounts = structure.all_accounts()

    for account in accounts:
        status = t.check_roles(account)
        try:
            role_to_create = status.role_to_create()
        except ValueError:
            click.echo(
                f"Unable to assume roles for account {account}. "
                "Either roles are missing, there is an issue with the access, "
                "or the account is suspended."
            )
            continue
        if role_to_create:
            if not dry_run:
                click.echo(f"Creating role '{role_to_create}' in account {account}.")
                t.create_admin_role_in_account(
                    account, role_to_create, structure.master_account.id
                )
            else:
                click.echo(f"Role '{role_to_create}' is missing in account {account}.")
        else:
            click.echo(f"Roles are already created in account {account}.")
    if not dry_run:
        click.echo("All set!")


cli.add_command(create_roles)

@click.command(
    short_help="Copy shared VPCs tags"
)
@click.option("--dry-run", is_flag=True, help="Run without making changes")
@click.option(
    "--region", "-r",
    prompt="AWS region where the VPCs live",
    help="AWS region where the VPCs live.",
)
@click.option(
    "--vpc-name", "-v",
    prompt="VPC name to copy tags from",
    help="VPC name to copy tags from.",
)
def copy_vpc_tags(dry_run: bool, region: str, vpc_name: str) -> None:
    """Copy shared VPCs tags to all accounts."""
    root_id = t.org.get_root_id()
    structure = t.org.get_org_structure(root_id)
    accounts = structure.all_accounts()

    network_accounts = [account for account in accounts if "tools-network" in account.name]
    workload_accounts = [account for account in accounts if "workload" in account.name]
    
    # [network-account-name (to copy tags from)] -> [list of workload-account-names (to copy tags to)]
    accounts_to_copy_tags: dict[Account, list[Account]] = {}

    for network_account in network_accounts:
        # by FivexL naming convention:
        # [environment]-[use-case]
        environment = network_account.name.split("-")[0]
        # find all workload accounts that match the environment
        env_workload_accounts = [account for account in workload_accounts if account.name.startswith(environment)]
        accounts_to_copy_tags[network_account] = env_workload_accounts

    for network_account, workload_accounts in accounts_to_copy_tags.items():
        for workload_account in workload_accounts:
            print(f"\n# Copying tags from {network_account} to {workload_account}")
            copy_vpc_subnet_tags_cross_account(
                networking_account_id=network_account.id,
                workloads_account_id=workload_account.id, 
                vpc_name=vpc_name,
                region=region,
                dry_run=dry_run
            )
        

cli.add_command(copy_vpc_tags)
