"""Run portable template contracts against the actual frontend TypeScript module."""
import shutil
import subprocess
from pathlib import Path
import pytest


def test_portable_template_contracts():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node required for frontend contract tests")
    version = subprocess.check_output([node, "--version"], text=True).strip()
    major, minor = (int(part) for part in version[1:].split(".")[:2])
    if (major, minor) < (22, 6):
        pytest.skip("Node 22.6+ required for TypeScript source execution")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([node, "--experimental-strip-types", "--test", "tests/frontend/recipe-core.test.ts"], cwd=root, text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_launch_rechecks_template_requirements_without_a_frontend():
    from mms_web.recipe_requirements import validate_requirements
    from mms_web.errors import WebError
    for requirements, model, skills in [({'image':True},{},[]),({'reasoning':True},{'reasoning':False},[]),({'skills':['guide']},{},[]),({'video':True},{},[]),({'image':'true'},{},[])]:
        with pytest.raises(WebError): validate_requirements(requirements,model,skills)
    validate_requirements({'image':True,'reasoning':True,'skills':['guide']},{'input':['image'],'reasoning':True},[{'name':'guide'}])
