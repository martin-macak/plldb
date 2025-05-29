import pytest
from unittest.mock import MagicMock
from plldb.debugger import Debugger


class TestDebugger:
    def test_inspect_stack(self, mock_aws_session):
        # Mock CloudFormation client
        mock_cfn_client = MagicMock()
        mock_aws_session.client = MagicMock(return_value=mock_cfn_client)

        # Mock paginator
        mock_paginator = MagicMock()
        mock_cfn_client.get_paginator.return_value = mock_paginator

        # Mock list_stack_resources response
        mock_paginator.paginate.return_value = [
            {
                "StackResourceSummaries": [
                    {"ResourceType": "AWS::Lambda::Function", "LogicalResourceId": "MyLambdaFunction", "PhysicalResourceId": "my-function-xyz123"},
                    {"ResourceType": "AWS::Lambda::Function", "LogicalResourceId": "AnotherLambda", "PhysicalResourceId": "another-function-abc456"},
                    {"ResourceType": "AWS::S3::Bucket", "LogicalResourceId": "NotALambda", "PhysicalResourceId": "my-bucket-123"},
                ]
            }
        ]

        # Create debugger instance
        debugger = Debugger(session=mock_aws_session, stack_name="test-stack")

        # Verify CloudFormation client was called correctly
        mock_aws_session.client.assert_called_with("cloudformation")
        mock_cfn_client.get_paginator.assert_called_once_with("list_stack_resources")
        mock_paginator.paginate.assert_called_once_with(StackName="test-stack")

        # Verify the lookup table was built correctly (PhysicalResourceId -> LogicalResourceId)
        assert debugger._lambda_functions_lookup == {"my-function-xyz123": "MyLambdaFunction", "another-function-abc456": "AnotherLambda"}

    def test_inspect_stack_no_lambda_functions(self, mock_aws_session):
        # Mock CloudFormation client
        mock_cfn_client = MagicMock()
        mock_aws_session.client = MagicMock(return_value=mock_cfn_client)

        # Mock paginator
        mock_paginator = MagicMock()
        mock_cfn_client.get_paginator.return_value = mock_paginator

        # Mock list_stack_resources response without Lambda functions
        mock_paginator.paginate.return_value = [{"StackResourceSummaries": [{"ResourceType": "AWS::S3::Bucket", "LogicalResourceId": "MyBucket", "PhysicalResourceId": "my-bucket-123"}]}]

        # Create debugger instance
        debugger = Debugger(session=mock_aws_session, stack_name="test-stack")

        # Verify the lookup table is empty
        assert debugger._lambda_functions_lookup == {}

    def test_inspect_stack_lambda_without_physical_id(self, mock_aws_session):
        # Mock CloudFormation client
        mock_cfn_client = MagicMock()
        mock_aws_session.client = MagicMock(return_value=mock_cfn_client)

        # Mock paginator
        mock_paginator = MagicMock()
        mock_cfn_client.get_paginator.return_value = mock_paginator

        # Mock list_stack_resources response with Lambda without PhysicalResourceId
        mock_paginator.paginate.return_value = [
            {
                "StackResourceSummaries": [
                    {
                        "ResourceType": "AWS::Lambda::Function",
                        "LogicalResourceId": "MyLambdaFunction",
                        # No PhysicalResourceId
                    }
                ]
            }
        ]

        # Create debugger instance
        debugger = Debugger(session=mock_aws_session, stack_name="test-stack")

        # Verify the lookup table is empty (no physical ID to map)
        assert debugger._lambda_functions_lookup == {}

    def test_inspect_stack_multiple_pages(self, mock_aws_session):
        # Mock CloudFormation client
        mock_cfn_client = MagicMock()
        mock_aws_session.client = MagicMock(return_value=mock_cfn_client)

        # Mock paginator
        mock_paginator = MagicMock()
        mock_cfn_client.get_paginator.return_value = mock_paginator

        # Mock list_stack_resources response with multiple pages
        mock_paginator.paginate.return_value = [
            {"StackResourceSummaries": [{"ResourceType": "AWS::Lambda::Function", "LogicalResourceId": "Lambda1", "PhysicalResourceId": "function-1"}]},
            {"StackResourceSummaries": [{"ResourceType": "AWS::Lambda::Function", "LogicalResourceId": "Lambda2", "PhysicalResourceId": "function-2"}]},
        ]

        # Create debugger instance
        debugger = Debugger(session=mock_aws_session, stack_name="test-stack")

        # Verify the lookup table contains both functions
        assert debugger._lambda_functions_lookup == {"function-1": "Lambda1", "function-2": "Lambda2"}
