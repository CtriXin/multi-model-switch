import mms_openrouter_extension as openrouter


def _model(model_id, modality="text->text", pricing=None):
    left, right = modality.split("->", 1)
    return {
        "id": model_id,
        "name": model_id,
        "architecture": {
            "modality": modality,
            "input_modalities": left.split("+"),
            "output_modalities": right.split("+"),
        },
        "pricing": pricing or {"prompt": "0.001", "completion": "0.002"},
    }


def test_free_openrouter_account_only_exposes_free_text_models():
    payload = {
        "data": [
            _model("openai/gpt-paid"),
            _model("qwen/qwen3-coder:free", pricing={"prompt": "0", "completion": "0"}),
            _model("openai/gpt-image", "text+image->text+image"),
        ]
    }

    summary = openrouter.classify_openrouter_extension(payload, has_api_key=False)

    assert summary["account"]["tier"] == "missing_key"
    assert summary["free_only"] is True
    assert [item["id"] for item in summary["text_models"]] == ["qwen/qwen3-coder:free"]
    assert summary["image_enabled"] is False
    assert summary["video_enabled"] is False


def test_paid_openrouter_account_exposes_text_image_and_video_models():
    payload = {
        "data": [
            _model("openai/gpt-paid"),
            _model("qwen/qwen3-coder:free", pricing={"prompt": "0", "completion": "0"}),
            _model("openai/gpt-image", "text+image->text+image"),
        ]
    }
    videos = {
        "data": [
            {
                "id": "kwaivgi/kling-v3.0-pro",
                "name": "Kling Pro",
                "supported_resolutions": ["720p"],
                "supported_durations": [5, 10],
                "pricing_skus": {"duration_seconds": "0.112"},
            }
        ]
    }

    summary = openrouter.classify_openrouter_extension(
        payload,
        key_payload={"data": {"limit": 10}},
        video_models_payload=videos,
        has_api_key=True,
    )

    assert summary["account"]["tier"] == "paid"
    assert [item["id"] for item in summary["text_models"]] == [
        "openai/gpt-paid",
        "qwen/qwen3-coder:free",
        "openai/gpt-image",
    ]
    assert [item["id"] for item in summary["image_models"]] == ["openai/gpt-image"]
    assert [item["id"] for item in summary["video_models"]] == ["kwaivgi/kling-v3.0-pro"]
    assert summary["image_enabled"] is True
    assert summary["video_enabled"] is True


def test_openrouter_invalid_key_fails_closed_to_free_only():
    payload = {
        "data": [
            _model("openai/gpt-paid"),
            _model("meta-llama/llama-3.3-70b-instruct:free", pricing={"prompt": "0", "completion": "0"}),
        ]
    }

    summary = openrouter.classify_openrouter_extension(
        payload,
        has_api_key=True,
        key_error_status=401,
    )

    assert summary["account"]["tier"] == "invalid"
    assert [item["id"] for item in summary["text_models"]] == [
        "meta-llama/llama-3.3-70b-instruct:free"
    ]


def test_openrouter_user_model_list_is_used_for_paid_accounts():
    public_payload = {"data": [_model("public/free:free", pricing={"prompt": "0", "completion": "0"})]}
    user_payload = {"data": [_model("openai/gpt-user-paid")]}

    summary = openrouter.classify_openrouter_extension(
        public_payload,
        user_models_payload=user_payload,
        key_payload={"data": {"limit_remaining": 5}},
        has_api_key=True,
    )

    assert summary["model_source"] == "user"
    assert [item["id"] for item in summary["text_models"]] == ["openai/gpt-user-paid"]


def test_openrouter_template_is_explicit_only():
    import mms_core

    assert mms_core._select_provider_template() == "generic"
    assert mms_core._select_provider_template("qwen") == "generic"
    assert mms_core._select_provider_template("openrouter") == "openrouter"

    payload = mms_core._provider_template_payload("openrouter")
    assert payload["default_openai_base_url"] == "https://openrouter.ai/api/v1"
    assert payload["models_endpoint"] == "/models"
    assert payload["extension"] == "openrouter"
    assert payload["capabilities"]["image"] == "paid_only"
