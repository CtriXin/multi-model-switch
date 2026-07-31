import json
from pathlib import Path
import subprocess


def test_pi_retry_extension_normalizes_only_tokyo_parser_payloads_and_retries_parser_errors():
    extension_path = Path(__file__).resolve().parents[1] / "scripts" / "pi-retry-extension.mjs"
    script = r"""
const { default: extension } = await import(process.argv[1]);

const handlers = {};
extension({ on(name, callback) { handlers[name] = callback; } });
const parserPayload = {
  messages: [
    { role: "tool", content: "actual-control:\u001b[31mred\u001b[0m" },
    { role: "tool", content: String.raw`legacy-escape:\x1b` },
    { role: "tool", content: String.raw`legacy-escape-upper:\xAF` },
    { role: "tool", content: String.raw`legacy-bell:\a` },
    { role: "tool", content: String.raw`legacy-short:\e` },
    { role: "tool", content: String.raw`legacy-vtab:\v` },
    { role: "tool", content: String.raw`legacy-null:\0` },
    { role: "tool", content: "actual-del:\u007f" },
    { role: "tool", content: "safe\tline\n" },
  ],
};
const normalizedPayload = handlers.before_provider_request(
  { payload: parserPayload },
  { model: { provider: "mms-newapi-personal-tokyo-responses" } },
);
const unchangedPayload = handlers.before_provider_request(
  { payload: parserPayload },
  { model: { provider: "mms-uscrsopenai" } },
);
const cases = [
  ["mms-newapi-personal-tokyo-responses", "invalid character '\\x1b' in string literal"],
  ["mms-newapi-personal-tokyo-anthropic", "invalid character '\\f' in string literal"],
  ["mms-newapi-personal-tokyo-responses", "invalid character '+' in string escape code"],
  ["mms-newapi-personal-tokyo-responses", "invalid request body"],
  ["mms-uscrsopenai", "invalid character '\\x1b' in string literal"],
];
const results = cases.map(([provider, errorMessage]) => {
  const result = handlers.message_end(
    { message: { role: "assistant", stopReason: "error", provider, errorMessage } },
    { model: { provider } },
  );
  return result?.message?.errorMessage ?? null;
});
console.log(JSON.stringify({ normalizedPayload, unchangedPayload: unchangedPayload ?? null, results }));
"""

    result = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(extension_path)],
        check=True,
        capture_output=True,
        text=True,
    )

    output = json.loads(result.stdout)
    normalized_contents = [item["content"] for item in output["normalizedPayload"]["messages"]]
    assert normalized_contents == [
        r"actual-control:\u001b[31mred\u001b[0m",
        r"legacy-escape:\u001b",
        r"legacy-escape-upper:\u00af",
        r"legacy-bell:\u0007",
        r"legacy-short:\u001b",
        r"legacy-vtab:\u000b",
        r"legacy-null:\u0000",
        r"actual-del:\u007f",
        "safe\tline\n",
    ]
    assert output["unchangedPayload"] is None

    retry_messages = output["results"]
    assert retry_messages[0].startswith("internal_error transient relay parser retry:")
    assert retry_messages[1].startswith("internal_error transient relay parser retry:")
    assert retry_messages[2].startswith("internal_error transient relay parser retry:")
    assert retry_messages[3] is None
    assert retry_messages[4] is None
