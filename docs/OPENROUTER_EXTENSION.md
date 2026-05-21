# OpenRouter Extension

MMS treats OpenRouter as an explicit optional extension, not as a default public
capability.

## Scope

- Text models use the normal OpenAI-compatible provider path.
- OpenRouter model ids keep their original prefix, for example
  `openai/gpt-5-image` or `google/gemini-2.5-flash`.
- Image and video are extension capabilities, not launcher defaults.
- Free-only accounts show free text models only and hide the OpenRouter Image /
  Video actions.
- Paid accounts may show the key/user-scoped model list and can expose
  OpenRouter Image and OpenRouter Video model lists.

## Commands

```bash
mms config extension.openrouter add
mms config extension.openrouter status [provider_id]
mms config extension.openrouter models [provider_id] --limit 50
```

`add` enters the existing provider wizard with the OpenRouter template:

- `openai_base_url`: `https://openrouter.ai/api/v1`
- `models_endpoint`: `/models`
- `provider_profile`: `openrouter`
- capabilities: `text`, `image: paid_only`, `video: paid_only`

The status/models commands do not write real MMS config. They read the selected
provider key, or `OPENROUTER_API_KEY` / `OPEN_ROUTER_API_KEY` /
`MMS_OPENROUTER_API_KEY` from the current environment.

## Account Gating

MMS fails closed:

- Missing or invalid key => `free-only`
- Unknown plan signal => `free-only`
- Positive key limit or credits signal => `paid`
- `--assume-paid` is available for local dry-run UI checks, but should not be
  used as product truth.

The extension uses:

- `/api/v1/models` for public model metadata and modalities
- `/api/v1/key` and `/api/v1/credits` for key/account signals
- `/api/v1/models/user` for key-scoped model lists when available
- `/api/v1/videos/models` for OpenRouter Video models when paid is confirmed

## References

- https://openrouter.ai/docs/api/api-reference/models/get-models
- https://openrouter.ai/docs/guides/overview/multimodal/image-generation
- https://openrouter.ai/docs/api/api-reference/video-generation/list-videos-models
- https://openrouter.ai/docs/api/api-reference/api-keys/get-current-key
