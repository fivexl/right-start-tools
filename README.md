# FivexL RightStart Tools
**Please note!**
This repository is still a work in progress and is subject to change, so please be careful when running it in production environments.

This repository contains a set of tools that can simplify the management of AWS accounts within an AWS Organization.

To use it, please follow the instructions below:

Clone the repository locally.
- Navigate to the required directory: cd right-start-tools
- Install dependencies using Poetry: `poetry install`
- Log in to AWS: `aws-vault exec <profile>` / `aws configure`
- Run the tool you need: `rst <command>`


```
Information Commands:
- rst check-baseline
      Check if the RightStart account baseline is deployed to all accounts.

- rst gen-tf-backend
    Generate backend.tf file based on the current AWS environment.

- rst show-org-structure
    Show the tree structure of the AWS Organization
```

```
Commands:
- rst create-roles
      Check if 'OrganizationAccountAccessRole' and 'AWSControlTowerExecution' are deployed to all accounts and create them if needed.

- rst process-vpcs
    Intended to be used in the management account, requires Control Tower or AWSControlTowerExecution role. Will delete all default VPCs and internet gateways in all accounts in all regions.
    Note! This process will go through all accounts and regions and delete default VPCs and IGWs. This process may take a while (~3-4 minutes per account).
```

If you need to create cross-account tags for VPCs, please refer to the README.md in the tag_vpc directory.
