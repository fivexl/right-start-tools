This module adheres to the naming conventions specified at https://registry.terraform.io/modules/terraform-aws-modules/vpc/aws/latest. If subnets are not created using this module, get_tags.py will not generate a 'subnet_type' tag. Consequently, it will not provide output or create tags within the 'Networking account'.

When sharing VPCs across accounts using RAM, it's important to note that tags applied to subnets and route tables are not shared. Consequently, you'll need to apply tags through alternative methods; one manual approach is detailed below.

Utilize `get_tags.py` in the network account to retrieve tags for the subnets. Subsequently, employ `create_tags.py` in the shared account to apply these tags to the subnets within the shared account.

The scripts create_tags.py and get_tags.py are not part of the RST tools CLI for now. They are intended to be run directly as Python files.

To run scripts you would need to have boto3. We reccomend to use poetry to install deps. Clone repo, get to dir with `pyproject.toml`
and run `poetry install`.

If it would not work, try to use CloudShell in AWS console, it should have boto3 pre-installed, to run script, paste it into CLI like that:
```bash
python <<EOF
# Place python script there, just like plain text, and continue with steps below. 
EOF
```
Get Tags from VPC using get_tags.py:
- Login into the networking account.
- Provide the VPC_ID variable at the top of the file.
- Ensure that the region is correct.
- Ensure that VPC_NAME matches your VPC name.
- Run the Python file.
Note: The script will create tags in the networking account, which means you may get resources not created by Terraform, and Terraform might try to destroy your tags. This is fine, you can run Terraform in the networking account, and nothing will break.
Output from get_tags.py:
- After running get_tags.py, the script will output a dictionary {} with tags.
- Copy the output of the script.


Run create_tags.py in the Workloads Account:
- Login into the workloads account.
- Paste the output from the previous script into TAGS_TO_CREATE.
- Provide the VPC_ID variable at the top of the file.
- Ensure that the region is correct.
- Set DRY_RUN to true and run the script to see and confirm the output.
- Set DRY_RUN to false and run the script again.
- Done.


Looks like this script needs to be polished... 

Below is an example of the tags that the code would generate:
```python
TAGS_TO_CREATE= {
    "subnet-11111111111111111": {"AvailabilityZoneId": "use1-az2", "Type": "db", "Name": "apps-db-us-east-1a"},
    "subnet-22222222222222222": {"AvailabilityZoneId": "use1-az4", "Type": "public", "Name": "apps-public-us-east-1b"},
    "subnet-33333333333333333": {"AvailabilityZoneId": "use1-az2", "Type": "public", "Name": "apps-public-us-east-1a"},
    "subnet-44444444444444444": {"AvailabilityZoneId": "use1-az4", "Type": "private", "Name": "apps-private-us-east-1b"},
    "subnet-55555555555555555": {"AvailabilityZoneId": "use1-az4", "Type": "db", "Name": "apps-db-us-east-1b"},
    "subnet-66666666666666666": {"AvailabilityZoneId": "use1-az2", "Type": "private", "Name": "apps-private-us-east-1a"},
}
```

