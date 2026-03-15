"""
Discuss API - Three-phase discussion with synthesis
"""
import asyncio
import json
from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse
from models import DiscussRequest

router = APIRouter(tags=["discuss"])


async def generate_discuss_stream(request: DiscussRequest):
    """Generate SSE stream for discuss phases"""
    models = request.models
    prompt = request.prompt

    # Phase 1: Independent summaries
    yield {
        "event": "phase_start",
        "data": json.dumps({
            "phase": 1,
            "name": "方案摘要",
            "total": len(models)
        })
    }

    await asyncio.sleep(0.5)

    # Generate phase 1 results
    phase1_results = {
        "claude-sonnet-4-6": {
            "approach": "采用领域驱动设计(DDD)方法",
            "reasoning": "通过限界上下文划分，确保每个服务的职责清晰",
            "risks": ["团队学习成本", "初期开发速度较慢"],
            "keyDecisions": ["使用事件溯源", "CQRS模式"],
            "nextStep": "识别核心域和支持域"
        },
        "gpt-4.1-mini": {
            "approach": "渐进式微服务拆分",
            "reasoning": "从单体开始，在痛点明显时逐步拆分",
            "risks": ["后期重构成本", "临时方案可能成为永久方案"],
            "keyDecisions": ["API网关", "服务网格"],
            "nextStep": "绘制当前架构图"
        },
        "gemini-2.5-pro": {
            "approach": "模块化单体架构",
            "reasoning": "平衡开发效率和部署灵活性",
            "risks": ["模块间耦合", "共享数据库风险"],
            "keyDecisions": ["严格模块边界", "内部API契约"],
            "nextStep": "定义模块接口"
        },
        "deepseek-r1": {
            "approach": "垂直切片架构",
            "reasoning": "按业务能力而非技术分层组织代码",
            "risks": ["代码重复", "跨切片重构困难"],
            "keyDecisions": ["功能内聚", "共享内核最小化"],
            "nextStep": "识别业务能力边界"
        },
    }

    for model in models:
        result = phase1_results.get(model, {
            "approach": "标准分层架构",
            "reasoning": "简单直接，团队熟悉",
            "risks": ["层间耦合"],
            "keyDecisions": ["依赖注入"],
            "nextStep": "开始实现"
        })

        yield {
            "event": "phase1_result",
            "data": json.dumps({
                "model": model,
                "ok": True,
                "data": result
            })
        }
        await asyncio.sleep(0.3)

    yield {
        "event": "phase_complete",
        "data": json.dumps({"phase": 1})
    }

    await asyncio.sleep(0.5)

    # Phase 2: Cross reviews
    if len(models) >= 2:
        yield {
            "event": "phase_start",
            "data": json.dumps({
                "phase": 2,
                "name": "交叉审查",
                "total": len(models) * (len(models) - 1)
            })
        }

        # Generate cross reviews
        reviews = [
            ("claude-sonnet-4-6", "gpt-4.1-mini", "同意渐进式方法", "但缺乏明确的拆分标准", "可以结合DDD的边界划分"),
            ("gpt-4.1-mini", "claude-sonnet-4-6", "DDD是理想状态", "担心过度设计", "建议从轻量级DDD开始"),
            ("gemini-2.5-pro", "deepseek-r1", "垂直切片有价值", "担心重复代码", "可以结合模块化思想"),
            ("deepseek-r1", "gemini-2.5-pro", "模块化是务实选择", "但可能错失DDD好处", "建议先在核心域试用DDD"),
        ]

        for reviewer, target, agreement, challenge, better in reviews:
            if reviewer in models and target in models:
                yield {
                    "event": "phase2_result",
                    "data": json.dumps({
                        "reviewer": reviewer,
                        "target": target,
                        "ok": True,
                        "data": {
                            "agreement": agreement,
                            "challenge": challenge,
                            "betterOption": better
                        }
                    })
                }
                await asyncio.sleep(0.3)

        yield {
            "event": "phase_complete",
            "data": json.dumps({"phase": 2})
        }

    await asyncio.sleep(0.5)

    # Phase 3: Synthesis
    synthesizer = models[0] if models else "claude-sonnet-4-6"

    yield {
        "event": "phase_start",
        "data": json.dumps({
            "phase": 3,
            "name": "综合结论",
            "total": 1,
            "synthesizer": synthesizer
        })
    }

    # Stream synthesis content
    synthesis_text = """经过各模型的独立分析和交叉审查，以下是综合建议：

## 共识点
1. **渐进式演进**优于一步到位 - 所有模型都认同应该从当前状态逐步演进
2. **明确边界**是关键 - 无论是DDD的限界上下文还是模块边界
3. **务实优先** - 选择团队能够理解和维护的方案

## 分歧与权衡
- **DDD vs 简单分层**: 建议在核心域使用DDD，支撑域使用简单分层
- **单体 vs 微服务**: 从模块化单体开始，提取真正需要独立扩展的服务

## 最终建议
1. **阶段1**: 在现有代码中识别和标注业务边界
2. **阶段2**: 将跨边界的直接调用改为接口/事件
3. **阶段3**: 根据实际负载和团队规模决定是否需要拆分为独立服务

## 下一步行动
1. 绘制当前系统的业务领域图
2. 识别核心域、支撑域和通用域
3. 制定3个月的演进路线图"""

    words = synthesis_text.split(" ")
    for word in words:
        yield {
            "event": "phase3_chunk",
            "data": json.dumps({"text": word + " "})
        }
        await asyncio.sleep(0.02)

    yield {
        "event": "complete",
        "data": json.dumps({
            "synthesizer": synthesizer,
            "final": synthesis_text
        })
    }


@router.post("/discuss/stream")
async def discuss_stream(request: DiscussRequest):
    """Start a three-phase discussion with multiple models"""
    return EventSourceResponse(
        generate_discuss_stream(request),
        media_type="text/event-stream"
    )
