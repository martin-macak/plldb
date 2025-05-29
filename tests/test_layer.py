import os
import tempfile
import zipfile
from pathlib import Path

from plldb.setup import BootstrapManager


class TestLambdaLayer:
    """Test Lambda layer packaging and upload functionality."""

    def test_layer_files_exist(self):
        """Verify that layer files are present in the codebase."""
        layer_dir = Path(__file__).parent.parent / "plldb" / "cloudformation" / "layer"

        assert layer_dir.exists()
        assert (layer_dir / "bootstrap").exists()
        assert (layer_dir / "lambda_runtime.py").exists()

        # Check bootstrap is executable
        assert os.access(layer_dir / "bootstrap", os.X_OK)

    def test_package_and_upload_layer(self, mock_aws_session, monkeypatch):
        """Test packaging and uploading the Lambda layer."""
        manager = BootstrapManager(mock_aws_session)

        # Create test bucket
        manager.s3_client.create_bucket(Bucket="test-bucket")

        # Track S3 uploads
        uploaded_objects = []

        def mock_put_object(**kwargs):
            uploaded_objects.append(kwargs)
            return {}

        monkeypatch.setattr(manager.s3_client, "put_object", mock_put_object)

        # Execute the layer packaging
        manager._package_and_upload_layer("test-bucket")

        # Verify upload was called
        assert len(uploaded_objects) == 1
        upload = uploaded_objects[0]

        assert upload["Bucket"] == "test-bucket"
        assert "layer/debugger-layer.zip" in upload["Key"]

        # Verify the zip content
        zip_content = upload["Body"]

        with tempfile.NamedTemporaryFile(mode="wb", suffix=".zip", delete=False) as f:
            f.write(zip_content)
            temp_path = f.name

        try:
            with zipfile.ZipFile(temp_path, "r") as zipf:
                namelist = zipf.namelist()

                # Check required files are in the bin/ directory
                assert "bin/bootstrap" in namelist
                assert "bin/lambda_runtime.py" in namelist

                # Verify bootstrap content
                bootstrap_content = zipf.read("bin/bootstrap").decode()
                assert "#!/bin/bash" in bootstrap_content
                assert "lambda_runtime.py" in bootstrap_content
                assert "/opt/bin/lambda_runtime.py" in bootstrap_content

                # Verify lambda_runtime.py content
                runtime_content = zipf.read("bin/lambda_runtime.py").decode()
                assert "def lambda_handler" in runtime_content or "def main" in runtime_content
                assert "DEBUGGER_SESSION_ID" in runtime_content
                assert "DEBUGGER_CONNECTION_ID" in runtime_content
                assert "PLLDBDebuggerRole" in runtime_content
                assert "PLLDBDebugger" in runtime_content

        finally:
            os.unlink(temp_path)

    def test_cloudformation_template_includes_layer(self):
        """Verify that the CloudFormation template includes the layer resource."""
        template_path = Path(__file__).parent.parent / "plldb" / "cloudformation" / "template.yaml"

        # Import the custom loader from our other test
        from tests.test_cloudformation_template import CloudFormationYAMLLoader
        import yaml

        with open(template_path, "r") as f:
            template = yaml.load(f, Loader=CloudFormationYAMLLoader)

        resources = template["Resources"]

        # Check layer resource exists
        assert "PLLDBDebuggerLayer" in resources
        layer = resources["PLLDBDebuggerLayer"]

        assert layer["Type"] == "AWS::Lambda::LayerVersion"
        assert layer["Properties"]["LayerName"] == "PLLDBDebuggerRuntime"

        # Check S3 location
        content = layer["Properties"]["Content"]
        assert "S3Bucket" in content
        assert "S3Key" in content
        assert "layer/debugger-layer.zip" in str(content["S3Key"])

        # Check compatible runtimes
        runtimes = layer["Properties"]["CompatibleRuntimes"]
        assert "python3.13" in runtimes
        assert "python3.12" in runtimes
        assert "python3.11" in runtimes

        # Check layer is in outputs
        assert "DebuggerLayerArn" in template["Outputs"]

    def test_bootstrap_includes_layer_packaging(self, mock_aws_session, monkeypatch):
        """Test that the bootstrap setup process includes layer packaging."""
        manager = BootstrapManager(mock_aws_session)

        # Track method calls
        calls = {"layer": False, "functions": False, "template": False, "deploy": False}

        def mock_upload_lambda_functions(bucket_name):
            calls["functions"] = True

        def mock_package_and_upload_layer(bucket_name):
            calls["layer"] = True

        def mock_upload_template(bucket_name):
            calls["template"] = True
            return "test-key"

        def mock_deploy_stack(bucket_name, template_key):
            calls["deploy"] = True

        monkeypatch.setattr(manager, "_upload_lambda_functions", mock_upload_lambda_functions)
        monkeypatch.setattr(manager, "_package_and_upload_layer", mock_package_and_upload_layer)
        monkeypatch.setattr(manager, "_upload_template", mock_upload_template)
        monkeypatch.setattr(manager, "_deploy_stack", mock_deploy_stack)

        # Create bucket first
        manager.s3_client.create_bucket(Bucket=manager._get_bucket_name())

        # Run setup
        manager.setup()

        # Verify all steps were called
        assert calls["functions"]
        assert calls["layer"]
        assert calls["template"]
        assert calls["deploy"]
