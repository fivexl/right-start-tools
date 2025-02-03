#!/usr/bin/env python3

import boto3

def main():
    # -------------------------------------------------------------------------------------
    # Hardcoded Configuration - Modify these values as needed
    # -------------------------------------------------------------------------------------
    sso_start_url = "" # sample: https://something.awsapps.com/start/
    sso_region = "us-east-1"
    region = "us-east-1"
    prefix = ""
    postfix = ""
    permission_set_names = ["AdministratorAccess"]
    # Add more if needed, if > 1, permission set name will be appended to profile name as a postfix
    # -------------------------------------------------------------------------------------

    # Create a client for AWS Organizations
    org_client = boto3.client("organizations")

    # Paginate to list all accounts
    accounts = []
    next_token = None
    while True:
        if next_token:
            response = org_client.list_accounts(NextToken=next_token)
        else:
            response = org_client.list_accounts()
        accounts.extend(response["Accounts"])
        next_token = response.get("NextToken")
        if not next_token:
            break

    # Collect all config lines in a list so we can print and also write to file
    output_lines = []

    for account in accounts:
        account_id = account["Id"]
        # Convert the account name to something safe for AWS config profile names
        # e.g. "Development Tools" -> "development-tools"
        account_name = account["Name"].lower().replace(" ", "-")

        # Generate one profile per permission set
        for pset in permission_set_names:
            if len(permission_set_names) > 1:
                profile_name = f"{prefix}{account_name}{postfix}-{pset}"
            else:
                profile_name = f"{prefix}{account_name}{postfix}"

            output_lines.extend(
                (
                    f"[profile {profile_name}]",
                    f"sso_start_url = {sso_start_url}",
                    f"sso_region = {sso_region}",
                    f"sso_account_id = {account_id}",
                    f"sso_role_name = {pset}",
                    f"region = {region}",
                    "output = json",
                    "",
                )
            )
    # Print the lines to stdout
    for line in output_lines:
        print(line)

    # Also write them to a file named "config" (no extension)
    with open("config", "w") as f:
        for line in output_lines:
            f.write(line + "\n")

if __name__ == "__main__":
    main()
