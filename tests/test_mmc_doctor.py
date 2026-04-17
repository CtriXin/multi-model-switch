from __future__ import annotations

import json


def test_run_doctor_fails_when_proxy_missing(monkeypatch, tmp_path, capsys):
    import mmc_core

    monkeypatch.setenv("MMC_CONFIG_HOME", str(tmp_path / "mmc-config"))
    monkeypatch.setenv("MMC_REAL_HOME", str(tmp_path / "real-home"))
    monkeypatch.setattr(mmc_core, "_doctor_check_binary", lambda *_args, **_kwargs: (True, "/usr/bin/fake"))
    monkeypatch.setattr(mmc_core, "_doctor_check_directory_writable", lambda _path: (True, "/tmp/ok"))

    exit_code = mmc_core._run_doctor(mmc_core._build_launch_namespace())
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "FAIL proxy route" in output
    assert "FAIL summary" in output


def test_run_doctor_reports_parent_env_warning_and_proxy_guard_pass(monkeypatch, tmp_path, capsys):
    import mmc_core

    monkeypatch.setenv("MMC_CONFIG_HOME", str(tmp_path / "mmc-config"))
    monkeypatch.setenv("MMC_REAL_HOME", str(tmp_path / "real-home"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/501")
    monkeypatch.setattr(mmc_core, "_doctor_check_binary", lambda *_args, **_kwargs: (True, "/usr/bin/fake"))
    monkeypatch.setattr(
        mmc_core,
        "_doctor_probe_tcp_endpoint",
        lambda _host, _port, timeout_sec=4.0: (True, "127.0.0.1:7890"),
    )
    monkeypatch.setattr(
        mmc_core,
        "_build_local_proxy_guard",
        lambda _proxy, _no_proxy, **_kwargs: {"status": "ok", "exit_ip": "1.2.3.4"},
    )
    monkeypatch.setattr(mmc_core, "_doctor_check_directory_writable", lambda _path: (True, "/tmp/ok"))
    monkeypatch.setattr(mmc_core, "_doctor_check_state_path_writable", lambda _path: (True, "/tmp/ok"))
    monkeypatch.setattr(mmc_core, "_doctor_check_tty", lambda: (True, "stdin/stdout 均为 TTY"))
    monkeypatch.setattr(mmc_core, "_doctor_check_runtime_identity", lambda: (True, "当前以普通用户身份运行"))

    args = mmc_core._build_launch_namespace(proxy="http://127.0.0.1:7890")
    exit_code = mmc_core._run_doctor(args)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "PASS proxy guard: Claude upstream reachable; exit_ip=1.2.3.4" in output
    assert "WARN exit IP pin: 未配置 expected_exit_ip" in output
    assert "WARN parent env: ANTHROPIC_API_KEY" in output
    assert "XDG_RUNTIME_DIR" in output
    assert "PASS summary: doctor completed: 0 fail, 3 warn" in output


def test_main_doctor_applies_saved_defaults(monkeypatch, tmp_path):
    import mmc_core

    seen = {}
    monkeypatch.setenv("MMC_CONFIG_HOME", str(tmp_path / "mmc-config"))
    monkeypatch.setenv("MMC_REAL_HOME", str(tmp_path / "real-home"))
    mmc_core._save_launcher_defaults({"proxy": "http://127.0.0.1:7890", "tz": "America/Los_Angeles"})
    monkeypatch.setattr(
        mmc_core,
        "_run_doctor",
        lambda args: seen.update({"proxy": args.proxy, "tz": args.tz}) or 0,
    )

    try:
        mmc_core.main(["doctor"])
    except SystemExit as exc:
        assert exc.code == 0

    assert seen == {"proxy": "http://127.0.0.1:7890", "tz": "America/Los_Angeles"}


def test_run_doctor_fails_when_proxy_is_not_loopback(monkeypatch, tmp_path, capsys):
    import mmc_core

    monkeypatch.setenv("MMC_CONFIG_HOME", str(tmp_path / "mmc-config"))
    monkeypatch.setenv("MMC_REAL_HOME", str(tmp_path / "real-home"))
    monkeypatch.setattr(mmc_core, "_doctor_check_binary", lambda *_args, **_kwargs: (True, "/usr/bin/fake"))
    monkeypatch.setattr(mmc_core, "_doctor_check_directory_writable", lambda _path: (True, "/tmp/ok"))
    monkeypatch.setattr(mmc_core, "_doctor_check_state_path_writable", lambda _path: (True, "/tmp/ok"))

    exit_code = mmc_core._run_doctor(mmc_core._build_launch_namespace(proxy="http://10.0.0.8:8080"))
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "FAIL proxy route" in output
    assert "loopback" in output


def test_run_doctor_reports_route_file_and_expected_exit_ip(monkeypatch, tmp_path, capsys):
    import mmc_core

    routes_file = tmp_path / "proxy-routes.json"
    routes_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "routes": [
                    {
                        "id": "route-a",
                        "purpose": "oauth_claude",
                        "local_proxy_url": "http://127.0.0.1:31001",
                        "sticky_account_binding": {"email": "demo@example.com"},
                        "expected_exit_ip": "1.2.3.4",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MMC_CONFIG_HOME", str(tmp_path / "mmc-config"))
    monkeypatch.setenv("MMC_REAL_HOME", str(tmp_path / "real-home"))
    monkeypatch.setattr(mmc_core, "_doctor_check_binary", lambda *_args, **_kwargs: (True, "/usr/bin/fake"))
    monkeypatch.setattr(
        mmc_core,
        "_doctor_probe_tcp_endpoint",
        lambda _host, _port, timeout_sec=4.0: (True, "127.0.0.1:31001"),
    )
    monkeypatch.setattr(
        mmc_core,
        "_build_local_proxy_guard",
        lambda _proxy, _no_proxy, **_kwargs: {"status": "ok", "exit_ip": "1.2.3.4"},
    )
    monkeypatch.setattr(mmc_core, "_doctor_check_directory_writable", lambda _path: (True, "/tmp/ok"))
    monkeypatch.setattr(mmc_core, "_doctor_check_state_path_writable", lambda _path: (True, "/tmp/ok"))
    monkeypatch.setattr(mmc_core, "_doctor_check_tty", lambda: (True, "stdin/stdout 均为 TTY"))
    monkeypatch.setattr(mmc_core, "_doctor_check_runtime_identity", lambda: (True, "当前以普通用户身份运行"))
    monkeypatch.setattr(
        mmc_core,
        "_current_account_owner_metadata",
        lambda: {
            "account_home": str(tmp_path / "mmc-config" / "accounts" / "default"),
            "owner_user_id": "",
            "owner_account_uuid": "",
            "owner_email": "demo@example.com",
        },
    )

    args = mmc_core._build_launch_namespace(route_id="route-a", routes_file=str(routes_file))
    exit_code = mmc_core._run_doctor(args)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "PASS proxy route: route-a" in output
    assert "PASS exit IP pin: 1.2.3.4 matches expected" in output


def test_run_doctor_warns_on_nested_session_and_sudo(monkeypatch, tmp_path, capsys):
    import mmc_core

    monkeypatch.setenv("MMC_CONFIG_HOME", str(tmp_path / "mmc-config"))
    monkeypatch.setenv("MMC_REAL_HOME", str(tmp_path / "real-home"))
    monkeypatch.setenv("MMC_SESSION_HOME", str(tmp_path / "nested-session"))
    monkeypatch.setenv("SUDO_USER", "xin")
    monkeypatch.setattr(mmc_core, "_doctor_check_binary", lambda *_args, **_kwargs: (True, "/usr/bin/fake"))
    monkeypatch.setattr(
        mmc_core,
        "_doctor_probe_tcp_endpoint",
        lambda _host, _port, timeout_sec=4.0: (True, "127.0.0.1:7890"),
    )
    monkeypatch.setattr(
        mmc_core,
        "_build_local_proxy_guard",
        lambda _proxy, _no_proxy, **_kwargs: {"status": "ok", "exit_ip": "1.2.3.4"},
    )
    monkeypatch.setattr(mmc_core, "_doctor_check_directory_writable", lambda _path: (True, "/tmp/ok"))
    monkeypatch.setattr(mmc_core, "_doctor_check_state_path_writable", lambda _path: (True, "/tmp/ok"))
    monkeypatch.setattr(mmc_core, "_doctor_check_tty", lambda: (False, "stdin 不是 TTY；交互式 Claude 会话可能退化"))
    monkeypatch.setattr(
        mmc_core,
        "_doctor_check_runtime_identity",
        lambda: (False, "当前通过 root/sudo 运行，可能把 ~/.config/mmc 写成 root 所有"),
    )

    exit_code = mmc_core._run_doctor(mmc_core._build_launch_namespace(proxy="http://127.0.0.1:7890"))
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "WARN tty: stdin 不是 TTY" in output
    assert "WARN runtime identity: 当前通过 root/sudo 运行" in output
    assert "WARN nested session: 当前 shell 已在 MMC session 内" in output


def test_run_doctor_strict_mode_fails_on_warning(monkeypatch, tmp_path, capsys):
    import mmc_core

    monkeypatch.setenv("MMC_CONFIG_HOME", str(tmp_path / "mmc-config"))
    monkeypatch.setenv("MMC_REAL_HOME", str(tmp_path / "real-home"))
    monkeypatch.setattr(mmc_core, "_doctor_check_binary", lambda *_args, **_kwargs: (True, "/usr/bin/fake"))
    monkeypatch.setattr(
        mmc_core,
        "_doctor_probe_tcp_endpoint",
        lambda _host, _port, timeout_sec=4.0: (True, "127.0.0.1:7890"),
    )
    monkeypatch.setattr(
        mmc_core,
        "_build_local_proxy_guard",
        lambda _proxy, _no_proxy, **_kwargs: {"status": "ok", "exit_ip": "1.2.3.4"},
    )
    monkeypatch.setattr(mmc_core, "_doctor_check_directory_writable", lambda _path: (True, "/tmp/ok"))
    monkeypatch.setattr(mmc_core, "_doctor_check_state_path_writable", lambda _path: (True, "/tmp/ok"))
    monkeypatch.setattr(mmc_core, "_doctor_check_tty", lambda: (True, "stdin/stdout 均为 TTY"))
    monkeypatch.setattr(mmc_core, "_doctor_check_runtime_identity", lambda: (True, "当前以普通用户身份运行"))

    args = mmc_core._build_launch_namespace(proxy="http://127.0.0.1:7890")
    args.strict = True
    exit_code = mmc_core._run_doctor(args)
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "strict mode blocked on warnings" in output
