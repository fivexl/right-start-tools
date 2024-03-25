This module adheres to the naming conventions specified at https://registry.terraform.io/modules/terraform-aws-modules/vpc/aws/latest. If subnets are not created using this module, get_tags.py will not generate a 'subnet_type' tag. Consequently, it will not provide output or create tags within the 'Networking account'.

When sharing VPCs across accounts using RAM, it's important to note that tags applied to subnets and route tables are not shared. Consequently, you'll need to apply tags through alternative methods; one manual approach is detailed below.

Utilize `get_tags.py` in the network account to retrieve tags for the subnets. Subsequently, employ `create_tags.py` in the shared account to apply these tags to the subnets within the shared account.

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
`get_tags.py` will generate output like the above. You can then copy and paste this output into the TAGS_TO_CREATE variable within `create_tags.py` and execute create_tags.py in the shared account to apply the tags to the subnets in that account.

