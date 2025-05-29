import os
import tempfile
import zipfile

import pytest
from botocore.exceptions import ClientError

from plldb.setup import BootstrapManager


class TestBootstrapManager:
    def test_init(self, mock_aws_session):
        manager = BootstrapManager(mock_aws_session)
        assert manager.session == mock_aws_session
        assert manager.s3_client is not None
        assert manager.sts_client is not None
        assert manager.cloudformation_client is not None
        assert isinstance(manager.package_version, str)
        assert len(manager.package_version) > 0

    def test_get_bucket_name(self, mock_aws_session):
        manager = BootstrapManager(mock_aws_session)

        bucket_name = manager._get_bucket_name()
        assert bucket_name.startswith("plldb-core-infrastructure-")
        assert "123456789012" in bucket_name

    def test_get_s3_key_prefix(self, mock_aws_session):
        manager = BootstrapManager(mock_aws_session)
        prefix = manager._get_s3_key_prefix()
        assert prefix.startswith("plldb/versions/")
        assert len(prefix) > len("plldb/versions/")

    def test_package_lambda_function(self, mock_aws_session):
        manager = BootstrapManager(mock_aws_session)

        # Test with real lambda function that exists
        zip_content = manager._package_lambda_function("websocket_connect")

        with tempfile.NamedTemporaryFile(mode="wb", suffix=".zip", delete=False) as f:
            f.write(zip_content)
            f.flush()

            with zipfile.ZipFile(f.name, "r") as zipf:
                assert "websocket_connect.py" in zipf.namelist()
                content = zipf.read("websocket_connect.py").decode()
                assert "def lambda_handler" in content

        os.unlink(f.name)

    def test_package_lambda_function_not_found(self, mock_aws_session):
        manager = BootstrapManager(mock_aws_session)

        with pytest.raises(FileNotFoundError, match="Lambda function nonexistent.py not found"):
            manager._package_lambda_function("nonexistent")

    def test_upload_lambda_functions(self, mock_aws_session, monkeypatch):
        manager = BootstrapManager(mock_aws_session)

        # Create bucket first
        manager.s3_client.create_bucket(Bucket="test-bucket")

        # Mock the _package_lambda_function method
        call_args = []

        def mock_package(func_name):
            call_args.append(func_name)
            return b"mock zip content"

        monkeypatch.setattr(manager, "_package_lambda_function", mock_package)

        manager._upload_lambda_functions("test-bucket")

        assert len(call_args) == 6
        assert "websocket_connect" in call_args
        assert "websocket_disconnect" in call_args
        assert "websocket_authorize" in call_args
        assert "websocket_default" in call_args
        assert "restapi" in call_args
        assert "debugger_instrumentation" in call_args

        # Verify files were uploaded
        response = manager.s3_client.list_objects_v2(Bucket="test-bucket")
        assert response["KeyCount"] == 6

    def test_upload_template(self, mock_aws_session):
        manager = BootstrapManager(mock_aws_session)

        # Create bucket first
        manager.s3_client.create_bucket(Bucket="test-bucket")

        s3_key = manager._upload_template("test-bucket")

        assert s3_key.startswith("plldb/versions/")
        assert s3_key.endswith("/template.yaml")

        # Verify file was uploaded
        response = manager.s3_client.get_object(Bucket="test-bucket", Key=s3_key)
        content = response["Body"].read().decode("utf-8")
        assert "AWSTemplateFormatVersion" in content

    def test_deploy_stack_parameters(self, mock_aws_session, monkeypatch):
        manager = BootstrapManager(mock_aws_session)

        # Test that the method builds the correct parameters
        create_stack_calls = []

        def mock_describe_stacks(**kwargs):
            raise ClientError({"Error": {"Code": "ValidationError", "Message": "Stack does not exist"}}, "DescribeStacks")

        def mock_create_stack(**kwargs):
            create_stack_calls.append(kwargs)
            return {}

        class MockWaiter:
            def wait(self, **kwargs):
                pass

        def mock_get_waiter(waiter_name):
            return MockWaiter()

        monkeypatch.setattr(manager.cloudformation_client, "describe_stacks", mock_describe_stacks)
        monkeypatch.setattr(manager.cloudformation_client, "create_stack", mock_create_stack)
        monkeypatch.setattr(manager.cloudformation_client, "get_waiter", mock_get_waiter)

        template_key = f"{manager._get_s3_key_prefix()}/template.yaml"
        manager._deploy_stack("test-bucket", template_key)

        assert len(create_stack_calls) == 1
        assert create_stack_calls[0]["StackName"] == "plldb"
        assert create_stack_calls[0]["TemplateURL"] == f"https://test-bucket.s3.amazonaws.com/{template_key}"
        assert create_stack_calls[0]["Capabilities"] == ["CAPABILITY_IAM", "CAPABILITY_AUTO_EXPAND", "CAPABILITY_NAMED_IAM"]

    def test_deploy_stack_update_parameters(self, mock_aws_session, monkeypatch):
        manager = BootstrapManager(mock_aws_session)

        # Test update stack parameters
        update_stack_calls = []

        def mock_describe_stacks(**kwargs):
            return {"Stacks": [{"StackName": "plldb"}]}

        def mock_update_stack(**kwargs):
            update_stack_calls.append(kwargs)
            return {}

        class MockWaiter:
            def wait(self, **kwargs):
                pass

        def mock_get_waiter(waiter_name):
            return MockWaiter()

        monkeypatch.setattr(manager.cloudformation_client, "describe_stacks", mock_describe_stacks)
        monkeypatch.setattr(manager.cloudformation_client, "update_stack", mock_update_stack)
        monkeypatch.setattr(manager.cloudformation_client, "get_waiter", mock_get_waiter)

        template_key = f"{manager._get_s3_key_prefix()}/template.yaml"
        manager._deploy_stack("test-bucket", template_key)

        assert len(update_stack_calls) == 1
        assert update_stack_calls[0]["StackName"] == "plldb"
        assert update_stack_calls[0]["TemplateURL"] == f"https://test-bucket.s3.amazonaws.com/{template_key}"
        assert update_stack_calls[0]["Capabilities"] == ["CAPABILITY_IAM", "CAPABILITY_AUTO_EXPAND", "CAPABILITY_NAMED_IAM"]

    def test_destroy_stack_calls(self, mock_aws_session, monkeypatch):
        manager = BootstrapManager(mock_aws_session)

        # Test destroy stack calls
        delete_stack_calls = []
        delete_bucket_calls = []

        def mock_describe_stacks(**kwargs):
            return {"Stacks": [{"StackName": "plldb"}]}

        def mock_delete_stack(**kwargs):
            delete_stack_calls.append(kwargs)
            return {}

        class MockWaiter:
            def wait(self, **kwargs):
                pass

        def mock_get_waiter(waiter_name):
            return MockWaiter()

        def mock_head_bucket(**kwargs):
            return {}

        class MockPaginator:
            def paginate(self, **kwargs):
                return []

        def mock_get_paginator(operation_name):
            return MockPaginator()

        def mock_delete_bucket(**kwargs):
            delete_bucket_calls.append(kwargs)
            return {}

        monkeypatch.setattr(manager.cloudformation_client, "describe_stacks", mock_describe_stacks)
        monkeypatch.setattr(manager.cloudformation_client, "delete_stack", mock_delete_stack)
        monkeypatch.setattr(manager.cloudformation_client, "get_waiter", mock_get_waiter)
        monkeypatch.setattr(manager.s3_client, "head_bucket", mock_head_bucket)
        monkeypatch.setattr(manager.s3_client, "get_paginator", mock_get_paginator)
        monkeypatch.setattr(manager.s3_client, "delete_bucket", mock_delete_bucket)

        manager.destroy()

        assert len(delete_stack_calls) == 1
        assert delete_stack_calls[0] == {"StackName": "plldb"}
        assert len(delete_bucket_calls) == 1

    def test_destroy_no_stack_calls(self, mock_aws_session, monkeypatch):
        manager = BootstrapManager(mock_aws_session)

        # Test destroy when no stack exists
        delete_stack_calls = []
        delete_bucket_calls = []

        def mock_describe_stacks(**kwargs):
            raise ClientError({"Error": {"Code": "ValidationError", "Message": "Stack does not exist"}}, "DescribeStacks")

        def mock_delete_stack(**kwargs):
            delete_stack_calls.append(kwargs)
            return {}

        class MockWaiter:
            def wait(self, **kwargs):
                pass

        def mock_get_waiter(waiter_name):
            return MockWaiter()

        def mock_head_bucket(**kwargs):
            return {}

        class MockPaginator:
            def paginate(self, **kwargs):
                return []

        def mock_get_paginator(operation_name):
            return MockPaginator()

        def mock_delete_bucket(**kwargs):
            delete_bucket_calls.append(kwargs)
            return {}

        monkeypatch.setattr(manager.cloudformation_client, "describe_stacks", mock_describe_stacks)
        monkeypatch.setattr(manager.cloudformation_client, "delete_stack", mock_delete_stack)
        monkeypatch.setattr(manager.cloudformation_client, "get_waiter", mock_get_waiter)
        monkeypatch.setattr(manager.s3_client, "head_bucket", mock_head_bucket)
        monkeypatch.setattr(manager.s3_client, "get_paginator", mock_get_paginator)
        monkeypatch.setattr(manager.s3_client, "delete_bucket", mock_delete_bucket)

        manager.destroy()

        assert len(delete_stack_calls) == 0
        assert len(delete_bucket_calls) == 1
