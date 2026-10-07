import json
import time

import boto3
from botocore.exceptions import ClientError


ACCOUNT_ID = "950037471965"
REGION = "us-east-1"
BUCKET = "income-lab-950037471965-us-east-1"
CI_USER = "income-lab-github"
EC2_ROLE = "income-api-ec2-role"
CI_PROFILE = "income-lab-ci"


def ensure_iam_resources() -> None:
    iam = boto3.client("iam")

    ci_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "ManageLabBucket",
                "Effect": "Allow",
                "Action": [
                    "s3:CreateBucket",
                    "s3:PutEncryptionConfiguration",
                    "s3:PutBucketPublicAccessBlock",
                    "s3:PutBucketPolicy",
                    "s3:GetBucketLocation",
                    "s3:ListBucket",
                ],
                "Resource": f"arn:aws:s3:::{BUCKET}",
            },
            {
                "Sid": "ManageLabObjects",
                "Effect": "Allow",
                "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
                "Resource": [
                    f"arn:aws:s3:::{BUCKET}/dvc/*",
                    f"arn:aws:s3:::{BUCKET}/artifacts/current/*",
                ],
            },
        ],
    }
    iam.put_user_policy(
        UserName=CI_USER,
        PolicyName="income-lab-s3-access",
        PolicyDocument=json.dumps(ci_policy),
    )

    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "ec2.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    }
    try:
        iam.create_role(
            RoleName=EC2_ROLE,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Tags=[{"Key": "Project", "Value": "income-lab"}],
        )
    except iam.exceptions.EntityAlreadyExistsException:
        pass

    iam.get_waiter("role_exists").wait(RoleName=EC2_ROLE)
    iam.attach_role_policy(
        RoleName=EC2_ROLE,
        PolicyArn="arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
    )

    try:
        iam.create_instance_profile(InstanceProfileName=EC2_ROLE)
    except iam.exceptions.EntityAlreadyExistsException:
        pass

    profile = iam.get_instance_profile(InstanceProfileName=EC2_ROLE)[
        "InstanceProfile"
    ]
    if not any(role["RoleName"] == EC2_ROLE for role in profile["Roles"]):
        iam.add_role_to_instance_profile(
            InstanceProfileName=EC2_ROLE,
            RoleName=EC2_ROLE,
        )


def ensure_bucket() -> None:
    session = boto3.Session(profile_name=CI_PROFILE, region_name=REGION)
    s3 = session.client("s3")

    try:
        s3.create_bucket(Bucket=BUCKET)
    except s3.exceptions.BucketAlreadyOwnedByYou:
        pass

    s3.get_waiter("bucket_exists").wait(Bucket=BUCKET)
    s3.put_bucket_encryption(
        Bucket=BUCKET,
        ServerSideEncryptionConfiguration={
            "Rules": [
                {
                    "ApplyServerSideEncryptionByDefault": {
                        "SSEAlgorithm": "AES256"
                    },
                    "BucketKeyEnabled": False,
                }
            ]
        },
    )
    s3.put_public_access_block(
        Bucket=BUCKET,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        },
    )

    bucket_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "AllowCiBucketRead",
                "Effect": "Allow",
                "Principal": {
                    "AWS": f"arn:aws:iam::{ACCOUNT_ID}:user/{CI_USER}"
                },
                "Action": ["s3:GetBucketLocation", "s3:ListBucket"],
                "Resource": f"arn:aws:s3:::{BUCKET}",
            },
            {
                "Sid": "AllowCiObjects",
                "Effect": "Allow",
                "Principal": {
                    "AWS": f"arn:aws:iam::{ACCOUNT_ID}:user/{CI_USER}"
                },
                "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
                "Resource": [
                    f"arn:aws:s3:::{BUCKET}/dvc/*",
                    f"arn:aws:s3:::{BUCKET}/artifacts/current/*",
                ],
            },
            {
                "Sid": "AllowEc2ModelDownload",
                "Effect": "Allow",
                "Principal": {
                    "AWS": f"arn:aws:iam::{ACCOUNT_ID}:role/{EC2_ROLE}"
                },
                "Action": "s3:GetObject",
                "Resource": (
                    f"arn:aws:s3:::{BUCKET}/artifacts/current/model.joblib"
                ),
            },
            {
                "Sid": "DenyInsecureTransport",
                "Effect": "Deny",
                "Principal": "*",
                "Action": "s3:*",
                "Resource": [
                    f"arn:aws:s3:::{BUCKET}",
                    f"arn:aws:s3:::{BUCKET}/*",
                ],
                "Condition": {"Bool": {"aws:SecureTransport": "false"}},
            },
        ],
    }
    s3.put_bucket_policy(Bucket=BUCKET, Policy=json.dumps(bucket_policy))


def main() -> None:
    ensure_iam_resources()
    time.sleep(5)
    ensure_bucket()
    print(f"Configured S3 bucket: {BUCKET}")
    print(f"Configured CI user: {CI_USER}")
    print(f"Configured EC2 role and instance profile: {EC2_ROLE}")


if __name__ == "__main__":
    try:
        main()
    except ClientError as error:
        raise SystemExit(f"AWS bootstrap failed: {error}") from error
