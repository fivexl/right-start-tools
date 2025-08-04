"""
Cross-account VPC subnet tagging functions using AWS Resource Access Manager (RAM).

This module provides functions to:
1. Identify networking accounts using RAM resource shares
2. Find subnet shares and target accounts using RAM APIs
3. Extract subnet tags from networking accounts
4. Apply those tags to shared subnets in target accounts

The new approach uses AWS RAM to discover sharing relationships rather than
relying on naming conventions.

Usage:
    copy_vpc_subnet_tags_using_ram(
        vpc_name="apps",
        region="us-east-1",
        dry_run=True
    )
"""
from typing import Dict, List, Optional, Set, Tuple

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


def get_vpc_tags_by_id(vpc_id: str, ec2_client) -> Dict[str, str]:
    """
    Get all tags for a given VPC ID.
    
    Args:
        vpc_id: The VPC ID to get tags for
        ec2_client: The boto3 EC2 client
        
    Returns:
        Dictionary of VPC tags
    """
    try:
        response = ec2_client.describe_vpcs(VpcIds=[vpc_id])
        vpc = response["Vpcs"][0]
        tags = {}
        for tag in vpc.get("Tags", []):
            tags[tag["Key"]] = tag["Value"]
        return tags
    except (ClientError, BotoCoreError) as e:
        print(f"Error getting tags for VPC {vpc_id}: {e}")
        return {}


def apply_tags_to_vpc(vpc_id: str, tags: Dict[str, str], ec2_client, dry_run: bool = True) -> bool:
    """
    Apply tags to a specific VPC.
    
    Args:
        vpc_id: The VPC ID to tag
        tags: Dictionary of tags to apply
        ec2_client: The boto3 EC2 client
        dry_run: If True, only print what would be done
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Convert tags dict to AWS tags format
        aws_tags = [
            {"Key": str(key), "Value": str(value)} 
            for key, value in tags.items()
        ]
        
        if dry_run:
            print(f"DRY RUN - Would apply tags to VPC {vpc_id}: {tags}")
            return True
        else:
            ec2_client.create_tags(
                Resources=[vpc_id],
                Tags=aws_tags
            )
            print(f"Successfully applied tags to VPC {vpc_id}: {tags}")
            return True
    except (ClientError, BotoCoreError) as e:
        print(f"Error applying tags to VPC {vpc_id}: {e}")
        return False


def copy_vpc_name_tag_cross_account(
    networking_account_id: str,
    workloads_account_id: str,
    vpc_id: str,
    region: str = "us-east-1",
    role_name: str = "AWSControlTowerExecution",
    dry_run: bool = True
) -> bool:
    """
    Copy VPC Name tag from networking account to workloads account.
    
    Args:
        networking_account_id: AWS account ID of the networking account
        workloads_account_id: AWS account ID of the workloads account
        vpc_id: The VPC ID (should exist in both accounts if using RAM sharing)
        region: AWS region (default: us-east-1)
        role_name: IAM role name to assume (default: AWSControlTowerExecution)
        dry_run: If True, only print what would be done (default: True)
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Get VPC tags from networking account
        networking_session = assume_role(networking_account_id, role_name)
        networking_ec2_client = networking_session.client("ec2", region_name=region)
        vpc_tags = get_vpc_tags_by_id(vpc_id, networking_ec2_client)
        
        if not vpc_tags or "Name" not in vpc_tags:
            print(f"No Name tag found for VPC {vpc_id} in networking account {networking_account_id}")
            return False
        
        # Only copy the Name tag
        name_tag = {"Name": vpc_tags["Name"]}
        print(f"Found VPC Name tag: {name_tag}")
        
        # Apply VPC Name tag to workloads account
        workloads_session = assume_role(workloads_account_id, role_name)
        workloads_ec2_client = workloads_session.client("ec2", region_name=region)
        
        return apply_tags_to_vpc(vpc_id, name_tag, workloads_ec2_client, dry_run)
        
    except (ClientError, BotoCoreError) as e:
        print(f"Error copying VPC Name tag: {e}")
        return False


def copy_vpc_subnet_tags_cross_account(
    networking_account_id: str,
    workloads_account_id: str,
    vpc_name: str,
    region: str = "us-east-1",
    role_name: str = "AWSControlTowerExecution",
    dry_run: bool = True
) -> Dict[str, bool]:
    """
    Main function to copy VPC and subnet tags from networking account to workloads account.
    
    Args:
        networking_account_id: AWS account ID where the VPC tags are defined
        workloads_account_id: AWS account ID where tags should be applied
        vpc_name: The VPC name used for tag generation
        region: AWS region (default: us-east-1)
        role_name: IAM role name to assume in both accounts (default: AWSControlTowerExecution)
        dry_run: If True, only print what would be done (default: True)
        
    Returns:
        Dictionary mapping subnet IDs to success status (True/False)
        
    Raises:
        ClientError: If role assumption or AWS API calls fail
    """
    print(f"Starting cross-account VPC and subnet tag copy...")
    print(f"Networking Account: {networking_account_id}")
    print(f"Workloads Account: {workloads_account_id}")
    print(f"VPC Name: {vpc_name}")
    print(f"Region: {region}")
    print(f"Dry Run: {dry_run}")
    print("-" * 50)

    session = assume_role(networking_account_id, role_name)
    vpc_id = get_vpc_id_by_name(session, vpc_name, region)
    
    # Step 1: Copy VPC Name tag
    print("Step 1: Copying VPC Name tag from networking account to workloads account...")
    vpc_success = copy_vpc_name_tag_cross_account(
        networking_account_id=networking_account_id,
        workloads_account_id=workloads_account_id,
        vpc_id=vpc_id,
        region=region,
        role_name=role_name,
        dry_run=dry_run
    )
    
    if vpc_success:
        print("VPC Name tag copied successfully")
    else:
        print("Failed to copy VPC Name tag")
    print("-" * 50)
    
    # Step 2: Extract subnet tags from networking account
    print("Step 2: Extracting subnet tags from networking account...")
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
    
    # Step 3: Apply subnet tags to workloads account
    print("Step 3: Applying subnet tags to workloads account...")
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
    print(f"Summary: VPC Name tag {'copied' if vpc_success else 'failed'}, {successful}/{total} subnets processed successfully")
    
    return results


def get_ram_resource_shares(session: boto3.Session, region: str = "us-east-1") -> List[Dict]:
    """
    Get all resource shares owned by the current account using AWS RAM.
    
    Args:
        session: Boto3 session for the account to check
        region: AWS region to check for resource shares
        
    Returns:
        List of resource share dictionaries
    """
    try:
        ram_client = session.client("ram", region_name=region)
        
        resource_shares = []
        paginator = ram_client.get_paginator("get_resource_shares")
        
        for page in paginator.paginate(resourceOwner="SELF"):
            resource_shares.extend(page.get("resourceShares", []))
            
        print(f"Found {len(resource_shares)} resource shares")
        return resource_shares
        
    except (ClientError, BotoCoreError) as e:
        print(f"Error getting resource shares: {e}")
        return []


def get_shared_subnets_from_ram(session: boto3.Session, vpc_id: str, region: str = "us-east-1") -> List[Dict]:
    """
    Get all subnets shared from the specified VPC using AWS RAM.
    
    Args:
        session: Boto3 session for the networking account
        vpc_id: VPC ID to find shared subnets for
        region: AWS region
        
    Returns:
        List of subnet ARNs that are shared via RAM
    """
    try:
        ram_client = session.client("ram", region_name=region)
        ec2_client = session.client("ec2", region_name=region)
        
        # Get all subnets in the VPC
        subnets = get_subnets_by_vpc_id(vpc_id, ec2_client)
        if not subnets:
            return []
        
        vpc_subnet_arns = [
            f"arn:aws:ec2:{region}:{session.client('sts').get_caller_identity()['Account']}:subnet/{subnet['SubnetId']}"
            for subnet in subnets
        ]
        
        # Find which subnets are shared via RAM
        shared_subnets = []
        
        # Get all resource shares owned by this account first
        resource_shares = []
        shares_paginator = ram_client.get_paginator("get_resource_shares")
        for page in shares_paginator.paginate(resourceOwner="SELF"):
            resource_shares.extend(page.get("resourceShares", []))
        
        # Then get resource associations for each resource share
        for resource_share in resource_shares:
            resource_share_arn = resource_share["resourceShareArn"]
            
            paginator = ram_client.get_paginator("get_resource_share_associations")
            for page in paginator.paginate(
                associationType="RESOURCE",
                resourceShareArns=[resource_share_arn]
            ):
                for association in page.get("resourceShareAssociations", []):
                    resource_arn = association.get("associatedEntity")
                    if (resource_arn and 
                        resource_arn.startswith("arn:aws:ec2:") and 
                        ":subnet/" in resource_arn and 
                        resource_arn in vpc_subnet_arns and
                        association.get("status") == "ASSOCIATED"):
                        
                        shared_subnets.append({
                            "subnet_arn": resource_arn,
                            "subnet_id": resource_arn.split("/")[-1],
                            "resource_share_arn": resource_share_arn
                        })
        
        print(f"Found {len(shared_subnets)} shared subnets in VPC {vpc_id}")
        return shared_subnets
        
    except (ClientError, BotoCoreError) as e:
        print(f"Error finding shared subnets: {e}")
        return []


def get_target_accounts_from_ram_shares(session: boto3.Session, resource_share_arns: List[str], region: str = "us-east-1") -> Set[str]:
    """
    Get all target account IDs that have access to the specified resource shares.
    
    Args:
        session: Boto3 session for the networking account
        resource_share_arns: List of resource share ARNs to check
        region: AWS region
        
    Returns:
        Set of account IDs that have access to the resource shares
    """
    try:
        ram_client = session.client("ram", region_name=region)
        target_accounts = set()
        
        # Get principal associations for each resource share
        for resource_share_arn in resource_share_arns:
            paginator = ram_client.get_paginator("get_resource_share_associations")
            for page in paginator.paginate(
                associationType="PRINCIPAL",
                resourceShareArns=[resource_share_arn]
            ):
                for association in page.get("resourceShareAssociations", []):
                    principal = association.get("associatedEntity")
                    if (principal and 
                        association.get("status") == "ASSOCIATED"):
                        
                        # Handle direct account IDs
                        if principal.isdigit() and len(principal) == 12:
                            target_accounts.add(principal)
                        # Handle OU ARNs - expand to member accounts
                        elif "ou-" in principal:
                            print(f"Found OU principal: {principal} - expanding to member accounts")
                            ou_accounts = expand_ou_to_accounts(principal, region)
                            target_accounts.update(ou_accounts)
        
        print(f"Found {len(target_accounts)} target accounts from RAM shares")
        return target_accounts
        
    except (ClientError, BotoCoreError) as e:
        print(f"Error getting target accounts from RAM shares: {e}")
        return set()


def expand_ou_to_accounts(ou_arn_or_id: str, region: str = "us-east-1") -> Set[str]:
    """
    Expand an OU ARN or ID to its member account IDs.
    
    Args:
        ou_arn_or_id: OU ARN or OU ID (e.g., "ou-12345" or full ARN)
        region: AWS region (not used for Organizations API but kept for consistency)
        
    Returns:
        Set of account IDs that are members of the OU
    """
    try:
        # Extract OU ID from ARN if needed
        if ou_arn_or_id.startswith("arn:aws:organizations::"):
            ou_id = ou_arn_or_id.split("/")[-1]
        else:
            ou_id = ou_arn_or_id
        
        # Organizations API is global, so we don't need to specify region
        org_client = boto3.client("organizations")
        
        account_ids = set()
        
        # Get accounts directly in this OU
        paginator = org_client.get_paginator("list_accounts_for_parent")
        for page in paginator.paginate(ParentId=ou_id):
            for account in page.get("Accounts", []):
                if account.get("Status") == "ACTIVE":
                    account_ids.add(account["Id"])
        
        # Recursively get accounts from child OUs
        child_paginator = org_client.get_paginator("list_organizational_units_for_parent")
        for page in child_paginator.paginate(ParentId=ou_id):
            for child_ou in page.get("OrganizationalUnits", []):
                child_accounts = expand_ou_to_accounts(child_ou["Id"], region)
                account_ids.update(child_accounts)
        
        print(f"Expanded OU {ou_id} to {len(account_ids)} accounts")
        return account_ids
        
    except (ClientError, BotoCoreError) as e:
        print(f"Error expanding OU {ou_arn_or_id} to accounts: {e}")
        return set()


def get_all_vpcs_with_shared_subnets(session: boto3.Session, region: str = "us-east-1") -> List[Dict[str, str]]:
    """
    Get all VPCs that have subnets shared via RAM.
    
    Args:
        session: Boto3 session for the networking account
        region: AWS region
        
    Returns:
        List of dictionaries with VPC info: [{"vpc_id": "vpc-123", "vpc_name": "apps"}]
    """
    try:
        ram_client = session.client("ram", region_name=region)
        ec2_client = session.client("ec2", region_name=region)
        
        # Get all VPCs in the account
        vpcs_response = ec2_client.describe_vpcs()
        vpcs_with_shared_subnets = []
        
        # Get all shared subnet ARNs from RAM
        # First get all resource shares owned by this account
        shared_subnet_arns = set()
        resource_shares = []
        
        shares_paginator = ram_client.get_paginator("get_resource_shares")
        for page in shares_paginator.paginate(resourceOwner="SELF"):
            resource_shares.extend(page.get("resourceShares", []))
        
        # Then get resource associations for each resource share
        for resource_share in resource_shares:
            resource_share_arn = resource_share["resourceShareArn"]
            
            paginator = ram_client.get_paginator("get_resource_share_associations")
            for page in paginator.paginate(
                associationType="RESOURCE",
                resourceShareArns=[resource_share_arn]
            ):
                for association in page.get("resourceShareAssociations", []):
                    resource_arn = association.get("associatedEntity")
                    if (resource_arn and 
                        resource_arn.startswith("arn:aws:ec2:") and 
                        ":subnet/" in resource_arn and
                        association.get("status") == "ASSOCIATED"):
                        shared_subnet_arns.add(resource_arn)
        
        if not shared_subnet_arns:
            print("No shared subnets found via RAM")
            return []
        
        # For each VPC, check if it has any shared subnets
        for vpc in vpcs_response.get("Vpcs", []):
            vpc_id = vpc["VpcId"]
            
            # Get subnets in this VPC
            subnets = get_subnets_by_vpc_id(vpc_id, ec2_client)
            if not subnets:
                continue
                
            # Check if any subnets in this VPC are shared
            account_id = session.client('sts').get_caller_identity()['Account']
            vpc_subnet_arns = [
                f"arn:aws:ec2:{region}:{account_id}:subnet/{subnet['SubnetId']}"
                for subnet in subnets
            ]
            
            # If this VPC has shared subnets, include it
            if any(arn in shared_subnet_arns for arn in vpc_subnet_arns):
                # Get VPC name from tags
                vpc_name = None
                for tag in vpc.get("Tags", []):
                    if tag["Key"] == "Name":
                        vpc_name = tag["Value"]
                        break
                
                vpcs_with_shared_subnets.append({
                    "vpc_id": vpc_id,
                    "vpc_name": vpc_name or f"unnamed-vpc-{vpc_id}"
                })
        
        print(f"Found {len(vpcs_with_shared_subnets)} VPCs with shared subnets")
        return vpcs_with_shared_subnets
        
    except (ClientError, BotoCoreError) as e:
        print(f"Error finding VPCs with shared subnets: {e}")
        return []


def copy_vpc_subnet_tags_using_ram(
    vpc_name: Optional[str] = None,
    region: str = "us-east-1",
    role_name: str = "AWSControlTowerExecution",
    dry_run: bool = True,
    networking_account_ids: Optional[List[str]] = None
) -> Dict[str, Dict[str, bool]]:
    """
    Copy VPC and subnet tags using AWS RAM to discover shared subnets and target accounts.
    
    This function replaces the naming convention-based approach with RAM-based discovery:
    1. Identifies networking accounts (or uses provided list)
    2. Finds subnet shares using RAM APIs
    3. Discovers target accounts from RAM principal associations
    4. Copies tags for shared subnets to target accounts
    
    Args:
        vpc_name: The VPC name to copy tags for (if None, processes all VPCs with shared subnets)
        region: AWS region (default: us-east-1)
        role_name: IAM role name to assume in accounts (default: AWSControlTowerExecution)
        dry_run: If True, only print what would be done (default: True)
        networking_account_ids: List of networking account IDs (if not provided, will try to discover)
        
    Returns:
        Dictionary mapping account IDs to subnet tagging results
    """
    print(f"Starting RAM-based VPC and subnet tag copy...")
    print(f"VPC Name: {vpc_name if vpc_name else 'All VPCs with shared subnets'}")
    print(f"Region: {region}")
    print(f"Dry Run: {dry_run}")
    print("-" * 50)
    
    # Validate inputs
    if not region or not region.strip():
        raise ValueError("Region cannot be empty")
    
    all_results = {}
    
    # Step 1: Identify networking accounts
    if networking_account_ids:
        print(f"Using provided networking accounts: {networking_account_ids}")
    else:
        print("Step 1: Identifying networking accounts from RAM resource shares...")
        # This would need to be implemented based on your organization structure
        print("ERROR: No networking accounts provided and auto-discovery not implemented")
        print("Please provide networking_account_ids parameter")
        return {}
    
    # Step 2: For each networking account, find shared subnets and target accounts
    for networking_account_id in networking_account_ids:
        print(f"\nProcessing networking account: {networking_account_id}")
        
        try:
            # Assume role in networking account
            networking_session = assume_role(networking_account_id, role_name)
            
            # Determine which VPCs to process
            vpcs_to_process = []
            if vpc_name:
                # Process specific VPC
                vpc_id = get_vpc_id_by_name(networking_session, vpc_name, region)
                vpcs_to_process = [{"vpc_id": vpc_id, "vpc_name": vpc_name}]
                print(f"Found VPC {vpc_id} with name '{vpc_name}'")
            else:
                # Process all VPCs with shared subnets
                vpcs_to_process = get_all_vpcs_with_shared_subnets(networking_session, region)
                if not vpcs_to_process:
                    print("No VPCs with shared subnets found")
                    continue
            
            # Step 3: Process each VPC
            for vpc_info in vpcs_to_process:
                current_vpc_id = vpc_info["vpc_id"]
                current_vpc_name = vpc_info["vpc_name"]
                
                print(f"\n--- Processing VPC: {current_vpc_name} ({current_vpc_id}) ---")
                
                # Find shared subnets using RAM
                print("Finding shared subnets using RAM...")
                shared_subnets = get_shared_subnets_from_ram(networking_session, current_vpc_id, region)
                
                if not shared_subnets:
                    print("No shared subnets found for this VPC")
                    continue
                
                # Get unique resource share ARNs
                resource_share_arns = list(set([subnet["resource_share_arn"] for subnet in shared_subnets]))
                
                # Step 4: Find target accounts from RAM principal associations
                print("Finding target accounts from RAM principal associations...")
                target_accounts = get_target_accounts_from_ram_shares(
                    networking_session, resource_share_arns, region
                )
                
                if not target_accounts:
                    print("No target accounts found for this VPC")
                    continue
                
                # Step 5: Extract subnet tags from networking account
                print("Extracting subnet tags from networking account...")
                subnet_tags = extract_subnet_tags_from_networking_account(
                    networking_account_id=networking_account_id,
                    vpc_id=current_vpc_id,
                    vpc_name=current_vpc_name,
                    region=region,
                    role_name=role_name
                )
                
                if not subnet_tags:
                    print("No valid subnet tags found in networking account for this VPC")
                    continue
                
                # Filter subnet tags to only include shared subnets
                shared_subnet_ids = [subnet["subnet_id"] for subnet in shared_subnets]
                shared_subnet_tags = {
                    subnet_id: tags for subnet_id, tags in subnet_tags.items() 
                    if subnet_id in shared_subnet_ids
                }
                
                print(f"Found tags for {len(shared_subnet_tags)} shared subnets")
                
                # Step 6: Apply tags to each target account
                for target_account_id in target_accounts:
                    print(f"\nCopying tags to target account: {target_account_id}")
                    
                    # Copy VPC Name tag
                    print("Copying VPC Name tag...")
                    vpc_success = copy_vpc_name_tag_cross_account(
                        networking_account_id=networking_account_id,
                        workloads_account_id=target_account_id,
                        vpc_id=current_vpc_id,
                        region=region,
                        role_name=role_name,
                        dry_run=dry_run
                    )
                    
                    # Copy subnet tags for shared subnets only
                    print("Copying subnet tags for shared subnets...")
                    subnet_results = apply_subnet_tags_to_workloads_account(
                        workloads_account_id=target_account_id,
                        vpc_id=current_vpc_id,
                        subnet_tags=shared_subnet_tags,
                        region=region,
                        role_name=role_name,
                        dry_run=dry_run
                    )
                    
                    # Store results with VPC context
                    account_vpc_key = f"{target_account_id}-{current_vpc_id}"
                    all_results[account_vpc_key] = subnet_results
                    
                    # Summary for this target account and VPC
                    successful = sum(1 for success in subnet_results.values() if success)
                    total = len(subnet_results)
                    print(f"Account {target_account_id} / VPC {current_vpc_name}: VPC Name tag {'copied' if vpc_success else 'failed'}, {successful}/{total} subnets processed successfully")
        
        except Exception as e:
            print(f"Error processing networking account {networking_account_id}: {e}")
            continue
    
    # Overall summary
    total_operations = len(all_results)
    total_subnets = sum(len(results) for results in all_results.values())
    successful_subnets = sum(
        sum(1 for success in results.values() if success) 
        for results in all_results.values()
    )
    
    print("-" * 50)
    if vpc_name:
        print(f"Overall Summary: Processed {total_operations} target accounts for VPC '{vpc_name}', {successful_subnets}/{total_subnets} subnet tag operations successful")
    else:
        print(f"Overall Summary: Processed {total_operations} account-VPC combinations, {successful_subnets}/{total_subnets} subnet tag operations successful")
    
    return all_results 