import json
import time

from plldb.cloudformation.lambda_functions.restapi import lambda_handler


class TestRestApiLambda:
    def test_create_session_success(self, mock_aws_session):
        # Setup DynamoDB table
        dynamodb = mock_aws_session.resource("dynamodb")
        dynamodb.create_table(
            TableName="PLLDBSessions",
            KeySchema=[{"AttributeName": "SessionId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "SessionId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        # Test event
        event = {"httpMethod": "POST", "path": "/sessions", "body": json.dumps({"stackName": "test-stack"})}

        # Call handler
        response = lambda_handler(event, None)

        # Verify response
        assert response["statusCode"] == 201
        body = json.loads(response["body"])
        assert "sessionId" in body
        assert len(body["sessionId"]) > 0

        # Verify item was created in DynamoDB
        table = dynamodb.Table("PLLDBSessions")
        item = table.get_item(Key={"SessionId": body["sessionId"]})["Item"]
        assert item["StackName"] == "test-stack"
        assert item["Status"] == "PENDING"
        assert item["TTL"] > int(time.time())
        assert item["TTL"] <= int(time.time()) + 3600

    def test_create_session_missing_stack_name(self, mock_aws_session):
        # Setup DynamoDB table
        dynamodb = mock_aws_session.resource("dynamodb")
        dynamodb.create_table(
            TableName="PLLDBSessions",
            KeySchema=[{"AttributeName": "SessionId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "SessionId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        # Test event without stackName
        event = {"httpMethod": "POST", "path": "/sessions", "body": json.dumps({})}

        # Call handler
        response = lambda_handler(event, None)

        # Verify response
        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["error"] == "stackName is required"

    def test_create_session_invalid_json(self, mock_aws_session):
        # Setup DynamoDB table (needed as boto3 resource is created at module level)
        dynamodb = mock_aws_session.resource("dynamodb")
        dynamodb.create_table(
            TableName="PLLDBSessions",
            KeySchema=[{"AttributeName": "SessionId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "SessionId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        # Test event with invalid JSON
        event = {"httpMethod": "POST", "path": "/sessions", "body": "invalid json"}

        # Call handler
        response = lambda_handler(event, None)

        # Verify response
        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert "error" in body

    def test_not_found_route(self, mock_aws_session):
        # Setup DynamoDB table (needed as boto3 resource is created at module level)
        dynamodb = mock_aws_session.resource("dynamodb")
        dynamodb.create_table(
            TableName="PLLDBSessions",
            KeySchema=[{"AttributeName": "SessionId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "SessionId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        # Test event for non-existent route
        event = {"httpMethod": "GET", "path": "/invalid", "body": "{}"}

        # Call handler
        response = lambda_handler(event, None)

        # Verify response
        assert response["statusCode"] == 404
        body = json.loads(response["body"])
        assert body["error"] == "Not Found"
