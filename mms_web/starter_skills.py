"""Small bundled instructions, explicitly selected per message; no global install."""
from pathlib import Path


_STARTERS = (
    ("plan-task", "把想法变成步骤", "整理目标、步骤与完成条件。", "请先帮我梳理这项任务的目标和步骤：", "pilot-skills/plan-task"),
    ("review-changes", "检查当前改动", "找出具体问题，给出证据和建议。", "请检查当前工作文件夹里的改动，说明问题、影响和建议。", "pilot-skills/review-changes"),
    ("offduty", "保存进度", "记住做到哪里和下一步，保留会话与进程。", "请保存当前任务的进度和下一步，方便稍后继续。", "handover/aliases/offduty"),
    ("onduty", "继续上次", "读取已保存的进度，核实后继续。", "请读取这个工作文件夹已有的任务进度，核实当前状态后继续。", "handover/aliases/onduty"),
    ("handover", "整理交接", "把目标、成果与未完成事项交给下个会话。", "请整理当前任务的交接说明，包含验证结果、未完成事项和下一步。", "handover"),
)


def starter_skills():
    root = Path(__file__).resolve().parent.parent / "vendor"
    return [{"id": "pilot:" + name, "name": name, "title": title, "description": description,
             "example": example, "source": "Pilot 内置", "sourceRoot": str(root), "overrides": [],
             "filePath": str(root / relative / "SKILL.md"), "baseDir": str(root / relative),
             "manualOnly": True, "starter": True}
            for name, title, description, example, relative in _STARTERS
            if (root / relative / "SKILL.md").is_file()]
