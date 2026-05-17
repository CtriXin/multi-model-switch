def test_qwen_install_uses_nvm_node22_without_changing_default(monkeypatch):
    import mms_installer

    monkeypatch.setattr(mms_installer, "_node_major_version", lambda: 18)

    command = mms_installer._install_command_for_cli(
        "qwen",
        mms_installer.INSTALL_COMMANDS["qwen"],
    )

    assert "nvm use 22" in command
    assert "nvm alias default" not in command
    assert command.endswith("npm install -g @qwen-code/qwen-code")


def test_qwen_install_reuses_current_node22(monkeypatch):
    import mms_installer

    monkeypatch.setattr(mms_installer, "_node_major_version", lambda: 22)

    command = mms_installer._install_command_for_cli(
        "qwen",
        mms_installer.INSTALL_COMMANDS["qwen"],
    )

    assert command == "npm install -g @qwen-code/qwen-code"
