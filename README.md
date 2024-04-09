# FivexL RightStart tools
This repository contains the tools and scripts used by the RightStart team.

```
Commands:
  check-baseline      Check if the RightStart account baseline is deployed to
                      all accounts.
  create-roles        Check if 'OrganizationAccountAccessRole' and
                      'AWSControlTowerExecution' are deployed to all accounts
                      and create them if needed.
  gen-tf-backend      Generate backend.tf file based on current AWS
                      environment.
  process-vpcs        Intended to be used in management account, requires Control Tower or AWSControlTowerExecution role. Will delete all default VPC and internet gateways in all accounts in all regions.
  show-org-structure  Show the structure of the AWS Organization
```