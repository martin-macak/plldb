import boto3
import click
from botocore.exceptions import ClientError


class BootstrapManager:
    def __init__(self, session: boto3.Session):
        self.session = session
        self.s3_client = self.session.client("s3")
        self.sts_client = self.session.client("sts")

    def _get_bucket_name(self) -> str:
        account_id = self.sts_client.get_caller_identity()["Account"]
        region = self.session.region_name or "us-east-1"
        return f"plldb-core-infrastructure-{region}-{account_id}"

    def setup(self) -> None:
        bucket_name = self._get_bucket_name()
        region = self.session.region_name or "us-east-1"

        click.echo(f"Setting up core infrastructure bucket: {bucket_name}")

        try:
            self.s3_client.head_bucket(Bucket=bucket_name)
            click.echo(f"Bucket {bucket_name} already exists")
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                click.echo(f"Creating bucket {bucket_name}")
                if region == "us-east-1":
                    self.s3_client.create_bucket(Bucket=bucket_name)
                else:
                    self.s3_client.create_bucket(
                        Bucket=bucket_name,
                        CreateBucketConfiguration={"LocationConstraint": region},
                    )

                self.s3_client.put_public_access_block(
                    Bucket=bucket_name,
                    PublicAccessBlockConfiguration={
                        "BlockPublicAcls": True,
                        "IgnorePublicAcls": True,
                        "BlockPublicPolicy": True,
                        "RestrictPublicBuckets": True,
                    },
                )
                click.echo(f"Bucket {bucket_name} created with public access blocked")
            else:
                raise

        click.echo("Bootstrap setup completed successfully")

    def destroy(self) -> None:
        bucket_name = self._get_bucket_name()

        click.echo(f"Destroying core infrastructure bucket: {bucket_name}")

        try:
            self.s3_client.head_bucket(Bucket=bucket_name)
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                click.echo(f"Bucket {bucket_name} does not exist")
                return
            else:
                raise

        click.echo(f"Emptying bucket {bucket_name}")
        paginator = self.s3_client.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=bucket_name)

        delete_keys = []
        for page in pages:
            if "Contents" in page:
                for obj in page["Contents"]:
                    delete_keys.append({"Key": obj["Key"]})

                    if len(delete_keys) >= 1000:
                        self.s3_client.delete_objects(Bucket=bucket_name, Delete={"Objects": delete_keys})
                        delete_keys = []

        if delete_keys:
            self.s3_client.delete_objects(Bucket=bucket_name, Delete={"Objects": delete_keys})

        click.echo(f"Deleting bucket {bucket_name}")
        self.s3_client.delete_bucket(Bucket=bucket_name)

        click.echo("Bootstrap destroy completed successfully")
