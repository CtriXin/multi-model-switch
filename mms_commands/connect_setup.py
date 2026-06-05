"""Provider/account connect and setup helpers."""

from __future__ import annotations


def check_cli_installed(cli_name, *, resolve_cli_binary):
    return bool(resolve_cli_binary(cli_name))


def prompt_provider_credentials(
    provider,
    existing_base_url="",
    existing_api_key="",
    allow_keep=False,
    *,
    stdin_isatty,
    console,
    current_command,
    config_command_hint,
    localize,
    ensure_rich,
    default_base_url,
    provider_label,
    prompt_ask,
    exit_func,
):
    if not stdin_isatty():
        console.print(
            f"[red]{localize('当前不是交互终端，无法输入 API URL / API Key，请在终端里运行', 'Not running in an interactive terminal. Please run')} {current_command()} "
            f"{localize('或执行', 'or')} {config_command_hint()}[/red]"
        )
        exit_func(1)
    ensure_rich()

    default_openai = provider.get("default_openai_base_url", "")
    default_anthropic = provider.get("default_anthropic_base_url", "")
    current_openai = provider.get("openai_base_url", "") or existing_base_url
    current_anthropic = provider.get("anthropic_base_url", "") or existing_base_url
    protocols = provider.get("protocols", [])
    needs_openai = "openai_chat_completions" in protocols
    needs_anthropic = "anthropic_messages" in protocols

    base_url = ""
    openai_base_url = ""
    anthropic_base_url = ""

    if needs_openai and needs_anthropic and default_openai and default_anthropic and default_openai != default_anthropic:
        openai_base_url = prompt_ask(
            f"请输入 OpenAI 接口地址 / Base URL（请求地址，通道: {provider_label(provider)}）",
            default=current_openai or default_openai,
        ).rstrip("/")
        anthropic_base_url = prompt_ask(
            f"请输入 Anthropic 接口地址 / Base URL（请求地址，通道: {provider_label(provider)}）",
            default=current_anthropic or default_anthropic,
        ).rstrip("/")
        base_url = anthropic_base_url or openai_base_url
    elif needs_openai and not needs_anthropic:
        openai_base_url = prompt_ask(
            f"请输入 OpenAI 接口地址 / Base URL（请求地址，通道: {provider_label(provider)}）",
            default=current_openai or default_openai or existing_base_url or default_base_url,
        ).rstrip("/")
        base_url = openai_base_url
    elif needs_anthropic and not needs_openai:
        anthropic_base_url = prompt_ask(
            f"请输入 Anthropic 接口地址 / Base URL（请求地址，通道: {provider_label(provider)}）",
            default=current_anthropic or default_anthropic or existing_base_url or default_base_url,
        ).rstrip("/")
        base_url = anthropic_base_url
    else:
        base_default = existing_base_url or default_base_url
        base_url = prompt_ask(
            f"请输入接口地址 / Base URL（请求地址，通道: {provider_label(provider)}）",
            default=base_default,
        ).rstrip("/")
        openai_base_url = base_url if needs_openai else ""
        anthropic_base_url = base_url if needs_anthropic else ""

        key_prompt = f"{localize('请输入 API Key', 'Enter API key')}（{localize('通道', 'channel')}: {provider_label(provider)}）"
    if allow_keep and existing_api_key:
        key_prompt = f"{localize('请输入 API Key', 'Enter API key')}（{localize('通道', 'channel')}: {provider_label(provider)}，{localize('留空保持不变', 'leave empty to keep current value')}）"

    prompt_kwargs = {"password": True}
    if allow_keep:
        prompt_kwargs["default"] = ""
    api_key = prompt_ask(key_prompt, **prompt_kwargs)
    if allow_keep and existing_api_key and not api_key:
        api_key = existing_api_key

    if not api_key:
        console.print(f"[red]{localize('API Key 不能为空', 'API key cannot be empty')}[/red]")
        exit_func(1)

    return base_url, api_key, openai_base_url, anthropic_base_url


def quick_connect_official(
    cfg,
    preset_cli=None,
    *,
    ensure_interactive_terminal,
    localize,
    panel_cls,
    console,
    managed_oauth_clis,
    delegated_oauth_clis,
    wizard_prompt,
    wizard_back_cls,
    wizard_cancel_cls,
    account_map,
    unique_runtime_id,
    normalize_account_id,
    default_account_home,
    prompt_validated_proxy_fields,
    prompt_validated_timezone,
    default_account_timezone,
    normalize_account,
    default_priority,
    ensure_account_config,
    save_config,
    load_config,
    confirm_ask,
):
    ensure_interactive_terminal(localize("官方通道接入", "official channel setup"))
    console.print(panel_cls(
        localize(
            "[bold]官方通道[/bold]\n\n创建一个独立登录目录；创建完成后，回主界面启动该通道时再进入官方 CLI 登录。\n"
            "显示名称给你自己看；系统会自动生成内部标识，避免后续引用丢失。\n"
            "适合多个 ChatGPT / Claude / Antigravity 账号并行使用。\n"
            "[dim]输入 b 返回，q 退出。[/dim]",
            "[bold]Official channel[/bold]\n\nCreate an isolated login directory first; after setup, launch this channel from the main UI to continue the official CLI login flow.\n"
            "The display name is user-facing; MMS auto-generates the stable system ID used by config and follow-up commands.\n"
            "Use this when you want multiple ChatGPT / Claude / Antigravity accounts in parallel.\n"
            "[dim]Type b to go back, q to cancel.[/dim]",
        ),
        title=localize("快速接入", "Quick Connect"),
        border_style="cyan",
    ))
    choices = {
        "1": ("codex", "ChatGPT / Codex"),
        "2": ("agy", "Antigravity CLI"),
    }
    if preset_cli in delegated_oauth_clis:
        console.print("[yellow]Claude OAuth 独立入口已下线；MMS 不再新增 Claude 官方账号。[/yellow]")
        return cfg, False
    if preset_cli in managed_oauth_clis:
        cli_name = preset_cli
    else:
        console.print("  1. ChatGPT / Codex")
        console.print("  2. Antigravity CLI")
        try:
            selected = wizard_prompt(localize("选择官方通道类型", "Select official channel type"), default="1")
        except wizard_back_cls:
            console.print(f"[yellow]{localize('已返回上一层', 'Returned to previous step')}[/yellow]")
            return cfg, False
        except wizard_cancel_cls:
            console.print(f"[yellow]{localize('已退出接入', 'Setup cancelled')}[/yellow]")
            return cfg, False
        if selected not in choices:
            console.print(f"[red]{localize('请输入 1-2', 'Please enter 1-2')}[/red]")
            return cfg, False
        cli_name = choices[selected][0]

    suggested_name = f"{cli_name}-main"
    try:
        name = wizard_prompt(
            localize("显示名 / 列表展示名（主界面里看到的名字）", "Display name / list label"),
            default=suggested_name,
        ).strip() or suggested_name
    except wizard_back_cls:
        console.print(f"[yellow]{localize('已返回上一层', 'Returned to previous step')}[/yellow]")
        return cfg, False
    except wizard_cancel_cls:
        console.print(f"[yellow]{localize('已退出接入', 'Setup cancelled')}[/yellow]")
        return cfg, False
    accounts = account_map(cfg)
    account_id = unique_runtime_id(set(accounts.keys()), normalize_account_id(name))
    console.print(f"[dim]{localize('系统内部标识（自动生成）', 'System ID (auto-generated)')}: {account_id}[/dim]")

    home_dir = default_account_home(account_id)
    try:
        proxy, no_proxy = prompt_validated_proxy_fields("", "", wizard=True)
        timezone_name = prompt_validated_timezone(default_account_timezone, wizard=True)
    except wizard_back_cls:
        console.print(f"[yellow]{localize('已返回上一层', 'Returned to previous step')}[/yellow]")
        return cfg, False
    except wizard_cancel_cls:
        console.print(f"[yellow]{localize('已退出接入', 'Setup cancelled')}[/yellow]")
        return cfg, False
    account = normalize_account({
        "id": account_id,
        "name": name,
        "cli": cli_name,
        "home_dir": home_dir,
        "enabled": True,
        "priority": default_priority,
        "proxy": proxy,
        "no_proxy": no_proxy,
        "timezone": timezone_name,
    })
    updated_cfg = dict(cfg)
    updated_cfg["accounts"] = list(cfg.get("accounts", [])) + [account]
    updated_cfg, _ = ensure_account_config(updated_cfg)
    save_config(updated_cfg)
    console.print(f"[green]✓ {localize('已添加官方通道', 'Official channel added')}: {name}[/green]")
    console.print(f"[dim]{localize('内部标识', 'System ID')}: {account_id}[/dim]")
    console.print(f"[dim]{localize('文件夹目录', 'Directory')}: {home_dir}[/dim]")
    console.print(
        f"[dim]{localize('已跳过立即登录；请回主界面启动这个官方通道，再完成登录。', 'Immediate login skipped; launch this official channel from the main UI when you are ready to sign in.')}[/dim]"
    )
    if confirm_ask(localize(f"设为 {cli_name} 的默认官方通道？", f"Set as the default {cli_name} official channel?"), default=True):
        updated_cfg = load_config()
        updated_cfg.setdefault("account", {}).setdefault("defaults", {})
        updated_cfg["account"]["defaults"][cli_name] = account_id
        save_config(updated_cfg)
        console.print(f"[green]✓ {localize(f'{cli_name} 默认官方通道已更新为 {account_id}', f'Default {cli_name} official channel set to {account_id}')}[/green]")
    return load_config(), True


def quick_connect_gateway(
    cfg,
    preset_id=None,
    *,
    ensure_interactive_terminal,
    select_provider_template,
    provider_template_payload,
    localize,
    panel_cls,
    console,
    provider_map,
    wizard_prompt,
    wizard_back_cls,
    wizard_cancel_cls,
    normalize_provider_id_input,
    default_provider_id,
    unique_runtime_id,
    normalize_provider,
    default_base_url,
    confirm_ask,
    prompt_ask,
    normalize_models_endpoint,
    prompt_validated_proxy_fields,
    prompt_validated_timezone,
    default_account_timezone,
    upsert_provider,
    save_config,
    save_provider_credentials_with_probe,
    load_config,
):
    ensure_interactive_terminal(localize("网关通道接入", "gateway channel setup"))
    template_key = select_provider_template(preset_id=preset_id)
    template = provider_template_payload(template_key)
    console.print(panel_cls(
        localize(
            "[bold]网关通道[/bold]\n\n填写接口地址（请求地址 / Base URL）和 API Key，接入兼容 OpenAI / Anthropic 的服务。\n"
            "显示名称给你自己看；系统会自动生成内部标识，避免后续功能和外部消费引用丢失。\n"
            "如果模型列表地址和请求地址不同，再额外填写“模型列表地址（高级）”。\n"
            "默认会启用全部 CLI；后续如需精细限制，再用 provider.edit 调整。\n"
            "[dim]输入 b 返回，q 退出。[/dim]",
            "[bold]Gateway channel[/bold]\n\nEnter the request Base URL and API key for any OpenAI- or Anthropic-compatible service.\n"
            "The display name is for you; MMS auto-generates a stable system ID so presets and external consumers do not break.\n"
            "Only fill a separate model list URL if listing models uses a different endpoint.\n"
            "All CLIs are enabled by default; use provider.edit later if you need tighter limits.\n"
            "[dim]Type b to go back, q to cancel.[/dim]",
        ),
        title=localize("快速接入", "Quick Connect"),
        border_style="cyan",
    ))
    providers = provider_map(cfg)
    suggested_name = template["name"]
    try:
        name = wizard_prompt(
            localize("显示名称 / 列表展示名（主界面里看到的名字）", "Display name / list label"),
            default=suggested_name,
        ).strip() or suggested_name
        suggested_id = normalize_provider_id_input(name)
        if suggested_id == default_provider_id:
            suggested_id = normalize_provider_id_input(template["id"] or name)
        provider_id = unique_runtime_id(set(providers.keys()), suggested_id)
    except wizard_back_cls:
        console.print(f"[yellow]{localize('已返回上一层', 'Returned to previous step')}[/yellow]")
        return cfg, False
    except wizard_cancel_cls:
        console.print(f"[yellow]{localize('已退出接入', 'Setup cancelled')}[/yellow]")
        return cfg, False
    console.print(f"[dim]{localize('系统内部标识（自动生成）', 'System ID (auto-generated)')}: {provider_id}[/dim]")

    provider = normalize_provider({
        **template,
        "id": provider_id,
        "name": name,
    })
    try:
        base_url = wizard_prompt(
            localize("接口地址 / Base URL（请求地址）", "Request Base URL"),
            default=provider.get("default_openai_base_url") or provider.get("default_anthropic_base_url") or default_base_url,
            required=True,
        ).rstrip("/")
        api_key = wizard_prompt(
            localize("API Key（不会回显）", "API key (hidden)"),
            password=True,
            required=True,
        )
        if confirm_ask(localize("模型列表地址与请求地址不同？（高级）", "Use a separate model list URL? (advanced)"), default=False):
            provider["models_endpoint"] = normalize_models_endpoint(
                prompt_ask(
                    localize(
                        "模型列表地址（高级，仅用于独立拉取模型列表；通常留默认）",
                        "Model list URL (advanced, only used for a separate model-list endpoint)",
                    ),
                    default=provider.get("models_endpoint", "/models"),
                )
            )
        provider["proxy"], provider["no_proxy"] = prompt_validated_proxy_fields(
            provider.get("proxy", ""),
            provider.get("no_proxy", ""),
            wizard=True,
        )
        provider["timezone"] = prompt_validated_timezone(
            provider.get("timezone") or default_account_timezone,
            wizard=True,
        )
        provider = normalize_provider(provider)
    except wizard_back_cls:
        console.print(f"[yellow]{localize('已返回上一层', 'Returned to previous step')}[/yellow]")
        return cfg, False
    except wizard_cancel_cls:
        console.print(f"[yellow]{localize('已退出接入', 'Setup cancelled')}[/yellow]")
        return cfg, False
    updated_cfg = upsert_provider(cfg, provider)
    save_config(updated_cfg)
    save_provider_credentials_with_probe(
        provider,
        base_url,
        api_key,
        base_url if "openai_chat_completions" in provider.get("protocols", []) else "",
        base_url if "anthropic_messages" in provider.get("protocols", []) else "",
    )
    console.print(f"[green]✓ {localize('已接入网关通道', 'Gateway channel added')}: {name}[/green]")
    console.print(f"[dim]{localize('内部标识', 'System ID')}: {provider_id}[/dim]")
    return load_config(), True


def select_cli(
    cli_names,
    *,
    check_cli_installed,
    check_and_offer_install,
    table_cls,
    int_prompt_cls,
    console,
    exit_func,
):
    if not cli_names:
        console.print("[red]当前没有可用的 CLI。请先检查 provider 配置和模型探测结果。[/red]")
        exit_func(1)
    table = table_cls(title="选择 CLI")
    table.add_column("#", style="cyan", width=4)
    table.add_column("CLI", style="green")
    table.add_column("状态", style="yellow")

    for i, name in enumerate(cli_names, 1):
        status = "[green]已安装[/green]" if check_cli_installed(name) else "[red]未安装[/red]"
        table.add_row(str(i), name, status)

    console.print(table)

    while True:
        try:
            choice = int_prompt_cls.ask("选择 CLI 编号")
            if 1 <= choice <= len(cli_names):
                cli = cli_names[choice - 1]
                if not check_cli_installed(cli):
                    check_and_offer_install(cli)
                return cli
            console.print(f"[red]请输入 1-{len(cli_names)}[/red]")
        except KeyboardInterrupt:
            exit_func(0)


def setup_provider_credentials(
    provider,
    existing_base_url="",
    existing_api_key="",
    allow_keep=False,
    *,
    prompt_provider_credentials,
    save_provider_credentials_with_probe,
):
    base_url, api_key, openai_base_url, anthropic_base_url = prompt_provider_credentials(
        provider,
        existing_base_url,
        existing_api_key,
        allow_keep,
    )
    return save_provider_credentials_with_probe(
        provider,
        base_url,
        api_key,
        openai_base_url,
        anthropic_base_url,
    )


def setup_api_credentials(
    existing_base_url="",
    existing_api_key="",
    allow_keep=False,
    *,
    default_provider,
    setup_provider_credentials,
):
    provider = default_provider()
    provider_ctx = setup_provider_credentials(provider, existing_base_url, existing_api_key, allow_keep)
    return provider_ctx["base_url"], provider_ctx["api_key"]


def ensure_provider_credentials(
    cfg,
    provider_id=None,
    *,
    get_provider_definition,
    load_provider_credentials,
    resolve_provider_context,
    setup_provider_credentials,
):
    provider = get_provider_definition(cfg, provider_id)
    if provider.get("_mms_bundle_runtime") and provider.get("api_key") and (
        provider.get("openai_base_url")
        or provider.get("anthropic_base_url")
        or provider.get("default_openai_base_url")
        or provider.get("default_anthropic_base_url")
    ):
        return resolve_provider_context(cfg, provider["id"])
    credentials = load_provider_credentials(provider["id"])
    if (
        credentials["base_url"]
        or credentials["openai_base_url"]
        or credentials["anthropic_base_url"]
    ) and credentials["api_key"]:
        return resolve_provider_context(cfg, provider["id"])
    existing_base = (
        credentials["base_url"]
        or credentials["openai_base_url"]
        or credentials["anthropic_base_url"]
    )
    return setup_provider_credentials(
        provider,
        existing_base,
        credentials["api_key"],
        allow_keep=bool(credentials["api_key"]),
    )


def ensure_api_credentials(*, default_config, ensure_provider_credentials):
    provider_ctx = ensure_provider_credentials(default_config())
    return provider_ctx["base_url"], provider_ctx["api_key"]


def setup_wizard(
    ui_language=None,
    *,
    normalize_language,
    set_language,
    display_title,
    localize,
    panel_cls,
    default_config,
    setup_provider_credentials,
    get_provider_definition,
    prompt_ask,
    mode_all,
    mode_recommended,
    save_config,
    config_path,
    console,
):
    ui_language = normalize_language(ui_language) or "zh"
    set_language(ui_language)
    title = display_title()
    console.print(panel_cls(
        f"[bold cyan]{localize(f'欢迎使用 {title} — AI Coding CLI 统一启动器', f'Welcome to {title} — unified AI coding CLI launcher')}[/bold cyan]\n\n"
        f"{localize(f'{title} 帮你一键启动 AI 编程助手', f'{title} helps you launch AI coding assistants from one entrypoint')}\n"
        f"{localize('首次使用，需要配置 API 地址和认证信息', 'First-time setup needs an API endpoint and credentials')}",
        title=f"{title} Setup",
    ))

    cfg = default_config()
    cfg.setdefault("ui", {})["language"] = ui_language
    setup_provider_credentials(get_provider_definition(cfg))

    role = prompt_ask(localize("模型模式", "Model mode"), choices=[mode_all, mode_recommended], default=mode_all)
    cfg = default_config(role)
    cfg.setdefault("ui", {})["language"] = ui_language
    save_config(cfg)
    console.print(f"\n[green]✓ {localize('配置已保存到', 'Config saved to')} {config_path}[/green]\n")
    return cfg
