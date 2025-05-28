import os
import tempfile
import zipfile
from pathlib import Path

import boto3
import click
from botocore.exceptions import ClientError


class BootstrapManager:
    def __init__(self, session: boto3.Session):
        self.session = session
        self.s3_client = self.session.client("s3")
        self.sts_client = self.session.client("sts")
        self.cloudformation_client = self.session.client("cloudformation")
        self.package_version = self._get_package_version()

    def _get_bucket_name(self) -> str:
        account_id = self.sts_client.get_caller_identity()["Account"]
        region = self.session.region_name or "us-east-1"
        return f"plldb-core-infrastructure-{region}-{account_id}"

    def _get_package_version(self) -> str:
        try:
            import importlib.metadata

            return importlib.metadata.version("plldb")
        except Exception:
            return "0.1.0"

    def _get_s3_key_prefix(self) -> str:
        return f"plldb/versions/{self.package_version}"

    def _package_lambda_function(self, function_name: str) -> bytes:
        lambda_dir = Path(__file__).parent / "cloudformation" / "lambda_functions"
        lambda_file = lambda_dir / f"{function_name}.py"

        if not lambda_file.exists():
            raise FileNotFoundError(f"Lambda function {function_name}.py not found")

        with tempfile.NamedTemporaryFile(mode="wb", suffix=".zip", delete=False) as temp_file:
            temp_path = temp_file.name

        try:
            with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(lambda_file, f"{function_name}.py")

            with open(temp_path, "rb") as f:
                return f.read()
        finally:
            os.unlink(temp_path)

    def _upload_lambda_functions(self, bucket_name: str) -> None:
        lambda_dir = Path(__file__).parent / "cloudformation" / "lambda_functions"
        s3_key_prefix = self._get_s3_key_prefix()

        # Discover all Python modules in the lambda_functions directory
        lambda_functions = []
        for file_path in lambda_dir.glob("*.py"):
            if file_path.name != "__init__.py":
                lambda_functions.append(file_path.stem)

        if not lambda_functions:
            raise ValueError("No Lambda functions found in lambda_functions directory")

        for function_name in sorted(lambda_functions):
            click.echo(f"Packaging lambda function: {function_name}")
            function_zip = self._package_lambda_function(function_name)

            s3_key = f"{s3_key_prefix}/lambda_functions/{function_name}.zip"
            click.echo(f"Uploading to s3://{bucket_name}/{s3_key}")

            self.s3_client.put_object(Bucket=bucket_name, Key=s3_key, Body=function_zip)

    def _package_and_upload_layer(self, bucket_name: str) -> None:
        """Package and upload the Lambda layer for debugging runtime."""
        layer_dir = Path(__file__).parent / "cloudformation" / "layer"
        s3_key_prefix = self._get_s3_key_prefix()

        click.echo("Packaging Lambda layer...")

        with tempfile.NamedTemporaryFile(mode="wb", suffix=".zip", delete=False) as temp_file:
            temp_path = temp_file.name

        try:
            with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                # Add bootstrap script to bin/ directory
                bootstrap_path = layer_dir / "bootstrap"
                zipf.write(bootstrap_path, "bin/bootstrap")

                # Add lambda_runtime.py to bin/ directory
                runtime_path = layer_dir / "lambda_runtime.py"
                zipf.write(runtime_path, "bin/lambda_runtime.py")

            with open(temp_path, "rb") as f:
                layer_content = f.read()

            s3_key = f"{s3_key_prefix}/layer/debugger-layer.zip"
            click.echo(f"Uploading layer to s3://{bucket_name}/{s3_key}")

            self.s3_client.put_object(Bucket=bucket_name, Key=s3_key, Body=layer_content)

        finally:
            os.unlink(temp_path)

    def _upload_template(self, bucket_name: str) -> str:
        template_path = Path(__file__).parent / "cloudformation" / "template.yaml"
        s3_key_prefix = self._get_s3_key_prefix()
        s3_key = f"{s3_key_prefix}/template.yaml"

        click.echo(f"Uploading CloudFormation template to s3://{bucket_name}/{s3_key}")

        with open(template_path, "r") as f:
            template_content = f.read()

        self.s3_client.put_object(Bucket=bucket_name, Key=s3_key, Body=template_content.encode("utf-8"))

        return s3_key

    def _deploy_stack(self, bucket_name: str, template_s3_key: str) -> None:
        stack_name = "plldb"
        s3_key_prefix = self._get_s3_key_prefix()

        template_url = f"https://{bucket_name}.s3.amazonaws.com/{template_s3_key}"

        click.echo(f"Deploying CloudFormation stack: {stack_name}")

        try:
            self.cloudformation_client.describe_stacks(StackName=stack_name)
            click.echo(f"Stack {stack_name} already exists, updating...")
            operation = self.cloudformation_client.update_stack
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "ValidationError" and "does not exist" in str(e):
                click.echo(f"Creating new stack: {stack_name}")
                operation = self.cloudformation_client.create_stack
            else:
                raise

        try:
            operation(
                StackName=stack_name,
                TemplateURL=template_url,
                Parameters=[{"ParameterKey": "S3Bucket", "ParameterValue": bucket_name}, {"ParameterKey": "S3KeyPrefix", "ParameterValue": s3_key_prefix}],
                Capabilities=["CAPABILITY_IAM", "CAPABILITY_AUTO_EXPAND", "CAPABILITY_NAMED_IAM"],
            )

            click.echo(f"Waiting for stack {stack_name} to complete...")
            waiter = self.cloudformation_client.get_waiter("stack_create_complete" if operation == self.cloudformation_client.create_stack else "stack_update_complete")
            waiter.wait(StackName=stack_name)
            click.echo(f"Stack {stack_name} deployed successfully")

        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "ValidationError" and "No updates are to be performed" in str(e):
                click.echo(f"Stack {stack_name} is already up to date")
            else:
                raise

    def setup(self) -> None:
        bucket_name = self._get_bucket_name()
        region = self.session.region_name or "us-east-1"

        click.echo(f"Setting up core infrastructure bucket: {bucket_name}")

        try:
            self.s3_client.head_bucket(Bucket=bucket_name)
            click.echo(f"Bucket {bucket_name} already exists")
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "404":
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

        click.echo("\nPackaging and uploading Lambda functions...")
        self._upload_lambda_functions(bucket_name)

        click.echo("\nPackaging and uploading Lambda layer...")
        self._package_and_upload_layer(bucket_name)

        click.echo("\nUploading CloudFormation template...")
        template_s3_key = self._upload_template(bucket_name)

        click.echo("\nDeploying CloudFormation stack...")
        self._deploy_stack(bucket_name, template_s3_key)

        click.echo("\nBootstrap infrastructure deployment completed successfully")

    def destroy(self) -> None:
        bucket_name = self._get_bucket_name()
        stack_name = "plldb"

        click.echo(f"Destroying CloudFormation stack: {stack_name}")

        try:
            self.cloudformation_client.describe_stacks(StackName=stack_name)
            click.echo(f"Deleting stack {stack_name}...")
            self.cloudformation_client.delete_stack(StackName=stack_name)

            click.echo(f"Waiting for stack {stack_name} to be deleted...")
            waiter = self.cloudformation_client.get_waiter("stack_delete_complete")
            waiter.wait(StackName=stack_name)
            click.echo(f"Stack {stack_name} deleted successfully")
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "ValidationError" and "does not exist" in str(e):
                click.echo(f"Stack {stack_name} does not exist")
            else:
                raise

        click.echo(f"\nDestroying core infrastructure bucket: {bucket_name}")

        try:
            self.s3_client.head_bucket(Bucket=bucket_name)
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "404":
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
