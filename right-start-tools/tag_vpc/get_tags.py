import json

import boto3
import create_tags

VPC_ID = ""
REGION = "us-east-1"
VPC_NAME = "apps"  # Necessary to separate name from subnet type, e.g., "apps-db"
VALID_SUBNET_TYPES = [
    "public",
    "private",
    "db",
    "redshift",
    "elasticache",
    "intra",
    "outpost",
]  # subnet types from VPC module
CREATE_TAGS = True  # Set this to True to apply tagging for subnets in the account


def get_subnets_by_vpc_id(vpc_id: str, ec2_client) -> list[dict] | None:  # noqa: ANN001
    try:
        response = ec2_client.describe_subnets(
            Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]
        )
        return response["Subnets"] if "Subnets" in response else None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None


def get_subnet_type_suffix(
    subnet_name: str, valid_subnet_types: list[str]
) -> str | None:
    # default name from module is : <name_that_user_gave_to_vpc>-<subnet_type>-<az_id>
    # So we want to get the second part of the name.
    name_parts = subnet_name.split("-")
    if len(name_parts) >= 3 and name_parts[0] == VPC_NAME:  # noqa: PLR2004
        subnet_type = name_parts[1]
        if subnet_type in valid_subnet_types:
            return subnet_type
    return None


if __name__ == "__main__":
    if not VPC_ID:
        print("Please set VPC_ID variable.")
        exit(1)
    if not VPC_NAME:
        print("Please set VPC_NAME variable.")
        exit(1)
    if CREATE_TAGS:
        print("CREATE_TAGS is set to True. Tags will be created.")
    if not CREATE_TAGS:
        print("CREATE_TAGS is set to False. Tags will not be created.")

    ec2_client = boto3.client("ec2", region_name=REGION)  # type: ignore # noqa: PGH003
    all_tags = {}
    if subnets := get_subnets_by_vpc_id(VPC_ID, ec2_client):
        for subnet in subnets:
            subnet_name = [
                tag["Value"] for tag in subnet["Tags"] if tag["Key"] == "Name"
            ][0]
            if subnet_type := get_subnet_type_suffix(subnet_name, VALID_SUBNET_TYPES):
                tags = {
                    "NamePrefix": f"{VPC_NAME}-",
                    "AvailabilityZoneId": subnet["AvailabilityZoneId"],
                    "Type": subnet_type,
                }
                if CREATE_TAGS:
                    create_tags.create_tag(subnet["SubnetId"], tags, ec2_client)
                    print(
                        f"Next tags were created for {subnet_name}:",
                        json.dumps(tags, indent=4),
                    )
                all_tags[f"{subnet['SubnetId']}"] = tags
            else:
                print(f"Invalid or unexpected name '{subnet_name}'.")
    else:
        print("No subnets found.")
    print("Tags to create in other account:", json.dumps(all_tags, indent=4))
