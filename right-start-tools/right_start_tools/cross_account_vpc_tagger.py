"""
Cross-account VPC subnet tagging functions.

This module provides functions to:
1. Assume roles in different AWS accounts
2. Extract subnet tags from a networking account
3. Apply those tags to subnets in a workloads account

Usage:
    copy_vpc_subnet_tags_cross_account(
        networking_account_id="123456789012",
        workloads_account_id="987654321098",
        vpc_id="vpc-1234567890abcdef0",
        vpc_name="apps",
        region="us-east-1"
    )
"""
from typing import Dict, List, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError


VALID_SUBNET_TYPES = [
    "public",
    "private",
    "db",
    "intra",
]


def assume_role(account_id: str, role_name: str = "AWSControlTowerExecution", session_name: str = "CrossAccountVPCTagger") -> boto3.Session:
    """
    Assume a role in another AWS account and return a session.
    
    Args:
        account_id: The AWS account ID to assume role in
        role_name: The name of the role to assume (default: AWSControlTowerExecution)
        session_name: The session name for the assumed role
        
    Returns:
        boto3.Session: A session with the assumed role credentials
        
    Raises:
        ClientError: If role assumption fails
    """
    try:
        sts_client = boto3.client("sts")
        role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"
        
        response = sts_client.assume_role(
            RoleArn=role_arn,
            RoleSessionName=session_name
        )
        
        credentials = response["Credentials"]
        
        return boto3.Session(
            aws_access_key_id=credentials["AccessKeyId"],
            aws_secret_access_key=credentials["SecretAccessKey"],
            aws_session_token=credentials["SessionToken"]
        )
    except (ClientError, BotoCoreError) as e:
        raise ClientError(
            error_response={"Error": {"Code": "RoleAssumptionFailed", "Message": str(e)}},
            operation_name="assume_role"
        ) from e


def get_subnets_by_vpc_id(vpc_id: str, ec2_client) -> Optional[List[Dict]]:
    """
    Get all subnets for a given VPC ID.
    
    Args:
        vpc_id: The VPC ID to get subnets for
        ec2_client: The boto3 EC2 client
        
    Returns:
        List of subnet dictionaries or None if error occurs
    """
    try:
        response = ec2_client.describe_subnets(
            Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]
        )
        return response.get("Subnets")
    except (ClientError, BotoCoreError) as e:
        print(f"Error getting subnets for VPC {vpc_id}: {e}")
        return None


def get_subnet_type_from_name(subnet_name: str, vpc_name: str, valid_subnet_types: List[str]) -> Optional[str]:
    """
    Extract subnet type from subnet name following terraform-aws-modules/vpc naming convention.
    
    Expected format: <vpc_name>-<subnet_type>-<az_id>
    
    Args:
        subnet_name: The name of the subnet
        vpc_name: The VPC name prefix
        valid_subnet_types: List of valid subnet types
        
    Returns:
        The subnet type if valid, None otherwise
    """
    name_parts = subnet_name.split("-")
    if len(name_parts) >= 3 and name_parts[0] == vpc_name:
        subnet_type = name_parts[1]
        if subnet_type in valid_subnet_types:
            return subnet_type
    return None


def extract_subnet_tags_from_networking_account(
    networking_account_id: str,
    vpc_id: str,
    vpc_name: str,
    region: str = "us-east-1",
    role_name: str = "AWSControlTowerExecution"
) -> Dict[str, Dict[str, str]]:
    """
    Extract subnet tags from the networking account.
    
    Args:
        networking_account_id: AWS account ID of the networking account
        vpc_id: The VPC ID to extract tags from
        vpc_name: The VPC name used for tag generation
        region: AWS region (default: us-east-1)
        role_name: IAM role name to assume (default: AWSControlTowerExecution)
        
    Returns:
        Dictionary mapping subnet IDs to their tag dictionaries
        
    Raises:
        ClientError: If role assumption or AWS API calls fail
    """
    session = assume_role(networking_account_id, role_name)
    ec2_client = session.client("ec2", region_name=region)
    
    subnet_tags = {}
    subnets = get_subnets_by_vpc_id(vpc_id, ec2_client)
    
    if not subnets:
        print(f"No subnets found for VPC {vpc_id} in networking account {networking_account_id}")
        return subnet_tags
    
    for subnet in subnets:
        # Get subnet name from tags
        subnet_name = None
        for tag in subnet.get("Tags", []):
            if tag["Key"] == "Name":
                subnet_name = tag["Value"]
                break
        
        if not subnet_name:
            print(f"No Name tag found for subnet {subnet['SubnetId']}")
            continue
            
        subnet_type = get_subnet_type_from_name(subnet_name, vpc_name, VALID_SUBNET_TYPES)
        
        if subnet_type:
            tags = {
                "NamePrefix": f"{vpc_name}-",
                "AvailabilityZoneId": subnet["AvailabilityZoneId"],
                "Type": subnet_type,
            }
            subnet_tags[subnet["SubnetId"]] = tags
            print(f"Extracted tags for {subnet_name}: {tags}")
        else:
            print(f"Invalid or unexpected subnet name format: '{subnet_name}'")
    
    return subnet_tags


def apply_tags_to_subnet(subnet_id: str, tags: Dict[str, str], ec2_client) -> bool:
    """
    Apply tags to a specific subnet.
    
    Args:
        subnet_id: The subnet ID to tag
        tags: Dictionary of tags to apply
        ec2_client: The boto3 EC2 client
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Convert tags dict to AWS tags format
        aws_tags = [
            {"Key": str(key), "Value": str(value)} 
            for key, value in tags.items()
        ]
        
        ec2_client.create_tags(
            Resources=[subnet_id],
            Tags=aws_tags
        )
        return True
    except (ClientError, BotoCoreError) as e:
        print(f"Error applying tags to subnet {subnet_id}: {e}")
        return False


def apply_subnet_tags_to_workloads_account(
    workloads_account_id: str,
    vpc_id: str,
    subnet_tags: Dict[str, Dict[str, str]],
    region: str = "us-east-1",
    role_name: str = "AWSControlTowerExecution",
    dry_run: bool = True
) -> Dict[str, bool]:
    """
    Apply subnet tags to the workloads account.
    
    Args:
        workloads_account_id: AWS account ID of the workloads account
        vpc_id: The VPC ID in the workloads account
        subnet_tags: Dictionary mapping subnet IDs to their tag dictionaries
        region: AWS region (default: us-east-1)
        role_name: IAM role name to assume (default: AWSControlTowerExecution)
        dry_run: If True, only print what would be done (default: True)
        
    Returns:
        Dictionary mapping subnet IDs to success status (True/False)
        
    Raises:
        ClientError: If role assumption or AWS API calls fail
    """
    session = assume_role(workloads_account_id, role_name)
    ec2_client = session.client("ec2", region_name=region)
    
    # Get subnets in workloads account
    subnets = get_subnets_by_vpc_id(vpc_id, ec2_client)
    if not subnets:
        print(f"No subnets found for VPC {vpc_id} in workloads account {workloads_account_id}")
        return {}
    
    results = {}
    workloads_subnet_ids = {subnet["SubnetId"] for subnet in subnets}
    
    for subnet_id, tags in subnet_tags.items():
        if subnet_id not in workloads_subnet_ids:
            print(f"Subnet {subnet_id} not found in workloads account - skipping")
            results[subnet_id] = False
            continue
            
        # Generate final tags
        final_tags = tags.copy()
        
        # Find the subnet to get its AZ for the Name tag
        subnet_az = None
        for subnet in subnets:
            if subnet["SubnetId"] == subnet_id:
                subnet_az = subnet["AvailabilityZone"]
                break
        
        if subnet_az:
            final_tags["Name"] = f"{final_tags['NamePrefix']}{final_tags['Type']}-{subnet_az}"
            del final_tags["NamePrefix"]
            
            if dry_run:
                print(f"DRY RUN - Would apply tags to {subnet_id}: {final_tags}")
                results[subnet_id] = True
            else:
                success = apply_tags_to_subnet(subnet_id, final_tags, ec2_client)
                if success:
                    print(f"Successfully applied tags to {subnet_id}: {final_tags}")
                results[subnet_id] = success
        else:
            print(f"Could not find availability zone for subnet {subnet_id}")
            results[subnet_id] = False
    
    return results

def get_vpc_id_by_name(session: boto3.Session, vpc_name: str, region: str) -> str:
    ec2_client = session.client("ec2", region_name=region)
    response = ec2_client.describe_vpcs(
        Filters=[{"Name": "tag:Name", "Values": [vpc_name]}]
    )
    return response["Vpcs"][0]["VpcId"]


def copy_vpc_subnet_tags_cross_account(
    networking_account_id: str,
    workloads_account_id: str,
    vpc_name: str,
    region: str = "us-east-1",
    role_name: str = "AWSControlTowerExecution",
    dry_run: bool = True
) -> Dict[str, bool]:
    """
    Main function to copy VPC subnet tags from networking account to workloads account.
    
    Args:
        networking_account_id: AWS account ID where the VPC tags are defined
        workloads_account_id: AWS account ID where tags should be applied
        vpc_id: The VPC ID (should exist in both accounts if using RAM sharing)
        vpc_name: The VPC name used for tag generation
        region: AWS region (default: us-east-1)
        role_name: IAM role name to assume in both accounts (default: AWSControlTowerExecution)
        dry_run: If True, only print what would be done (default: True)
        
    Returns:
        Dictionary mapping subnet IDs to success status (True/False)
        
    Raises:
        ClientError: If role assumption or AWS API calls fail
    """
    print(f"Starting cross-account VPC subnet tag copy...")
    print(f"Networking Account: {networking_account_id}")
    print(f"Workloads Account: {workloads_account_id}")
    print(f"VPC Name: {vpc_name}")
    print(f"Region: {region}")
    print(f"Dry Run: {dry_run}")
    print("-" * 50)

    session = assume_role(networking_account_id, role_name)
    vpc_id = get_vpc_id_by_name(session, vpc_name, region)
    
    # Step 1: Extract tags from networking account
    print("Step 1: Extracting subnet tags from networking account...")
    subnet_tags = extract_subnet_tags_from_networking_account(
        networking_account_id=networking_account_id,
        vpc_id=vpc_id,
        vpc_name=vpc_name,
        region=region,
        role_name=role_name
    )
    
    if not subnet_tags:
        print("No valid subnet tags found in networking account")
        return {}
    
    print(f"Found tags for {len(subnet_tags)} subnets")
    print("-" * 50)
    
    # Step 2: Apply tags to workloads account
    print("Step 2: Applying subnet tags to workloads account...")
    results = apply_subnet_tags_to_workloads_account(
        workloads_account_id=workloads_account_id,
        vpc_id=vpc_id,
        subnet_tags=subnet_tags,
        region=region,
        role_name=role_name,
        dry_run=dry_run
    )
    
    # Summary
    successful = sum(1 for success in results.values() if success)
    total = len(results)
    print("-" * 50)
    print(f"Summary: {successful}/{total} subnets processed successfully")
    
    return results 