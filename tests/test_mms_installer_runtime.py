def test_installer_no_longer_supports_qwen_or_kimi_cli():
    import mms_installer

    assert "qwen" not in mms_installer.INSTALL_COMMANDS
    assert "kimi" not in mms_installer.INSTALL_COMMANDS
    assert "qwen" not in mms_installer.CLI_DESCRIPTIONS
    assert "kimi" not in mms_installer.CLI_DESCRIPTIONS
