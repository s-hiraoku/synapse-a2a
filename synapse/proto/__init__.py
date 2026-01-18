"""
Synapse A2A Protocol Buffer definitions.

Generated from a2a.proto using grpcio-tools.
Regenerate with:
    GRPC_PROTO=$(python -c "import grpc_tools, os; \\
        print(os.path.join(os.path.dirname(grpc_tools.__file__), '_proto'))")
    python -m grpc_tools.protoc \\
        --proto_path=synapse/proto \\
        --proto_path=$GRPC_PROTO \\
        --python_out=synapse/proto \\
        --grpc_python_out=synapse/proto \\
        synapse/proto/a2a.proto
"""

from synapse.proto.a2a_pb2 import (
    AgentCapabilities,
    AgentCard,
    Artifact,
    CancelTaskRequest,
    CancelTaskResponse,
    FilePart,
    GetAgentCardRequest,
    GetAgentCardResponse,
    GetTaskRequest,
    GetTaskResponse,
    ListTasksRequest,
    ListTasksResponse,
    Message,
    Part,
    SendMessageRequest,
    SendMessageResponse,
    SendPriorityMessageRequest,
    Skill,
    SubscribeRequest,
    Task,
    TaskError,
    TaskStreamEvent,
    TextPart,
)
from synapse.proto.a2a_pb2_grpc import (
    A2AServiceServicer,
    A2AServiceStub,
    add_A2AServiceServicer_to_server,
)

__all__ = [
    # Messages
    "TextPart",
    "FilePart",
    "Part",
    "Message",
    "Artifact",
    "TaskError",
    "Task",
    "Skill",
    "AgentCapabilities",
    "AgentCard",
    # Requests/Responses
    "SendMessageRequest",
    "SendMessageResponse",
    "GetTaskRequest",
    "GetTaskResponse",
    "ListTasksRequest",
    "ListTasksResponse",
    "CancelTaskRequest",
    "CancelTaskResponse",
    "GetAgentCardRequest",
    "GetAgentCardResponse",
    "TaskStreamEvent",
    "SubscribeRequest",
    "SendPriorityMessageRequest",
    # gRPC
    "A2AServiceStub",
    "A2AServiceServicer",
    "add_A2AServiceServicer_to_server",
]
