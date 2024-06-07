import click
from boto3 import Session

from . import main as rst

OU_SYMBOL = click.style("➜", fg="blue")
ACCOUNT_SYMBOL = click.style("•", fg="green")


def show_children(ous: list[rst.ChildOU], indent=0):
    for ou in ous:
        click.echo("  " * indent + f"{OU_SYMBOL} {ou.name} ({ou.id})")
        for account in ou.accounts:
            click.echo(
                "  " * (indent + 2) + f"{ACCOUNT_SYMBOL} {account.name} ({account.id})"
            )
        show_children(ou.ous, indent + 2)


def print_org_structure(structure: rst.OrgStructure):
    click.echo(f"Root: {structure.root_id}")
    click.echo(
        f"{ACCOUNT_SYMBOL} Master Account: {structure.master_account.name} ({structure.master_account.id})"
    )
    show_children(structure.children)


@click.command(short_help="Show the structure of the AWS Organization")
def show_org_structure() -> None:
    """Show the structure of the AWS Organization."""
    session = Session()
    org = rst.Organizations(session.client("organizations"))
    root_id = org.get_root_id()
    structure = org.get_org_structure(root_id)
    print_org_structure(structure)
