import boto3
import click
import hashlib
import os
from mypy_boto3_sts import STSClient


def get_aws_account_id(client: STSClient) -> str:
    account_id = client.get_caller_identity()['Account']
    return account_id

def hash_environment_id(tf_environment_id):
    # Create a SHA-1 hash object
    hash_object = hashlib.sha1()
    # Update the hash object with the bytes of the string, encoding needed to convert str to bytes
    hash_object.update(tf_environment_id.encode('utf-8'))
    # Get the hexadecimal representation of the digest
    hashed_environment_id = hash_object.hexdigest()
    return hashed_environment_id

def write_backend_config(aws_default_region, hashed_environment_id):
    backend_config = f"""terraform {{
  backend "s3" {{
    bucket         = "terraform-state-{hashed_environment_id}"
    key            = "terraform/main/main.tfstate"
    region         = "{aws_default_region}"
    encrypt        = true
    dynamodb_table = "terraform-state-lock-{hashed_environment_id}"
  }}
}}
"""
    with open("backend.tf", "w") as f:
        f.write(backend_config)

@click.command(short_help='Generate backend.tf file based on current AWS environment.')
def gen_tf_backend():
    """Generate backend.tf file."""
    session = boto3.Session()
    client = session.client('sts')
    aws_account_id = get_aws_account_id(client)
    region         = session.region_name
    env_id = hash_environment_id(f"{aws_account_id}-{region}")
    click.echo(f"Writing backend.tf...")
    click.echo(f"  AWS Account ID: {aws_account_id}")
    click.echo(f"  AWS Region: {region}")
    write_backend_config(region, env_id)


# def main():
#     # Check for AWS_DEFAULT_REGION in environment variables
#     aws_default_region = os.getenv("AWS_DEFAULT_REGION", region)
#     if not aws_default_region:
#         print("Define env variable AWS_DEFAULT_REGION (should be your region name, ex: us-east-1) and try again.")
#         exit(1)

#     tf_environment_id = set_tf_environment_id(aws_default_region)
#     hashed_environment_id = hash_environment_id(tf_environment_id)
#     write_backend_config(tf_environment_id, aws_default_region, hashed_environment_id)

# if __name__ == "__main__":
#     main()
