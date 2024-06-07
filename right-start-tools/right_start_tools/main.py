import json
from dataclasses import dataclass
from typing import Callable, Literal

import boto3
from mypy_boto3_iam import IAMClient
from mypy_boto3_organizations import OrganizationsClient
from mypy_boto3_organizations.type_defs import AccountTypeDef, OrganizationalUnitTypeDef
from mypy_boto3_sts import STSClient


@dataclass
class Parent:
    id: str
    type: Literal["ORGANIZATIONAL_UNIT", "ROOT"]

    @staticmethod
    def from_dict(d: dict) -> "Parent":
        return Parent(d["Id"], d["Type"])  # type: ignore


@dataclass
class Account:
    id: str
    arn: str
    name: str
    email: str

    @staticmethod
    def from_dict(d: AccountTypeDef) -> "Account":
        return Account(
            id=d["Id"],  # type: ignore
            arn=d["Arn"],  # type: ignore
            name=d["Name"],  # type: ignore
            email=d["Email"],  # type: ignore
        )

    def __str__(self) -> str:
        return f"{self.name} ({self.id})"

    def __repr__(self) -> str:
        return f"{self.name} ({self.id})"


@dataclass
class OU:
    id: str
    arn: str
    name: str

    @staticmethod
    def from_dict(d: OrganizationalUnitTypeDef) -> "OU":
        return OU(
            id=d["Id"],  # type: ignore
            arn=d["Arn"],  # type: ignore
            name=d["Name"],  # type: ignore
        )

    def __str__(self) -> str:
        return f"OU: {self.name} ({self.id})"

    def __repr__(self) -> str:
        return f"OU: {self.name} ({self.id})"


@dataclass
class ChildOU(OU):
    accounts: list[Account]
    ous: list["ChildOU"]

    def all_accounts(self) -> list[Account]:
        return ChildOU._all_accounts(self)

    @staticmethod
    def _all_accounts(ou: "ChildOU") -> list[Account]:
        accounts = []
        for account in ou.accounts:
            accounts.append(account)
        for child_ou in ou.ous:
            accounts.extend(ChildOU._all_accounts(child_ou))
        return accounts


@dataclass
class OrgStructure:
    root_id: str
    children: list[ChildOU]
    master_account: Account

    def all_accounts(self) -> list[Account]:
        accounts = []
        for child in self.children:
            accounts.extend(child.all_accounts())
        return accounts


class Organizations:
    def __init__(self, client: OrganizationsClient):
        self.client = client

    def execute_on_account_in_org_root(self, account: Account, action: Callable):
        """
        Moves the given account to the root of the organization, executes the provided action on the account,
        and then moves the account back to its original parent.

        Args:
            account (rst.Account): The account to be moved and acted upon.
            action (Callable[[rst.Account], None]): The action to be executed on the account.

        Raises:
            Exception: If an error occurs during the execution of the action.

        Returns:
            None
        """
        parent_id = self.get_parent(account.id).id
        root_id = self.get_root_id()
        self.move_account(account.id, parent_id, root_id)
        try:
            action(account)
        except Exception as e:
            raise e
        finally:
            self.move_account(account.id, root_id, parent_id)

    def move_account(self, id: str, source: str, destination: str):
        """Move an AWS account from source parent to destination parent."""
        response = self.client.move_account(
            AccountId=id, SourceParentId=source, DestinationParentId=destination
        )
        return response

    def get_parent(self, child_id) -> Parent:
        # https://docs.aws.amazon.com/organizations/latest/APIReference/API_ListParents.html
        # In the current release, a child can have only a single parent.
        response = self.client.list_parents(ChildId=child_id)
        return Parent.from_dict(response["Parents"][0])  # type: ignore

    def get_root_id(self) -> str:
        return self.client.list_roots()["Roots"][0]["Id"]  # type: ignore

    def list_accounts(self, parent_id) -> list[Account]:
        """
        Lists accounts under a given parent ID (OU).
        """
        accounts = []
        paginator = self.client.get_paginator("list_accounts_for_parent")
        for account_page in paginator.paginate(ParentId=parent_id):
            for account in account_page["Accounts"]:
                accounts.append(Account.from_dict(account))
        return accounts

    def list_ous(self, parent_id) -> list[OU]:
        """
        Lists organizational units (OUs) under a given parent ID (OU).
        """
        ous = []
        paginator = self.client.get_paginator("list_organizational_units_for_parent")
        for ou_page in paginator.paginate(ParentId=parent_id):
            for ou in ou_page["OrganizationalUnits"]:
                ous.append(OU.from_dict(ou))
        return ous

    def get_org_structure(self, root_id: str) -> OrgStructure:
        master_account_id = self.client.describe_organization()["Organization"]["MasterAccountId"]  # type: ignore
        master_account = Account.from_dict(
            self.client.describe_account(AccountId=master_account_id)["Account"]
        )
        children = self._get_children(root_id)
        return OrgStructure(root_id, children, master_account)

    def _get_children(self, parent_id) -> list[ChildOU]:
        children = []
        for ou in self.list_ous(parent_id):
            accounts = self.list_accounts(ou.id)
            ous = self._get_children(ou.id)
            children.append(ChildOU(ou.id, ou.arn, ou.name, accounts, ous))
        return children


class STS:
    def __init__(self, client: STSClient):
        self.client = client

    def assume_role_and_get_credentials(
        self, account_id: str, role_name: str, session_name: str = "AssumeRoleSession"
    ):
        assumed_role_object = self.client.assume_role(
            RoleArn=f"arn:aws:iam::{account_id}:role/{role_name}",
            RoleSessionName=session_name,
        )
        credentials = assumed_role_object["Credentials"]
        return {
            "aws_access_key_id": credentials["AccessKeyId"],
            "aws_secret_access_key": credentials["SecretAccessKey"],
            "aws_session_token": credentials["SessionToken"],
        }


class IAM:
    def __init__(self, client: IAMClient):
        self.client = client

    @staticmethod
    def from_credentials(credentials: dict) -> "IAM":
        return IAM(boto3.client("iam", **credentials))

    def create_admin_role(self, management_account_id: str, role_name: str):
        self.client.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {
                                "AWS": f"arn:aws:iam::{management_account_id}:root"
                            },
                            "Action": "sts:AssumeRole",
                            "Condition": {},
                        }
                    ],
                }
            ),
            Description="Role for AWS Control Tower Execution",
        )
        self.client.attach_role_policy(
            RoleName=role_name, PolicyArn="arn:aws:iam::aws:policy/AdministratorAccess"
        )

    def is_role_exists(self, role_name: str) -> bool:
        try:
            self.client.get_role(RoleName=role_name)
            return True
        except self.client.exceptions.NoSuchEntityException:
            return False
        except Exception as e:
            raise e
