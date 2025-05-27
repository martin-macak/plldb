import os
import tempfile
import zipfile
from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError

from plldb.bootstrap.setup import BootstrapManager


class TestBootstrapManager:
    def test_init(self, mock_aws_session):
        manager = BootstrapManager(mock_aws_session)
        assert manager.session == mock_aws_session
        assert manager.s3_client is not None
        assert manager.sts_client is not None
        assert manager.cloudformation_client is not None
        assert manager.package_version == "0.1.0"

    def test_get_bucket_name(self, mock_aws_session):
        manager = BootstrapManager(mock_aws_session)

        bucket_name = manager._get_bucket_name()
        assert bucket_name.startswith("plldb-core-infrastructure-")
        assert "123456789012" in bucket_name

    def test_get_s3_key_prefix(self, mock_aws_session):
        manager = BootstrapManager(mock_aws_session)
        assert manager._get_s3_key_prefix() == "plldb/versions/0.1.0"

    def test_package_lambda_function(self, mock_aws_session):
        manager = BootstrapManager(mock_aws_session)

        # Test with real lambda function that exists
        zip_content = manager._package_lambda_function("connect")

        with tempfile.NamedTemporaryFile(mode="wb", suffix=".zip", delete=False) as f:
            f.write(zip_content)
            f.flush()

            with zipfile.ZipFile(f.name, "r") as zipf:
                assert "connect.py" in zipf.namelist()
                content = zipf.read("connect.py").decode()
                assert "def handler" in content

        os.unlink(f.name)

    def test_package_lambda_function_not_found(self, mock_aws_session):
        manager = BootstrapManager(mock_aws_session)

        with pytest.raises(FileNotFoundError, match="Lambda function nonexistent.py not found"):
            manager._package_lambda_function("nonexistent")

    def test_upload_lambda_functions(self, mock_aws_session):
        manager = BootstrapManager(mock_aws_session)

        # Create bucket first
        manager.s3_client.create_bucket(Bucket="test-bucket")

        with patch.object(manager, "_package_lambda_function") as mock_package:
            mock_package.return_value = b"mock zip content"

            manager._upload_lambda_functions("test-bucket")

            assert mock_package.call_count == 4
            mock_package.assert_any_call("connect")
            mock_package.assert_any_call("disconnect")
            mock_package.assert_any_call("authorize")
            mock_package.assert_any_call("default")

            # Verify files were uploaded
            response = manager.s3_client.list_objects_v2(Bucket="test-bucket")
            assert response["KeyCount"] == 4

    def test_upload_template(self, mock_aws_session):
        manager = BootstrapManager(mock_aws_session)

        # Create bucket first
        manager.s3_client.create_bucket(Bucket="test-bucket")

        s3_key = manager._upload_template("test-bucket")

        assert s3_key == "plldb/versions/0.1.0/template.yaml"

        # Verify file was uploaded
        response = manager.s3_client.get_object(Bucket="test-bucket", Key=s3_key)
        content = response["Body"].read().decode("utf-8")
        assert "AWSTemplateFormatVersion" in content

    def test_deploy_stack_parameters(self, mock_aws_session):
        manager = BootstrapManager(mock_aws_session)

        # Test that the method builds the correct parameters
        with patch.object(manager.cloudformation_client, "describe_stacks") as mock_describe:
            with patch.object(manager.cloudformation_client, "create_stack") as mock_create:
                with patch.object(manager.cloudformation_client, "get_waiter") as mock_waiter:
                    mock_describe.side_effect = ClientError({"Error": {"Code": "ValidationError", "Message": "Stack does not exist"}}, "DescribeStacks")
                    mock_waiter.return_value.wait.return_value = None

                    manager._deploy_stack("test-bucket", "plldb/versions/0.1.0/template.yaml")

                    mock_create.assert_called_once()
                    args = mock_create.call_args
                    assert args[1]["StackName"] == "plldb"
                    assert args[1]["TemplateURL"] == "https://test-bucket.s3.amazonaws.com/plldb/versions/0.1.0/template.yaml"
                    assert args[1]["Capabilities"] == ["CAPABILITY_IAM"]

    def test_deploy_stack_update_parameters(self, mock_aws_session):
        manager = BootstrapManager(mock_aws_session)

        # Test update stack parameters
        with patch.object(manager.cloudformation_client, "describe_stacks") as mock_describe:
            with patch.object(manager.cloudformation_client, "update_stack") as mock_update:
                with patch.object(manager.cloudformation_client, "get_waiter") as mock_waiter:
                    mock_describe.return_value = {"Stacks": [{"StackName": "plldb"}]}
                    mock_waiter.return_value.wait.return_value = None

                    manager._deploy_stack("test-bucket", "plldb/versions/0.1.0/template.yaml")

                    mock_update.assert_called_once()
                    args = mock_update.call_args
                    assert args[1]["StackName"] == "plldb"
                    assert args[1]["TemplateURL"] == "https://test-bucket.s3.amazonaws.com/plldb/versions/0.1.0/template.yaml"
                    assert args[1]["Capabilities"] == ["CAPABILITY_IAM"]

    def test_destroy_stack_calls(self, mock_aws_session):
        manager = BootstrapManager(mock_aws_session)

        # Test destroy stack calls
        with patch.object(manager.cloudformation_client, "describe_stacks") as mock_describe:
            with patch.object(manager.cloudformation_client, "delete_stack") as mock_delete:
                with patch.object(manager.cloudformation_client, "get_waiter") as mock_waiter:
                    with patch.object(manager.s3_client, "head_bucket") as mock_head:
                        with patch.object(manager.s3_client, "get_paginator") as mock_paginator:
                            with patch.object(manager.s3_client, "delete_bucket") as mock_delete_bucket:
                                mock_describe.return_value = {"Stacks": [{"StackName": "plldb"}]}
                                mock_waiter.return_value.wait.return_value = None
                                mock_head.return_value = {}
                                mock_paginator.return_value.paginate.return_value = []

                                manager.destroy()

                                mock_delete.assert_called_once_with(StackName="plldb")
                                mock_delete_bucket.assert_called_once()

    def test_destroy_no_stack_calls(self, mock_aws_session):
        manager = BootstrapManager(mock_aws_session)

        # Test destroy when no stack exists
        with patch.object(manager.cloudformation_client, "describe_stacks") as mock_describe:
            with patch.object(manager.cloudformation_client, "delete_stack") as mock_delete:
                with patch.object(manager.cloudformation_client, "get_waiter") as mock_waiter:
                    with patch.object(manager.s3_client, "head_bucket") as mock_head:
                        with patch.object(manager.s3_client, "get_paginator") as mock_paginator:
                            with patch.object(manager.s3_client, "delete_bucket") as mock_delete_bucket:
                                mock_describe.side_effect = ClientError({"Error": {"Code": "ValidationError", "Message": "Stack does not exist"}}, "DescribeStacks")
                                mock_waiter.return_value.wait.return_value = None
                                mock_head.return_value = {}
                                mock_paginator.return_value.paginate.return_value = []

                                manager.destroy()

                                mock_delete.assert_not_called()
                                mock_delete_bucket.assert_called_once()
