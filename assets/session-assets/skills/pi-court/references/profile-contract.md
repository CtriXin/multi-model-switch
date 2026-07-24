# Pi Court profile contract

Use an exact JSON object with schema `mms.pi_court.profile.v1`:

```json
{
  "schema": "mms.pi_court.profile.v1",
  "profile_id": "copy-and-test",
  "required_domains": ["copy", "testing"],
  "max_seats_per_model": 2,
  "seats": [
    {
      "seat_id": "copy-seat",
      "domain": "copy",
      "lens": "clarity-and-trust",
      "role_id": "copywriter"
    },
    {
      "seat_id": "test-seat",
      "domain": "testing",
      "lens": "contract-verification",
      "role_id": "qa"
    },
    {
      "seat_id": "wildcard-seat",
      "domain": "independent",
      "lens": "counterexample",
      "role_id": ""
    }
  ]
}
```

Rules:

- Use lowercase letters, digits, and hyphens for `profile_id`, `seat_id`, `domain`, and non-empty `role_id`.
- Keep every `seat_id` unique.
- Give every `required_domain` at least one seat.
- Resolve every non-empty `role_id` through the explicit `agent_spec_root/index.json` and require `roles/<role_id>.min.md`.
- Leave `role_id` empty for a Soul-free independent seat.
- `max_seats_per_model` must be positive. Capacity must cover all seats after explicit overrides.
- Do not put model names, provider URLs, keys, inline Soul cards, tools, or write permissions in the profile. Bind models per mission with `--model` or `--seat-model`.
