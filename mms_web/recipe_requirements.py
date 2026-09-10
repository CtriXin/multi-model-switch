"""Recheck a template's requirements against the actual launch configuration."""
from .errors import WebError


def validate_requirements(value, model, skills):
    if value is None:
        return
    if not isinstance(value, dict) or set(value) - {"image", "reasoning", "skills"}:
        raise WebError("RECIPE_REQUIREMENTS", "模板含有当前版本不认识的要求，请升级后重试。", 409)
    if any(type(value.get(k, False)) is not bool for k in ("image", "reasoning")):
        raise WebError("RECIPE_REQUIREMENTS", "模板模型能力要求格式不正确。", 400)
    names = value.get("skills", [])
    if not isinstance(names, list) or len(names) > 20 or any(not isinstance(n, str) for n in names):
        raise WebError("RECIPE_REQUIREMENTS", "模板 Skills 要求格式不正确。", 400)
    if value.get("image") and "image" not in (model.get("input") or []):
        raise WebError("RECIPE_REQUIREMENTS", "实际启动通道不满足模板的图片输入要求，请重新选择模型。", 409)
    if value.get("reasoning") and model.get("reasoning") is not True:
        raise WebError("RECIPE_REQUIREMENTS", "实际启动通道不满足模板的推理能力要求，请重新选择模型。", 409)
    for name in names:
        if sum(s.get("name") == name for s in skills) != 1:
            raise WebError("RECIPE_REQUIREMENTS", f"请选中当前项目唯一的 Skill {name} 后再发送。", 409)
