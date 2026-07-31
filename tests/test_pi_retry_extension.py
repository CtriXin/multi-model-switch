import json
from pathlib import Path
import subprocess


def test_pi_retry_extension_retries_only_tokyo_parser_errors():
    extension_path = Path(__file__).resolve().parents[1] / "scripts" / "pi-retry-extension.mjs"
    script = """
const { default: extension } = await import(process.argv[1]);

let handler;
extension({ on(name, callback) { if (name === "message_end") handler = callback; } });
const cases = [
  ["mms-newapi-personal-tokyo-responses", "invalid character '\\x1b' in string literal"],
  ["mms-newapi-personal-tokyo-anthropic", "invalid character '\\f' in string literal"],
  ["mms-newapi-personal-tokyo-responses", "invalid character '+' in string escape code"],
  ["mms-newapi-personal-tokyo-responses", "invalid request body"],
  ["mms-uscrsopenai", "invalid character '\\x1b' in string literal"],
];
const results = cases.map(([provider, errorMessage]) => {
  const result = handler(
    { message: { role: "assistant", stopReason: "error", provider, errorMessage } },
    { model: { provider } },
  );
  return result?.message?.errorMessage ?? null;
});
console.log(JSON.stringify(results));
"""

    result = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(extension_path)],
        check=True,
        capture_output=True,
        text=True,
    )

    retry_messages = json.loads(result.stdout)
    assert retry_messages[0].startswith("internal_error transient relay parser retry:")
    assert retry_messages[1].startswith("internal_error transient relay parser retry:")
    assert retry_messages[2].startswith("internal_error transient relay parser retry:")
    assert retry_messages[3] is None
    assert retry_messages[4] is None
