import yaml
from pathlib import Path


class CloudFormationYAMLLoader(yaml.SafeLoader):
    """Custom YAML loader that handles CloudFormation intrinsic functions."""

    pass


def cfn_constructor(loader, node):
    """Constructor for CloudFormation intrinsic functions."""
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    elif isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)


# Register CloudFormation intrinsic functions
for fn in ["!Ref", "!GetAtt", "!Sub", "!Join", "!Select", "!Split", "!Base64", "!If", "!Not", "!Equals", "!And", "!Or", "!FindInMap", "!ImportValue"]:
    CloudFormationYAMLLoader.add_constructor(fn, cfn_constructor)


class TestCloudFormationTemplate:
    """Test CloudFormation template structure and resources."""

    def test_template_resources_exist(self):
        """Verify that all required resources are defined in the template."""
        template_path = Path(__file__).parent.parent / "plldb" / "cloudformation" / "template.yaml"

        with open(template_path, "r") as f:
            template = yaml.load(f, Loader=CloudFormationYAMLLoader)

        # Check that Resources section exists
        assert "Resources" in template
        resources = template["Resources"]

        # Check for PLLDBDebugger table
        assert "PLLDBDebugger" in resources
        debugger_table = resources["PLLDBDebugger"]
        assert debugger_table["Type"] == "AWS::DynamoDB::Table"
        assert debugger_table["Properties"]["TableName"] == "PLLDBDebugger"

        # Check table attributes
        attributes = {attr["AttributeName"] for attr in debugger_table["Properties"]["AttributeDefinitions"]}
        assert "RequestId" in attributes
        assert "SessionId" in attributes
        assert "ConnectionId" in attributes

        # Check key schema
        assert debugger_table["Properties"]["KeySchema"][0]["AttributeName"] == "RequestId"
        assert debugger_table["Properties"]["KeySchema"][0]["KeyType"] == "HASH"

        # Check GSIs
        gsi_names = {idx["IndexName"] for idx in debugger_table["Properties"]["GlobalSecondaryIndexes"]}
        assert "GSI-SessionId" in gsi_names
        assert "GSI-ConnectionId" in gsi_names

        # Check for PLLDBDebuggerRole
        assert "PLLDBDebuggerRole" in resources
        debugger_role = resources["PLLDBDebuggerRole"]
        assert debugger_role["Type"] == "AWS::IAM::Role"
        assert debugger_role["Properties"]["RoleName"] == "PLLDBDebuggerRole"

        # Check assume role policy
        assume_policy = debugger_role["Properties"]["AssumeRolePolicyDocument"]
        assert assume_policy["Version"] == "2012-10-17"

        # Check that Lambda service can assume the role
        principals = [stmt["Principal"] for stmt in assume_policy["Statement"]]
        assert any("lambda.amazonaws.com" in str(p.get("Service", "")) for p in principals)

        # Check that AWS account root can assume the role
        assert any("AWS" in p for p in principals)

        # Check policies
        policies = debugger_role["Properties"]["Policies"]
        assert len(policies) == 1
        assert policies[0]["PolicyName"] == "PLLDBDebuggerPolicy"

        # Check policy permissions
        statements = policies[0]["PolicyDocument"]["Statement"]

        # Check DynamoDB permissions
        dynamodb_stmt = next(s for s in statements if "dynamodb:" in str(s["Action"]))
        assert "dynamodb:PutItem" in dynamodb_stmt["Action"]
        assert "dynamodb:GetItem" in dynamodb_stmt["Action"]
        assert "dynamodb:UpdateItem" in dynamodb_stmt["Action"]
        assert "dynamodb:DeleteItem" in dynamodb_stmt["Action"]
        assert "dynamodb:Query" in dynamodb_stmt["Action"]
        assert "dynamodb:Scan" in dynamodb_stmt["Action"]

        # Check WebSocket API permissions
        api_stmt = next(s for s in statements if "execute-api:" in str(s["Action"]))
        assert "execute-api:ManageConnections" in api_stmt["Action"]

    def test_debugger_role_can_access_debugger_table(self):
        """Verify that PLLDBDebuggerRole has proper access to PLLDBDebugger table."""
        template_path = Path(__file__).parent.parent / "plldb" / "cloudformation" / "template.yaml"

        with open(template_path, "r") as f:
            template = yaml.load(f, Loader=CloudFormationYAMLLoader)

        resources = template["Resources"]
        debugger_role = resources["PLLDBDebuggerRole"]

        # Find the DynamoDB policy statement
        policies = debugger_role["Properties"]["Policies"]
        dynamodb_stmt = None
        for stmt in policies[0]["PolicyDocument"]["Statement"]:
            if "dynamodb:" in str(stmt["Action"]):
                dynamodb_stmt = stmt
                break

        assert dynamodb_stmt is not None

        # Check that it references the PLLDBDebugger table
        resources_in_policy = dynamodb_stmt["Resource"]
        assert any("PLLDBDebugger.Arn" in str(r) for r in resources_in_policy)
        assert any("PLLDBDebugger.Arn}/index/*" in str(r) for r in resources_in_policy)

    def test_existing_resources_still_present(self):
        """Verify that existing resources are not affected by new additions."""
        template_path = Path(__file__).parent.parent / "plldb" / "cloudformation" / "template.yaml"

        with open(template_path, "r") as f:
            template = yaml.load(f, Loader=CloudFormationYAMLLoader)

        resources = template["Resources"]

        # Check existing resources are still present
        existing_resources = [
            "PLLDBSessions",
            "PLLDBServiceRole",
            "PLLDBWebSocketConnectFunction",
            "PLLDBWebSocketDisconnectFunction",
            "PLLDBWebSocketAuthorizeFunction",
            "PLLDBWebSocketDefaultFunction",
            "PLLDBRestApiFunction",
            "PLLDBDebuggerInstrumentationFunction",
            "PLLDBWebSocketAPI",
            "PLLDBAPI",
        ]

        for resource in existing_resources:
            assert resource in resources, f"Expected resource {resource} not found in template"

    def test_service_role_has_websocket_permissions(self):
        """Verify that PLLDBServiceRole has permissions to manage WebSocket connections."""
        template_path = Path(__file__).parent.parent / "plldb" / "cloudformation" / "template.yaml"

        with open(template_path, "r") as f:
            template = yaml.load(f, Loader=CloudFormationYAMLLoader)

        resources = template["Resources"]
        service_role = resources["PLLDBServiceRole"]

        # Find the execute-api policy statement
        policies = service_role["Properties"]["Policies"]
        api_stmt = None
        for stmt in policies[0]["PolicyDocument"]["Statement"]:
            if "execute-api:" in str(stmt.get("Action", [])):
                api_stmt = stmt
                break

        assert api_stmt is not None, "PLLDBServiceRole should have execute-api permissions"
        assert "execute-api:ManageConnections" in api_stmt["Action"]

        # Check that it references the WebSocket API
        resources_in_policy = api_stmt["Resource"]
        assert any("PLLDBWebSocketAPI" in str(r) for r in resources_in_policy)
