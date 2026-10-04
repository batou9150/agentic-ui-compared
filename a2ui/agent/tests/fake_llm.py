"""A deterministic stand-in for Gemini: replays scripted turns, no network."""

from collections.abc import AsyncGenerator
from typing import Any

from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.genai import types
from pydantic import Field


def call(name: str, **args: Any) -> types.Content:
    return types.Content(
        role="model",
        parts=[types.Part(function_call=types.FunctionCall(name=name, args=args))],
    )


def say(text: str) -> types.Content:
    return types.Content(role="model", parts=[types.Part(text=text)])


class FakeLlm(BaseLlm):
    model: str = "fake-llm"
    turns: list[types.Content]
    requests: list[LlmRequest] = Field(default_factory=list)

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse]:
        self.requests.append(llm_request)
        content = self.turns.pop(0)
        usage = types.GenerateContentResponseUsageMetadata(
            prompt_token_count=100, candidates_token_count=10
        )
        yield LlmResponse(content=content, usage_metadata=usage)
