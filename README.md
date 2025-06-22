[![FivexL](https://releases.fivexl.io/fivexlbannergit.jpg)](https://fivexl.io/)

# FivexL RightStart Tools


**Please note!**
This repository is still a work in progress and is subject to change, so please be careful when running it in production environments.

This repository contains a set of tools that can simplify the management of AWS accounts within an AWS Organization.

To use it, please follow the instructions below:

Clone the repository locally.
1. Move to the root directory of the repo
2. `unset AWS_VAULT`
3. `aws-vault exec <profile>`
4. `cd right-start-tools/`       
5. `poetry install`
6. use any command from the list below


If the commands below aren't working for you, please try running them with Poetry by using:
`poetry run rst <command>`

```
Information Commands:
- rst check-baseline
      Check if the RightStart account baseline is deployed to all accounts.

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

> This one requires you to be in the management account with permissions to STS & Organizations.
- rst gen-tf-backend --region ca-central-1
    Generate backend.tf file based on the current AWS environment.

```

If you need to create cross-account tags for VPCs, please refer to the README.md in the tag_vpc directory.

# Weekly review link
- [Review](https://github.com/fivexl/right-start-tools/compare/main@%7B7day%7D...main)
- [Review branch-based review](https://github.com/fivexl/right-start-tools/compare/review...main)
