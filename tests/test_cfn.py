import pytest
from plldb.util.cfn import (
    load_yaml,
    RefTag,
    GetAttTag,
    SubTag,
    JoinTag,
    SplitTag,
    SelectTag,
    FindInMapTag,
    Base64Tag,
    CidrTag,
    ImportValueTag,
    GetAZsTag,
)

# Test data for valid YAML inputs
VALID_YAML_TESTS = [
    # Ref tag tests
    (
        """
        Resources:
          MyBucket:
            Type: AWS::S3::Bucket
            Properties:
              BucketName: !Ref MyBucketName
        """,
        {"Resources": {"MyBucket": {"Type": "AWS::S3::Bucket", "Properties": {"BucketName": RefTag("MyBucketName")}}}},
    ),
    # GetAtt tag tests
    (
        """
        Resources:
          MyInstance:
            Type: AWS::EC2::Instance
            Properties:
              UserData: !GetAtt 
                - MyInstance
                - PublicDnsName
        """,
        {"Resources": {"MyInstance": {"Type": "AWS::EC2::Instance", "Properties": {"UserData": GetAttTag(["MyInstance", "PublicDnsName"])}}}},
    ),
    # Sub tag tests
    (
        """
        Resources:
          MyBucket:
            Type: AWS::S3::Bucket
            Properties:
              BucketName: !Sub ${AWS::StackName}-my-bucket
        """,
        {"Resources": {"MyBucket": {"Type": "AWS::S3::Bucket", "Properties": {"BucketName": SubTag(["${AWS::StackName}-my-bucket"])}}}},
    ),
    # Join tag tests
    (
        """
        Resources:
          MyBucket:
            Type: AWS::S3::Bucket
            Properties:
              BucketName: !Join 
                - '-'
                - - !Ref AWS::StackName
                  - my-bucket
        """,
        {"Resources": {"MyBucket": {"Type": "AWS::S3::Bucket", "Properties": {"BucketName": JoinTag(["-", [RefTag("AWS::StackName"), "my-bucket"]])}}}},
    ),
    # Split tag tests
    (
        """
        Resources:
          MyFunction:
            Type: AWS::Lambda::Function
            Properties:
              Handler: !Split 
                - '.'
                - index.handler
        """,
        {"Resources": {"MyFunction": {"Type": "AWS::Lambda::Function", "Properties": {"Handler": SplitTag([".", "index.handler"])}}}},
    ),
    # Select tag tests
    (
        """
        Resources:
          MyFunction:
            Type: AWS::Lambda::Function
            Properties:
              Runtime: !Select 
                - 0
                - - python3.9
                  - python3.8
        """,
        {"Resources": {"MyFunction": {"Type": "AWS::Lambda::Function", "Properties": {"Runtime": SelectTag([0, ["python3.9", "python3.8"]])}}}},
    ),
    # FindInMap tag tests
    (
        """
        Resources:
          MyInstance:
            Type: AWS::EC2::Instance
            Properties:
              InstanceType: !FindInMap 
                - RegionMap
                - !Ref AWS::Region
                - InstanceType
        """,
        {"Resources": {"MyInstance": {"Type": "AWS::EC2::Instance", "Properties": {"InstanceType": FindInMapTag(["RegionMap", RefTag("AWS::Region"), "InstanceType"])}}}},
    ),
    # Base64 tag tests
    (
        """
        Resources:
          MyFunction:
            Type: AWS::Lambda::Function
            Properties:
              Code: !Base64 |
                def handler(event, context):
                    return {'statusCode': 200}
        """,
        {"Resources": {"MyFunction": {"Type": "AWS::Lambda::Function", "Properties": {"Code": Base64Tag("def handler(event, context):\n    return {'statusCode': 200}\n")}}}},
    ),
    # Cidr tag tests
    (
        """
        Resources:
          MyVPC:
            Type: AWS::EC2::VPC
            Properties:
              CidrBlock: !Cidr 
                - 10.0.0.0/16
                - 8
                - 8
        """,
        {"Resources": {"MyVPC": {"Type": "AWS::EC2::VPC", "Properties": {"CidrBlock": CidrTag(["10.0.0.0/16", 8, 8])}}}},
    ),
    # ImportValue tag tests
    (
        """
        Resources:
          MyBucket:
            Type: AWS::S3::Bucket
            Properties:
              BucketName: !ImportValue MyExportedBucketName
        """,
        {"Resources": {"MyBucket": {"Type": "AWS::S3::Bucket", "Properties": {"BucketName": ImportValueTag("MyExportedBucketName")}}}},
    ),
    # GetAZs tag tests
    (
        """
        Resources:
          MyVPC:
            Type: AWS::EC2::VPC
            Properties:
              AvailabilityZones: !GetAZs us-east-1
        """,
        {"Resources": {"MyVPC": {"Type": "AWS::EC2::VPC", "Properties": {"AvailabilityZones": GetAZsTag("us-east-1")}}}},
    ),
]

# Test data for invalid YAML inputs
INVALID_YAML_TESTS = [
    # Invalid Ref tag (missing value)
    """
    Resources:
      MyBucket:
        Type: AWS::S3::Bucket
        Properties:
          BucketName: !Ref
    """,
    # Invalid GetAtt tag (wrong number of arguments)
    """
    Resources:
      MyInstance:
        Type: AWS::EC2::Instance
        Properties:
          UserData: !GetAtt MyInstance
    """,
    # Invalid Sub tag (missing value)
    """
    Resources:
      MyBucket:
        Type: AWS::S3::Bucket
        Properties:
          BucketName: !Sub
    """,
    # Invalid Join tag (missing delimiter)
    """
    Resources:
      MyBucket:
        Type: AWS::S3::Bucket
        Properties:
          BucketName: !Join
            - my-bucket
    """,
    # Invalid Split tag (missing delimiter)
    """
    Resources:
      MyFunction:
        Type: AWS::Lambda::Function
        Properties:
          Handler: !Split index.handler
    """,
    # Invalid Select tag (wrong index type)
    """
    Resources:
      MyFunction:
        Type: AWS::Lambda::Function
        Properties:
          Runtime: !Select 
            - "0"
            - - python3.9
              - python3.8
    """,
    # Invalid FindInMap tag (missing arguments)
    """
    Resources:
      MyInstance:
        Type: AWS::EC2::Instance
        Properties:
          InstanceType: !FindInMap RegionMap
    """,
    # Invalid Cidr tag (wrong number of arguments)
    """
    Resources:
      MyVPC:
        Type: AWS::EC2::VPC
        Properties:
          CidrBlock: !Cidr 10.0.0.0/16
    """,
]


@pytest.mark.parametrize("yaml_content,expected", VALID_YAML_TESTS)
def test_valid_yaml_parsing(yaml_content, expected):
    """Test parsing of valid YAML content with CloudFormation tags."""
    result = load_yaml(yaml_content)
    assert result == expected


@pytest.mark.parametrize("yaml_content", INVALID_YAML_TESTS)
def test_invalid_yaml_parsing(yaml_content):
    """Test that invalid YAML content raises appropriate exceptions."""
    with pytest.raises(Exception):
        load_yaml(yaml_content)


def test_nested_tags():
    """Test parsing of nested CloudFormation tags."""
    yaml_content = """
    Resources:
      MyBucket:
        Type: AWS::S3::Bucket
        Properties:
          BucketName: !Join 
            - '-'
            - - !Ref AWS::StackName
              - !Sub ${Environment}-bucket
    """
    result = load_yaml(yaml_content)
    assert isinstance(result["Resources"]["MyBucket"]["Properties"]["BucketName"], JoinTag)
    join_tag = result["Resources"]["MyBucket"]["Properties"]["BucketName"]
    assert join_tag.value[0] == "-"
    assert isinstance(join_tag.value[1][0], RefTag)
    assert isinstance(join_tag.value[1][1], SubTag)


def test_empty_yaml():
    """Test parsing of empty YAML content."""
    result = load_yaml("")
    assert result is None


def test_yaml_without_tags():
    """Test parsing of YAML content without CloudFormation tags."""
    yaml_content = """
    Resources:
      MyBucket:
        Type: AWS::S3::Bucket
        Properties:
          BucketName: my-bucket
    """
    result = load_yaml(yaml_content)
    assert result["Resources"]["MyBucket"]["Properties"]["BucketName"] == "my-bucket"


def test_yaml_with_comments():
    """Test parsing of YAML content with comments."""
    yaml_content = """
    # This is a comment
    Resources:
      MyBucket:
        Type: AWS::S3::Bucket
        Properties:
          # Another comment
          BucketName: !Ref MyBucketName
    """
    result = load_yaml(yaml_content)
    assert isinstance(result["Resources"]["MyBucket"]["Properties"]["BucketName"], RefTag)
    assert result["Resources"]["MyBucket"]["Properties"]["BucketName"].value == "MyBucketName"
