from __future__ import annotations


def test_run_doctor_fails_when_proxy_missing(monkeypatch, tmp_path, capsys):
    import mmc_core

    monkeypatch.setenv("MMC_CONFIG_HOME", str(tmp_path / "mmc-config"))
    monkeypatch.setenv("MMC_REAL_HOME", str(tmp_path / "real-home"))
    monkeypatch.setattr(mmc_core, "_doctor_check_binary", lambda *_args, **_kwargs: (True, "/usr/bin/fake"))
    monkeypatch.setattr(mmc_core, "_doctor_check_directory_writable", lambda _path: (True, "/tmp/ok"))

    exit_code = mmc_core._run_doctor(mmc_core._build_launch_namespace())
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "FAIL proxy config" in output
    assert "FAIL summary" in output


def test_run_doctor_reports_parent_env_warning_and_proxy_guard_pass(monkeypatch, tmp_path, capsys):
    import mmc_core

    monkeypatch.setenv("MMC_CONFIG_HOME", str(tmp_path / "mmc-config"))
    monkeypatch.setenv("MMC_REAL_HOME", str(tmp_path / "real-home"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    monkeypatch.setattr(mmc_core, "_doctor_check_binary", lambda *_args, **_kwargs: (True, "/usr/bin/fake"))
    monkeypatch.setattr(
        mmc_core,
        "_doctor_probe_tcp_endpoint",
        lambda _host, _port, timeout_sec=4.0: (True, "127.0.0.1:7890"),
    )
    monkeypatch.setattr(
        mmc_core,
        "_build_local_proxy_guard",
        lambda _proxy, _no_proxy: {"status": "ok", "exit_ip": "1.2.3.4"},
    )
    monkeypatch.setattr(mmc_core, "_doctor_check_directory_writable", lambda _path: (True, "/tmp/ok"))

    args = mmc_core._build_launch_namespace(proxy="http://127.0.0.1:7890")
    exit_code = mmc_core._run_doctor(args)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "PASS proxy guard: Claude upstream reachable; exit_ip=1.2.3.4" in output
    assert "WARN parent env: ANTHROPIC_API_KEY" in output
    assert "PASS summary: doctor completed: 0 fail, 2 warn" in output


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
