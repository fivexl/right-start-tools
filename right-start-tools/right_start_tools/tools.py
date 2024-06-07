from dataclasses import dataclass
from typing import Optional

import click
from boto3.session import Session

from right_start_tools import backend

from . import main as rst
from .constants import CT_EXECUTION_ROLE_NAME, ORG_ACCESS_ROLE_NAME


@dataclass
class RolesStatus:
    org_access: bool
    ct_execution: bool

    def role_to_create(self) -> Optional[str]:
        if self.org_access is False and self.ct_execution is False:
            raise ValueError(
                "Both 'OrganizationAccountAccessRole' and 'AWSControlTowerExecution' are missing."
            )
        elif self.org_access is False:
            return ORG_ACCESS_ROLE_NAME
        elif self.ct_execution is False:
            return CT_EXECUTION_ROLE_NAME
        else:
            return None


class Tools:
    def __init__(self, session: Session):
        self.session = session
        self.org = rst.Organizations(session.client("organizations"))  # type: ignore
        self.sts = rst.STS(session.client("sts"))  # type: ignore
        self.iam = rst.IAM(session.client("iam"))  # type: ignore

    def create_admin_role_in_account(
        self, account: rst.Account, role_to_create: str, master_account_id: str
    ):
        if role_to_create == ORG_ACCESS_ROLE_NAME:
            role_name = CT_EXECUTION_ROLE_NAME
        elif role_to_create == CT_EXECUTION_ROLE_NAME:
            role_name = ORG_ACCESS_ROLE_NAME

        credentials = self.sts.assume_role_and_get_credentials(account.id, role_name)
        iam = rst.IAM.from_credentials(credentials)

        if iam.is_role_exists(role_to_create):
            return

        iam.create_admin_role(master_account_id, role_to_create)

    def try_to_assume_and_ask_to_create_role(
        self,
        account: rst.Account,
        role_name: str,
        master_account_id: str,
        move_to_root: bool = False,
    ):
        if role_name == ORG_ACCESS_ROLE_NAME:
            create_role_name = CT_EXECUTION_ROLE_NAME
        elif role_name == CT_EXECUTION_ROLE_NAME:
            create_role_name = ORG_ACCESS_ROLE_NAME
        else:
            raise ValueError(f"Unknown role name: {role_name}")

        try:
            credentials = self.sts.assume_role_and_get_credentials(
                account.id, role_name
            )
            iam = rst.IAM.from_credentials(credentials)

            if iam.is_role_exists(create_role_name):
                click.echo(
                    f"Role `{create_role_name}` already exists in account '{account.id}'."
                )
                return

            if click.confirm(
                f"Create role `{create_role_name}` in account {account.id}?"
            ):
                iam.create_admin_role(master_account_id, create_role_name)
                click.echo("Done!")
            else:
                click.echo("You are a coward!")

        except self.sts.client.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "AccessDenied":
                # if we failed to assume the role, that means that
                # we can create it using other role
                click.echo(
                    f"Failed to assume role `{role_name}` in account '{account.id}': Access Denied"
                )
                print(e.response["Error"])
                error_message = e.response["Error"]["Message"]
                if "with an explicit deny in a service control policy" in error_message:
                    click.echo(
                        f"Account '{account.id}' has an SCP that denies access to the role `{role_name}`."
                    )
                    if click.confirm(
                        f"Move account '{account.id}' to the root and try again?"
                    ):
                        parent_id = self.org.get_parent(account.id).id
                        root_id = self.org.get_root_id()
                        self.org.move_account(account.id, parent_id, root_id)
                        click.echo(f"Account '{account.id}' moved to the root.")
                        try:
                            self.try_to_assume_and_ask_to_create_role(
                                account, role_name, master_account_id
                            )
                        except Exception as e:
                            click.echo(f"Error: {e}")
                        self.org.move_account(account.id, root_id, parent_id)
                        click.echo(
                            f"Account '{account.id}' moved back to '{parent_id}'."
                        )
                        return
                else:
                    raise e

                role_name, create_role_name = create_role_name, role_name
                self.try_to_assume_and_ask_to_create_role(
                    account, role_name, master_account_id
                )

    def try_to_assume_and_ask_to_create_role_v2(
        self,
        account: rst.Account,
        role_name: str,
        master_account_id: str,
        move_to_root: bool = False,
    ):
        if role_name == ORG_ACCESS_ROLE_NAME:
            name_of_role_to_create = CT_EXECUTION_ROLE_NAME
        elif role_name == CT_EXECUTION_ROLE_NAME:
            name_of_role_to_create = ORG_ACCESS_ROLE_NAME
        else:
            raise ValueError(f"Unknown role name: {role_name}")

        try:
            credentials = self.sts.assume_role_and_get_credentials(
                account.id, role_name
            )
            iam = rst.IAM.from_credentials(credentials)

            if iam.is_role_exists(name_of_role_to_create):
                click.echo(
                    f"Role `{name_of_role_to_create}` already exists in account '{account.id}'."
                )
                return

            if click.confirm(
                f"Create role `{name_of_role_to_create}` in account {account.id}?"
            ):
                iam.create_admin_role(master_account_id, name_of_role_to_create)
                click.echo("Done!")
            else:
                click.echo("You are a coward!")

        except self.sts.client.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "AccessDenied":
                click.echo(
                    f"Failed to assume role `{role_name}` in account '{account.id}': Access Denied"
                )

                error_message = e.response["Error"]["Message"]
                if "with an explicit deny in a service control policy" in error_message:

                    click.echo(
                        f"Account '{account.id}' has an SCP that denies access to the role `{role_name}`."
                    )
                    if click.confirm(
                        f"Move account '{account.id}' to the root and try again?"
                    ):

                        def action(account):
                            return self.try_to_assume_and_ask_to_create_role(
                                account, role_name, master_account_id
                            )

                        self.org.execute_on_account_in_org_root(account, action)

                else:
                    raise e

                role_name, name_of_role_to_create = name_of_role_to_create, role_name
                self.try_to_assume_and_ask_to_create_role(
                    account, role_name, master_account_id
                )

    def check_roles(
        self,
        account: rst.Account,
    ) -> RolesStatus:
        def _check_role(role_name: str) -> bool:
            try:
                self.sts.assume_role_and_get_credentials(account.id, role_name)
                return True
            except self.sts.client.exceptions.ClientError as e:
                if e.response["Error"]["Code"] == "AccessDenied":
                    return False
                else:
                    raise e

        return RolesStatus(
            org_access=_check_role(ORG_ACCESS_ROLE_NAME),
            ct_execution=_check_role(CT_EXECUTION_ROLE_NAME),
        )

    def check_tf_state_bucket(self, account: rst.Account) -> bool:
        try:
            credentials = self.sts.assume_role_and_get_credentials(
                account.id, ORG_ACCESS_ROLE_NAME
            )
        except Exception as e:
            click.echo(
                f"Failed to assume role `{ORG_ACCESS_ROLE_NAME}` in account '{account.id}': {e}"
            )
            return False

        session = Session(**credentials)  # type: ignore
        sts = session.client("sts")
        s3 = session.client("s3")

        aws_account_id = backend.get_aws_account_id(sts)
        region = session.region_name
        env_id = backend.hash_environment_id(f"{aws_account_id}-{region}")
        bucket_name = f"terraform-state-{env_id}"

        # find the bucket
        try:
            s3.head_bucket(Bucket=bucket_name)
            return True
        except s3.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            else:
                raise e
