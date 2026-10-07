from pathlib import Path
import urllib.request

import boto3
from botocore.exceptions import ClientError


REGION = "us-east-1"
INSTANCE_NAME = "income-api"
INSTANCE_TYPE = "t3.small"
ROLE_NAME = "income-api-ec2-role"
SECURITY_GROUP_NAME = "income-api-sg"
KEY_PAIR_NAME = "income-deploy"
LOCAL_PUBLIC_KEY = Path.home() / ".ssh" / "income_deploy.pub"
USER_DATA = Path(__file__).resolve().parents[1] / "infra" / "bootstrap_ec2.sh"


def get_client_ip() -> str:
    with urllib.request.urlopen("https://checkip.amazonaws.com", timeout=10) as response:
        return response.read().decode("utf-8").strip()


def ensure_key_pair(ec2) -> None:
    try:
        ec2.describe_key_pairs(KeyNames=[KEY_PAIR_NAME])
        return
    except ec2.exceptions.ClientError as error:
        if error.response["Error"]["Code"] != "InvalidKeyPair.NotFound":
            raise

    ec2.import_key_pair(
        KeyName=KEY_PAIR_NAME,
        PublicKeyMaterial=LOCAL_PUBLIC_KEY.read_bytes(),
        TagSpecifications=[
            {
                "ResourceType": "key-pair",
                "Tags": [{"Key": "Project", "Value": "income-lab"}],
            }
        ],
    )


def ensure_security_group(ec2, vpc_id: str, client_ip: str) -> str:
    groups = ec2.describe_security_groups(
        Filters=[
            {"Name": "group-name", "Values": [SECURITY_GROUP_NAME]},
            {"Name": "vpc-id", "Values": [vpc_id]},
        ]
    )["SecurityGroups"]
    if groups:
        group_id = groups[0]["GroupId"]
    else:
        group_id = ec2.create_security_group(
            GroupName=SECURITY_GROUP_NAME,
            Description="Income API access for GitHub Actions and lab client",
            VpcId=vpc_id,
            TagSpecifications=[
                {
                    "ResourceType": "security-group",
                    "Tags": [{"Key": "Project", "Value": "income-lab"}],
                }
            ],
        )["GroupId"]

    permissions = [
        {
            "IpProtocol": "tcp",
            "FromPort": 22,
            "ToPort": 22,
            "IpRanges": [
                {
                    "CidrIp": "0.0.0.0/0",
                    "Description": "Key-only SSH from GitHub-hosted runners",
                }
            ],
        },
        {
            "IpProtocol": "tcp",
            "FromPort": 8080,
            "ToPort": 8080,
            "IpRanges": [
                {
                    "CidrIp": f"{client_ip}/32",
                    "Description": "Income API from the current lab client",
                }
            ],
        },
    ]
    for permission in permissions:
        try:
            ec2.authorize_security_group_ingress(
                GroupId=group_id,
                IpPermissions=[permission],
            )
        except ec2.exceptions.ClientError as error:
            if error.response["Error"]["Code"] != "InvalidPermission.Duplicate":
                raise
    return group_id


def latest_ubuntu_ami(ec2) -> str:
    images = ec2.describe_images(
        Owners=["099720109477"],
        Filters=[
            {
                "Name": "name",
                "Values": ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"],
            },
            {"Name": "state", "Values": ["available"]},
        ],
    )["Images"]
    return max(images, key=lambda image: image["CreationDate"])["ImageId"]


def main() -> None:
    ec2 = boto3.client("ec2", region_name=REGION)
    existing = ec2.describe_instances(
        Filters=[
            {"Name": "tag:Name", "Values": [INSTANCE_NAME]},
            {
                "Name": "instance-state-name",
                "Values": ["pending", "running", "stopping", "stopped"],
            },
        ]
    )["Reservations"]
    if existing:
        instance = existing[0]["Instances"][0]
    else:
        default_vpc = ec2.describe_vpcs(
            Filters=[{"Name": "is-default", "Values": ["true"]}]
        )["Vpcs"][0]
        subnet = ec2.describe_subnets(
            Filters=[
                {"Name": "vpc-id", "Values": [default_vpc["VpcId"]]},
                {"Name": "availability-zone", "Values": [f"{REGION}a"]},
            ]
        )["Subnets"][0]
        group_id = ensure_security_group(
            ec2,
            default_vpc["VpcId"],
            get_client_ip(),
        )
        ensure_key_pair(ec2)

        instance = ec2.run_instances(
            ImageId=latest_ubuntu_ami(ec2),
            InstanceType=INSTANCE_TYPE,
            KeyName=KEY_PAIR_NAME,
            MinCount=1,
            MaxCount=1,
            IamInstanceProfile={"Name": ROLE_NAME},
            UserData=USER_DATA.read_text(encoding="utf-8"),
            MetadataOptions={
                "HttpTokens": "required",
                "HttpEndpoint": "enabled",
                "HttpPutResponseHopLimit": 1,
            },
            CreditSpecification={"CpuCredits": "standard"},
            BlockDeviceMappings=[
                {
                    "DeviceName": "/dev/sda1",
                    "Ebs": {
                        "VolumeSize": 12,
                        "VolumeType": "gp3",
                        "Encrypted": True,
                        "DeleteOnTermination": True,
                    },
                }
            ],
            NetworkInterfaces=[
                {
                    "DeviceIndex": 0,
                    "SubnetId": subnet["SubnetId"],
                    "Groups": [group_id],
                    "AssociatePublicIpAddress": True,
                }
            ],
            TagSpecifications=[
                {
                    "ResourceType": "instance",
                    "Tags": [
                        {"Key": "Name", "Value": INSTANCE_NAME},
                        {"Key": "Project", "Value": "income-lab"},
                    ],
                },
                {
                    "ResourceType": "volume",
                    "Tags": [{"Key": "Project", "Value": "income-lab"}],
                },
            ],
        )["Instances"][0]

    instance_id = instance["InstanceId"]
    ec2.get_waiter("instance_running").wait(InstanceIds=[instance_id])
    ec2.get_waiter("instance_status_ok").wait(
        InstanceIds=[instance_id],
        WaiterConfig={"Delay": 15, "MaxAttempts": 40},
    )
    instance = ec2.describe_instances(InstanceIds=[instance_id])["Reservations"][0][
        "Instances"
    ][0]
    print(f"Instance ID: {instance_id}")
    print(f"Public IP: {instance['PublicIpAddress']}")
    print(f"Instance type: {instance['InstanceType']}")


if __name__ == "__main__":
    try:
        main()
    except ClientError as error:
        raise SystemExit(f"EC2 launch failed: {error}") from error
