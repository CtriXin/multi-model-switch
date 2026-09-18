"""Fresh local bootstrap/export with no real provider or process launch."""
import json
import os
from pathlib import Path
import subprocess
import sys


def test_fresh_opencode_bootstrap_exports_verified_bundle_and_fails_closed(tmp_path):
    root = Path(__file__).resolve().parents[1]
    home = tmp_path / "home"
    home.mkdir()
    config = home / ".config" / "mms-next"
    env = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "WINDIR") if key in os.environ}
    env.update({"HOME": str(home), "USERPROFILE": str(home), "MMS_REAL_HOME": str(home),
                "REAL_HOME": str(home), "ORIGINAL_HOME": str(home), "MMS_CONFIG_ROOT": str(config),
                "PYTHONPATH": os.pathsep.join([str(root / "lib"), str(root)]), "MMS_TEST_ALLOW_REAL_CONFIG": "0"})
    run = subprocess.run([sys.executable, str(root / "tests/fixtures/opencode_first_run.py")],
                         cwd=root, env=env, text=True, capture_output=True, check=True, timeout=30)
    result = json.loads(run.stdout)
    assert result["root_absent_before"] and result["initial_runtime"] is None
    assert result["missing_bundle_blocked"] and result["corrupt_bundle_blocked"]
    assert result["bootstrap_loaded"] and result["verified"]
    assert result["config_source"] == "latest-approved-bundle"
    assert result["model"] == "mms/deepseek-chat"
    assert result["endpoint"] == "https://bootstrap.example.invalid/v1"
    assert result["synthetic_key_matched"] and result["config_uses_env_key"]
    assert Path(result["export_path"]).is_relative_to(config)
    assert not result["config_toml_exists"] and result["bootstrap_plan_leftovers"] == 0
