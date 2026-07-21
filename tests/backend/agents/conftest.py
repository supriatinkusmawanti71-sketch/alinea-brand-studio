from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from backend.agents.testing import InMemoryArtifactWriter, InMemoryInvocationRecorder
from backend.agents.workflow import build_brand_workflow
from backend.providers.models.fake import FakeImageModelProvider, FakeTextModelProvider


@pytest.fixture
def workflow():
    return build_brand_workflow(
        text_provider=FakeTextModelProvider(),
        image_provider=FakeImageModelProvider(),
        artifact_writer=InMemoryArtifactWriter(),
        invocation_recorder=InMemoryInvocationRecorder(),
        checkpointer=InMemorySaver(),
    )
