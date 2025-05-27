import boto3


class TestAWSResources:
    def test_dynamodb_table(self, mock_aws_session: boto3.Session) -> None:
        ddb = mock_aws_session.client("dynamodb")
        ddb.create_table(
            TableName="test-table",
            KeySchema=[
                {"AttributeName": "id", "KeyType": "HASH"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "id", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        waiter = ddb.get_waiter("table_exists")
        waiter.wait(TableName="test-table")
        ddb.delete_table(TableName="test-table")
