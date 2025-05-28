import yaml
from typing import Any, Dict, Optional, List, Union


def get_node_type_name(node: yaml.Node) -> str:
    """Get a human-readable type name for a YAML node."""
    if isinstance(node, yaml.ScalarNode):
        return "scalar"
    elif isinstance(node, yaml.SequenceNode):
        return "sequence"
    elif isinstance(node, yaml.MappingNode):
        return "mapping"
    else:
        return "unknown"


class CloudFormationTag:
    """Base class for CloudFormation tags."""

    def __init__(self, value: Any):
        self.value = value

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, self.__class__):
            return False
        return self.value == other.value

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({repr(self.value)})"


class RefTag(CloudFormationTag):
    """Represents !Ref tag."""

    pass


class GetAttTag(CloudFormationTag):
    """Represents !GetAtt tag."""

    pass


class SubTag(CloudFormationTag):
    """Represents !Sub tag."""

    pass


class JoinTag(CloudFormationTag):
    """Represents !Join tag."""

    pass


class SplitTag(CloudFormationTag):
    """Represents !Split tag."""

    pass


class SelectTag(CloudFormationTag):
    """Represents !Select tag."""

    pass


class FindInMapTag(CloudFormationTag):
    """Represents !FindInMap tag."""

    pass


class Base64Tag(CloudFormationTag):
    """Represents !Base64 tag."""

    pass


class CidrTag(CloudFormationTag):
    """Represents !Cidr tag."""

    pass


class ImportValueTag(CloudFormationTag):
    """Represents !ImportValue tag."""

    pass


class GetAZsTag(CloudFormationTag):
    """Represents !GetAZs tag."""

    pass


def construct_ref(loader: yaml.Loader, node: yaml.Node) -> RefTag:
    """Construct !Ref tag."""
    if not isinstance(node, yaml.ScalarNode):
        raise yaml.constructor.ConstructorError(None, None, "expected a scalar node, but found %s" % get_node_type_name(node), node.start_mark)
    value = loader.construct_scalar(node)
    if value is None or value == "":
        raise yaml.constructor.ConstructorError(None, None, "!Ref tag must not be empty", node.start_mark)
    return RefTag(value)


def construct_get_att(loader: yaml.Loader, node: yaml.Node) -> GetAttTag:
    """Construct !GetAtt tag."""
    if not isinstance(node, yaml.SequenceNode):
        raise yaml.constructor.ConstructorError(None, None, "expected a sequence node, but found %s" % get_node_type_name(node), node.start_mark)
    value = loader.construct_sequence(node)
    if len(value) != 2:
        raise yaml.constructor.ConstructorError(None, None, "expected 2 items in sequence, but found %d" % len(value), node.start_mark)
    return GetAttTag(value)


def construct_sub(loader: yaml.Loader, node: yaml.Node) -> SubTag:
    """Construct !Sub tag."""
    if isinstance(node, yaml.ScalarNode):
        value = loader.construct_scalar(node)
        if value is None or value == "":
            raise yaml.constructor.ConstructorError(None, None, "!Sub tag must not be empty", node.start_mark)
        return SubTag([value])
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node)
        if len(value) != 2:
            raise yaml.constructor.ConstructorError(None, None, "expected 2 items in sequence, but found %d" % len(value), node.start_mark)
        return SubTag(value)
    else:
        raise yaml.constructor.ConstructorError(None, None, "expected a scalar or sequence node, but found %s" % get_node_type_name(node), node.start_mark)


def construct_join(loader: yaml.Loader, node: yaml.Node) -> JoinTag:
    """Construct !Join tag."""
    if not isinstance(node, yaml.SequenceNode):
        raise yaml.constructor.ConstructorError(None, None, "expected a sequence node, but found %s" % get_node_type_name(node), node.start_mark)
    value = loader.construct_sequence(node)
    if len(value) != 2:
        raise yaml.constructor.ConstructorError(None, None, "expected 2 items in sequence, but found %d" % len(value), node.start_mark)
    return JoinTag(value)


def construct_split(loader: yaml.Loader, node: yaml.Node) -> SplitTag:
    """Construct !Split tag."""
    if not isinstance(node, yaml.SequenceNode):
        raise yaml.constructor.ConstructorError(None, None, "expected a sequence node, but found %s" % get_node_type_name(node), node.start_mark)
    value = loader.construct_sequence(node)
    if len(value) != 2:
        raise yaml.constructor.ConstructorError(None, None, "expected 2 items in sequence, but found %d" % len(value), node.start_mark)
    return SplitTag(value)


def construct_select(loader: yaml.Loader, node: yaml.Node) -> SelectTag:
    """Construct !Select tag."""
    if not isinstance(node, yaml.SequenceNode):
        raise yaml.constructor.ConstructorError(None, None, "expected a sequence node, but found %s" % get_node_type_name(node), node.start_mark)
    value = loader.construct_sequence(node)
    if len(value) != 2:
        raise yaml.constructor.ConstructorError(None, None, "expected 2 items in sequence, but found %d" % len(value), node.start_mark)
    if not isinstance(value[0], int):
        raise yaml.constructor.ConstructorError(None, None, "expected an integer index, but found %s" % type(value[0]).__name__, node.start_mark)
    return SelectTag(value)


def construct_find_in_map(loader: yaml.Loader, node: yaml.Node) -> FindInMapTag:
    """Construct !FindInMap tag."""
    if not isinstance(node, yaml.SequenceNode):
        raise yaml.constructor.ConstructorError(None, None, "expected a sequence node, but found %s" % get_node_type_name(node), node.start_mark)
    value = loader.construct_sequence(node)
    if len(value) != 3:
        raise yaml.constructor.ConstructorError(None, None, "expected 3 items in sequence, but found %d" % len(value), node.start_mark)
    return FindInMapTag(value)


def construct_base64(loader: yaml.Loader, node: yaml.Node) -> Base64Tag:
    """Construct !Base64 tag."""
    if not isinstance(node, yaml.ScalarNode):
        raise yaml.constructor.ConstructorError(None, None, "expected a scalar node, but found %s" % get_node_type_name(node), node.start_mark)
    return Base64Tag(loader.construct_scalar(node))


def construct_cidr(loader: yaml.Loader, node: yaml.Node) -> CidrTag:
    """Construct !Cidr tag."""
    if not isinstance(node, yaml.SequenceNode):
        raise yaml.constructor.ConstructorError(None, None, "expected a sequence node, but found %s" % get_node_type_name(node), node.start_mark)
    value = loader.construct_sequence(node)
    if len(value) != 3:
        raise yaml.constructor.ConstructorError(None, None, "expected 3 items in sequence, but found %d" % len(value), node.start_mark)
    return CidrTag(value)


def construct_import_value(loader: yaml.Loader, node: yaml.Node) -> ImportValueTag:
    """Construct !ImportValue tag."""
    if not isinstance(node, yaml.ScalarNode):
        raise yaml.constructor.ConstructorError(None, None, "expected a scalar node, but found %s" % get_node_type_name(node), node.start_mark)
    return ImportValueTag(loader.construct_scalar(node))


def construct_get_azs(loader: yaml.Loader, node: yaml.Node) -> GetAZsTag:
    """Construct !GetAZs tag."""
    if not isinstance(node, yaml.ScalarNode):
        raise yaml.constructor.ConstructorError(None, None, "expected a scalar node, but found %s" % get_node_type_name(node), node.start_mark)
    return GetAZsTag(loader.construct_scalar(node))


class CloudFormationLoader(yaml.SafeLoader):
    """Custom YAML loader that supports CloudFormation tags."""

    pass


# Register CloudFormation tags
CloudFormationLoader.add_constructor("!Ref", construct_ref)
CloudFormationLoader.add_constructor("!GetAtt", construct_get_att)
CloudFormationLoader.add_constructor("!Sub", construct_sub)
CloudFormationLoader.add_constructor("!Join", construct_join)
CloudFormationLoader.add_constructor("!Split", construct_split)
CloudFormationLoader.add_constructor("!Select", construct_select)
CloudFormationLoader.add_constructor("!FindInMap", construct_find_in_map)
CloudFormationLoader.add_constructor("!Base64", construct_base64)
CloudFormationLoader.add_constructor("!Cidr", construct_cidr)
CloudFormationLoader.add_constructor("!ImportValue", construct_import_value)
CloudFormationLoader.add_constructor("!GetAZs", construct_get_azs)


def load_yaml(stream: str) -> Dict[str, Any]:
    """
    Load YAML content with CloudFormation tag support.

    Args:
        stream: YAML content as string

    Returns:
        Dict containing the parsed YAML with CloudFormation tags
    """
    return yaml.load(stream, Loader=CloudFormationLoader)


def load_yaml_file(file_path: str) -> Dict[str, Any]:
    """
    Load YAML file with CloudFormation tag support.

    Args:
        file_path: Path to the YAML file

    Returns:
        Dict containing the parsed YAML with CloudFormation tags
    """
    with open(file_path, "r") as f:
        return yaml.load(f, Loader=CloudFormationLoader)
