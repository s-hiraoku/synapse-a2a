"""Tests for synapse.proto package."""

import pytest


def test_proto_imports():
    """Test that proto modules can be imported."""
    try:
        import synapse.proto
        from synapse.proto import a2a_pb2, a2a_pb2_grpc

        # Ensure they are loaded
        assert synapse.proto
        assert a2a_pb2
        assert a2a_pb2_grpc
    except ImportError as e:
        pytest.fail(f"Failed to import proto modules: {e}")


def test_proto_objects():
    """Test that proto objects can be instantiated."""
    from synapse.proto.a2a_pb2 import StreamRequest, StreamResponse

    req = StreamRequest()
    assert req is not None

    res = StreamResponse()
    assert res is not None
