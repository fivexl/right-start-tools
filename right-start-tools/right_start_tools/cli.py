# source: https://aws.amazon.com/blogs/architecture/field-notes-enroll-existing-aws-accounts-into-aws-control-tower/
# file: https://raw.githubusercontent.com/aws-samples/aws-control-tower-reference-architectures/master/customizations/AccountFactory/EnrollAccount/enroll_account.py

import click
from boto3.session import Session

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
