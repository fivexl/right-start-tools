It’s a simple Python script with no dependencies other than `boto3`. This script allows you to list your AWS Organization accounts and automatically generate AWS SSO `[profile ...]` blocks that can be appended to your `~/.aws/config`. You can customize things like SSO start URL, AWS region, and permission sets directly in the script’s configuration section.

# How to generate profiles for AWS SSO config
1. Install boto3
2. Get into the management account with access to the AWS Organizations service. Using aws-vault.
3. Go to the `generate_account_requests.py`, and specify: `sso_start_url(sso page url)`, `sso_region`, `region` and permission_set_names (if more than one, all profile names will be postfixed with the permission set name).
4. Run the script
5. Copy printed output to your .aws/config file
