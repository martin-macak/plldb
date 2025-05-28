import pytest
from botocore.exceptions import ClientError

from plldb.setup import BootstrapManager


class TestBootstrapManager:
    def test_get_bucket_name(self, mock_aws_session):
        manager = BootstrapManager(session=mock_aws_session)
        bucket_name = manager._get_bucket_name()

        assert bucket_name == "plldb-core-infrastructure-us-east-1-123456789012"

    def test_setup_creates_bucket_when_not_exists(self, mock_aws_session, monkeypatch):
        manager = BootstrapManager(session=mock_aws_session)
        s3_client = mock_aws_session.client("s3")

        # Mock the new methods to avoid CloudFormation calls
        monkeypatch.setattr(manager, "_upload_lambda_functions", lambda bucket_name: None)
        monkeypatch.setattr(manager, "_upload_template", lambda bucket_name: "test-key")
        monkeypatch.setattr(manager, "_deploy_stack", lambda bucket_name, template_key: None)

        manager.setup()

        response = s3_client.head_bucket(Bucket="plldb-core-infrastructure-us-east-1-123456789012")
        assert response["ResponseMetadata"]["HTTPStatusCode"] == 200

        public_access_block = s3_client.get_public_access_block(Bucket="plldb-core-infrastructure-us-east-1-123456789012")
        config = public_access_block["PublicAccessBlockConfiguration"]
        assert config["BlockPublicAcls"] is True
        assert config["IgnorePublicAcls"] is True
        assert config["BlockPublicPolicy"] is True
        assert config["RestrictPublicBuckets"] is True

    def test_setup_idempotent_when_bucket_exists(self, mock_aws_session, monkeypatch):
        manager = BootstrapManager(session=mock_aws_session)
        s3_client = mock_aws_session.client("s3")

        s3_client.create_bucket(Bucket="plldb-core-infrastructure-us-east-1-123456789012")

        # Mock the new methods to avoid CloudFormation calls
        monkeypatch.setattr(manager, "_upload_lambda_functions", lambda bucket_name: None)
        monkeypatch.setattr(manager, "_upload_template", lambda bucket_name: "test-key")
        monkeypatch.setattr(manager, "_deploy_stack", lambda bucket_name, template_key: None)

        manager.setup()

        response = s3_client.head_bucket(Bucket="plldb-core-infrastructure-us-east-1-123456789012")
        assert response["ResponseMetadata"]["HTTPStatusCode"] == 200

    def test_setup_creates_bucket_with_region_constraint(self, monkeypatch):
        # Create a new session with eu-west-1 region
        import boto3
        import moto

        monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-1")

        with moto.mock_aws():
            eu_session = boto3.Session(region_name="eu-west-1")
            manager = BootstrapManager(session=eu_session)
            s3_client = eu_session.client("s3")

            # Mock the new methods to avoid CloudFormation calls
            monkeypatch.setattr(manager, "_upload_lambda_functions", lambda bucket_name: None)
            monkeypatch.setattr(manager, "_upload_template", lambda bucket_name: "test-key")
            monkeypatch.setattr(manager, "_deploy_stack", lambda bucket_name, template_key: None)

            manager.setup()

            response = s3_client.head_bucket(Bucket="plldb-core-infrastructure-eu-west-1-123456789012")
            assert response["ResponseMetadata"]["HTTPStatusCode"] == 200

    def test_destroy_removes_bucket_and_contents(self, mock_aws_session, monkeypatch):
        manager = BootstrapManager(session=mock_aws_session)
        s3_client = mock_aws_session.client("s3")

        s3_client.create_bucket(Bucket="plldb-core-infrastructure-us-east-1-123456789012")
        s3_client.put_object(
            Bucket="plldb-core-infrastructure-us-east-1-123456789012",
            Key="test-object.txt",
            Body=b"test content",
        )

        # Mock the CloudFormation operations
        def mock_describe_stacks(**kwargs):
            raise ClientError({"Error": {"Code": "ValidationError", "Message": "Stack does not exist"}}, "DescribeStacks")

        class MockWaiter:
            def wait(self, **kwargs):
                pass

        def mock_get_waiter(waiter_name):
            return MockWaiter()

        monkeypatch.setattr(manager.cloudformation_client, "describe_stacks", mock_describe_stacks)
        monkeypatch.setattr(manager.cloudformation_client, "delete_stack", lambda **kwargs: None)
        monkeypatch.setattr(manager.cloudformation_client, "get_waiter", mock_get_waiter)

        manager.destroy()

        with pytest.raises(ClientError) as exc_info:
            s3_client.head_bucket(Bucket="plldb-core-infrastructure-us-east-1-123456789012")
        assert exc_info.value.response["Error"]["Code"] == "404"

    def test_destroy_idempotent_when_bucket_not_exists(self, mock_aws_session, monkeypatch):
        manager = BootstrapManager(session=mock_aws_session)

        # Mock the CloudFormation operations
        def mock_describe_stacks(**kwargs):
            raise ClientError({"Error": {"Code": "ValidationError", "Message": "Stack does not exist"}}, "DescribeStacks")

        class MockWaiter:
            def wait(self, **kwargs):
                pass

        def mock_get_waiter(waiter_name):
            return MockWaiter()

        monkeypatch.setattr(manager.cloudformation_client, "describe_stacks", mock_describe_stacks)
        monkeypatch.setattr(manager.cloudformation_client, "delete_stack", lambda **kwargs: None)
        monkeypatch.setattr(manager.cloudformation_client, "get_waiter", mock_get_waiter)

        manager.destroy()

    def test_destroy_handles_multiple_objects(self, mock_aws_session, monkeypatch):
        manager = BootstrapManager(session=mock_aws_session)
        s3_client = mock_aws_session.client("s3")

        s3_client.create_bucket(Bucket="plldb-core-infrastructure-us-east-1-123456789012")

        for i in range(10):
            s3_client.put_object(
                Bucket="plldb-core-infrastructure-us-east-1-123456789012",
                Key=f"test-object-{i}.txt",
                Body=b"test content",
            )

        # Mock the CloudFormation operations
        def mock_describe_stacks(**kwargs):
            raise ClientError({"Error": {"Code": "ValidationError", "Message": "Stack does not exist"}}, "DescribeStacks")

        class MockWaiter:
            def wait(self, **kwargs):
                pass

        def mock_get_waiter(waiter_name):
            return MockWaiter()

        monkeypatch.setattr(manager.cloudformation_client, "describe_stacks", mock_describe_stacks)
        monkeypatch.setattr(manager.cloudformation_client, "delete_stack", lambda **kwargs: None)
        monkeypatch.setattr(manager.cloudformation_client, "get_waiter", mock_get_waiter)

        manager.destroy()

        with pytest.raises(ClientError) as exc_info:
            s3_client.head_bucket(Bucket="plldb-core-infrastructure-us-east-1-123456789012")
        assert exc_info.value.response["Error"]["Code"] == "404"
