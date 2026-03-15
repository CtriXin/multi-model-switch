"""
Chat API - Multi-model streaming chat
"""
import asyncio
import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse
from models import ChatRequest

router = APIRouter(tags=["chat"])


async def generate_chat_stream(request: ChatRequest):
    """Generate SSE stream for chat responses"""
    models = request.models
    prompt = request.prompt

    # Simulate streaming for each model
    mock_responses = {
        "claude-sonnet-4-6": (
            "Based on your question about " + prompt[:30] + "..., here's my analysis:\n\n" +
            "1. **Key Considerations**:\n   - Performance impact\n   - Maintainability\n   - Scalability\n\n" +
            "2. **Recommendation**:\n   Use a modular architecture with clear separation of concerns.\n\n" +
            "<BRIEF>\nApproach: Modular architecture\nReasoning: Clear separation enables independent scaling\nRisks: Initial complexity, learning curve\nKey Decisions: Use interfaces, dependency injection\nNext Step: Define core modules and their contracts\n</BRIEF>"
        ),
        "gpt-4.1-mini": (
            "Here's my take on " + prompt[:30] + "...\n\n" +
            "The optimal solution depends on your constraints:\n\n" +
            "**Option A**: Microservices\n- Pros: Independent deployment\n- Cons: Operational complexity\n\n" +
            "**Option B**: Modular monolith\n- Pros: Simpler deployment\n- Cons: Risk of tight coupling\n\n" +
            "<BRIEF>\nApproach: Modular monolith first\nReasoning: Start simple, extract services when needed\nRisks: Coupling if not careful\nKey Decisions: Define strict module boundaries upfront\nNext Step: Map domain boundaries\n</BRIEF>"
        ),
        "gemini-2.5-pro": (
            "Analyzing " + prompt[:30] + "... from multiple angles:\n\n" +
            "**Architecture Patterns**:\n1. Layered architecture\n2. Hexagonal architecture\n3. Clean architecture\n\n" +
            "My recommendation is **Clean Architecture** because it provides the best testability and independence from frameworks.\n\n" +
            "<BRIEF>\nApproach: Clean Architecture\nReasoning: Framework independence, testability\nRisks: Steeper learning curve, more boilerplate\nKey Decisions: Use dependency inversion, domain at center\nNext Step: Create domain model, define use cases\n</BRIEF>"
        ),
        "deepseek-r1": (
            "Thinking through " + prompt[:30] + "...\n\n" +
            "Let me reason about this systematically:\n\n" +
            "1. What are the non-negotiables?\n   - Performance\n   - Maintainability\n   - Team expertise\n\n" +
            "2. Trade-off analysis:\n   - Microservices vs Monolith: Team size matters\n   - Sync vs Async: Latency requirements\n\n" +
            "<BRIEF>\nApproach: Start monolith, evolve to microservices\nReasoning: YAGNI principle, team velocity\nRisks: Future refactoring cost\nKey Decisions: Design internal APIs as if external\nNext Step: Document current pain points\n</BRIEF>"
        ),
    }

    # Default response for other models
    default_response = (
        "Here's my analysis of your question:\n\n" +
        "The key is to balance immediate delivery with long-term maintainability.\n\n" +
        "<BRIEF>\nApproach: Balanced approach\nReasoning: Deliver value while maintaining quality\nRisks: Technical debt if rushed\nKey Decisions: Prioritize core features, iterate\nNext Step: Create MVP, gather feedback\n</BRIEF>"
    )

    # Start responses for all models
    for model in models:
        yield {
            "event": "model_start",
            "data": json.dumps({"model": model, "status": "loading"})
        }

    # Stream chunks for each model
    for model in models:
        response_text = mock_responses.get(model, default_response)
        words = response_text.split(" ")

        for i, word in enumerate(words):
            chunk = word + (" " if i < len(words) - 1 else "")
            yield {
                "event": "chunk",
                "data": json.dumps({"model": model, "text": chunk})
            }
            await asyncio.sleep(0.01)  # Simulate network delay

        # Model done
        yield {
            "event": "model_done",
            "data": json.dumps({
                "model": model,
                "elapsed": 2.5,
                "status": "done"
            })
        }

    # All done
    yield {
        "event": "all_done",
        "data": json.dumps({"models": models})
    }


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Start a streaming chat with multiple models"""
    return EventSourceResponse(
        generate_chat_stream(request),
        media_type="text/event-stream"
    )
