import boto3
import get_tags

TAGS_TO_CREATE = {}  # <------ Copy output from get_tags.py here
VPC_ID = ""  # <------ VPC ID
REGION = "us-east-1"
DRY_RUN = False  # Set this to False to apply tagging for subnets in the account


def create_tag(subnet_id: str, tag_object: dict, ec2_client) -> None:  # noqa: ANN001
    try:
        tags_to_create = [
            {"Key": str(key), "Value": str(value)} for key, value in tag_object.items()
        ]
        ec2_client.create_tags(Resources=[subnet_id], Tags=tags_to_create)
    except Exception as e:
        print(f"An error occurred: {e}")
        return None


if __name__ == "__main__":
    if not VPC_ID:
        print("Please set VPC_ID variable.")
        exit(1)
    if not TAGS_TO_CREATE:
        print("Please set TAGS_TO_CREATE variable.")
        exit(1)

    ec2_client = boto3.client("ec2", region_name=REGION)  # type: ignore # noqa: PGH003
    subnets = get_tags.get_subnets_by_vpc_id(VPC_ID, ec2_client)
    if subnets is not None:
        for subnet in subnets:
            if subnet["SubnetId"] in TAGS_TO_CREATE:
                tags_to_create = TAGS_TO_CREATE[subnet["SubnetId"]]
                tags_to_create["Name"] = (
                    f"{tags_to_create['NamePrefix']}{tags_to_create['Type']}-{subnet['AvailabilityZone']}"
                )
                del tags_to_create['NamePrefix']
                print(f"Tags to create: {tags_to_create}")
                if not DRY_RUN:
                    create_tag(
                        subnet["SubnetId"], tags_to_create, ec2_client
                    )
                    print(f"Tags created for {subnet['SubnetId']}.")
            else:
                print(f"Tags not found for {subnet['SubnetId']}.")
    else:
        print("No subnets found.")
