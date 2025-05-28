import json
from unittest.mock import Mock, patch

import pytest

from plldb.cloudformation.lambda_functions.websocket_default import lambda_handler, handle_debugger_response


class TestWebSocketDefault:
    def test_lambda_handler_with_debugger_response(self):
        """Test handling debugger response message."""
        event = {"body": json.dumps({"requestId": "test-request-id", "statusCode": 200, "response": "test-response"})}

        with patch("plldb.cloudformation.lambda_functions.websocket_default.boto3") as mock_boto3:
            # Mock DynamoDB
            mock_table = Mock()
            mock_boto3.resource.return_value.Table.return_value = mock_table

            result = lambda_handler(event, None)

            assert result["statusCode"] == 200
            body = json.loads(result["body"])
            assert body["message"] == "Response stored successfully"

            # Verify DynamoDB update was called
            mock_table.update_item.assert_called_once()
            call_args = mock_table.update_item.call_args[1]
            assert call_args["Key"]["RequestId"] == "test-request-id"
            assert ":resp" in call_args["ExpressionAttributeValues"]
            assert call_args["ExpressionAttributeValues"][":resp"] == "test-response"
            assert call_args["ExpressionAttributeValues"][":status"] == 200

    def test_lambda_handler_with_debugger_response_and_error(self):
        """Test handling debugger response with error message."""
        event = {"body": json.dumps({"requestId": "test-request-id", "statusCode": 500, "response": "", "errorMessage": "Test error"})}

        with patch("plldb.cloudformation.lambda_functions.websocket_default.boto3") as mock_boto3:
            # Mock DynamoDB
            mock_table = Mock()
            mock_boto3.resource.return_value.Table.return_value = mock_table

            result = lambda_handler(event, None)

            assert result["statusCode"] == 200

            # Verify DynamoDB update included error message
            call_args = mock_table.update_item.call_args[1]
            assert ":error" in call_args["ExpressionAttributeValues"]
            assert call_args["ExpressionAttributeValues"][":error"] == "Test error"

    def test_lambda_handler_invalid_json(self):
        """Test handling invalid JSON in body."""
        event = {"body": "invalid json"}

        result = lambda_handler(event, None)

        assert result["statusCode"] == 400
        body = json.loads(result["body"])
        assert body["error"] == "Invalid JSON in request body"

    def test_lambda_handler_invalid_message_format(self):
        """Test handling message with missing required fields."""
        event = {
            "body": json.dumps(
                {
                    "requestId": "test-request-id"
                    # Missing statusCode and response
                }
            )
        }

        result = lambda_handler(event, None)

        assert result["statusCode"] == 400
        body = json.loads(result["body"])
        assert body["error"] == "Invalid message format"

    def test_lambda_handler_dynamodb_error(self):
        """Test handling DynamoDB errors."""
        event = {"body": json.dumps({"requestId": "test-request-id", "statusCode": 200, "response": "test-response"})}

        with patch("plldb.cloudformation.lambda_functions.websocket_default.boto3") as mock_boto3:
            # Mock DynamoDB to raise error
            mock_table = Mock()
            mock_table.update_item.side_effect = Exception("DynamoDB error")
            mock_boto3.resource.return_value.Table.return_value = mock_table

            result = lambda_handler(event, None)

            assert result["statusCode"] == 500
            body = json.loads(result["body"])
            assert "Failed to store response" in body["error"]

    def test_handle_debugger_response_success(self):
        """Test successful debugger response handling."""
        body = {"requestId": "test-request-id", "statusCode": 200, "response": "test-response"}

        with patch("plldb.cloudformation.lambda_functions.websocket_default.boto3") as mock_boto3:
            # Mock DynamoDB
            mock_table = Mock()
            mock_boto3.resource.return_value.Table.return_value = mock_table

            result = handle_debugger_response(body)

            assert result["statusCode"] == 200

            # Verify correct update expression
            call_args = mock_table.update_item.call_args[1]
            assert call_args["UpdateExpression"] == "SET #resp = :resp, StatusCode = :status"
            assert call_args["ExpressionAttributeNames"]["#resp"] == "Response"
