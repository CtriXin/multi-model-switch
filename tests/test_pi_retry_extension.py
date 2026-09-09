import json
from pathlib import Path
import subprocess


def _run_extension(script):
    extension_path = Path(__file__).resolve().parents[1] / "scripts" / "pi-retry-extension.mjs"
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(extension_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_pi_retry_extension_does_not_rewrite_outgoing_payloads():
    """Control characters are escaped by JSON.stringify before they reach the wire.

    Normalizing them in the payload cannot change what is sent, and rewriting
    literal escape text corrupts user content, so no request hook may exist.
    """
    output = _run_extension(
        """
const { default: extension } = await import(process.argv[1]);
const registered = [];
extension({ on(name) { registered.push(name); } });
console.log(JSON.stringify({ registered }));
"""
    )
    assert output["registered"] == ["context", "message_end"]


def test_pi_retry_extension_retries_malformed_body_rejections_across_mms_routes():
    script = """
const { default: extension } = await import(process.argv[1]);
const handlers = {};
extension({ on(name, callback) { handlers[name] = callback; } });
const cases = [
  ["mms-newapi-personal-tokyo-responses", "invalid character '\\u001b' in string literal"],
  ["mms-newapi-personal-tokyo-anthropic", "invalid character '\\f' in string literal"],
  ["mms-newapi-personal-tokyo-responses", "invalid character '+' in string escape code"],
  ["mms-uscrsopenai", "invalid character '\\u001b' in string literal"],
  ["mms-uscrsopenai", "400 \\"Invalid JSON\\""],
  ["mms-us-cpa-local-codex", "token has been invalidated"],
  ["mms-us-cpa-local-antigravity", "model_capacity_exhausted"],
  ["mms-newapi-personal-tokyo-responses", "invalid request body"],
  ["mms-newapi-personal-tokyo-responses", "model_not_found"],
  ["openai", "invalid character '\\u001b' in string literal"],
];
const results = cases.map(([provider, errorMessage]) => {
  const result = handlers.message_end(
    { message: { role: "assistant", stopReason: "error", provider, errorMessage } },
    { model: { provider } },
  );
  return result?.message?.errorMessage ?? null;
});
console.log(JSON.stringify({ results }));
"""
    results = _run_extension(script)["results"]

    parser_retry = "internal_error transient relay parser retry:"
    auth_retry = "internal_error transient auth retry:"

    # Both relays that exhibit the corruption now retry, on either signature.
    assert results[0].startswith(parser_retry)
    assert results[1].startswith(parser_retry)
    assert results[2].startswith(parser_retry)
    assert results[3].startswith(parser_retry)
    assert results[4].startswith(parser_retry)

    # Pre-existing transient-auth branches are untouched.
    assert results[5].startswith(auth_retry)
    assert results[6].startswith(auth_retry)

    # Genuine rejections must still surface instead of being retried away.
    assert results[7] is None
    assert results[8] is None

    # Only MMS-managed providers participate.
    assert results[9] is None


def test_pi_retry_extension_ignores_non_error_messages():
    script = """
const { default: extension } = await import(process.argv[1]);
const handlers = {};
extension({ on(name, callback) { handlers[name] = callback; } });
const provider = "mms-uscrsopenai";
const errorMessage = "invalid character '\\u001b' in string literal";
const results = [
  handlers.message_end({ message: { role: "assistant", stopReason: "stop", provider, errorMessage } }, { model: { provider } }),
  handlers.message_end({ message: { role: "user", stopReason: "error", provider, errorMessage } }, { model: { provider } }),
  handlers.message_end({ message: { role: "assistant", stopReason: "error", provider, errorMessage: "" } }, { model: { provider } }),
];
console.log(JSON.stringify({ results: results.map((item) => item ?? null) }));
"""
    assert _run_extension(script)["results"] == [None, None, None]


def test_pi_retry_extension_drops_poisoned_reasoning_signatures_after_encrypted_content_error():
    extension_path = Path(__file__).resolve().parents[1] / "scripts" / "pi-retry-extension.mjs"
    script = r"""
const { default: extension } = await import(process.argv[1]);

const handlers = {};
extension({ on(name, callback) { handlers[name] = callback; } });

const provider = "crs-openai";
const ctx = { model: { provider } };
const now = Date.now();
const buildMessages = () => [
  { role: "user", content: [{ type: "text", text: "hi" }] },
  {
    role: "assistant",
    provider,
    timestamp: now - 5000,
    content: [
      { type: "thinking", thinking: "old", thinkingSignature: JSON.stringify({ type: "reasoning", id: "rs_old", encrypted_content: "aaa" }) },
      { type: "text", text: "old answer" },
    ],
  },
  {
    role: "assistant",
    provider: "other-provider",
    timestamp: now - 5000,
    content: [
      { type: "thinking", thinking: "foreign", thinkingSignature: JSON.stringify({ type: "reasoning", id: "rs_foreign" }) },
    ],
  },
];

// Before any failure the context hook must be a no-op.
const beforeFailure = handlers.context({ messages: buildMessages() }, ctx) ?? null;

const errorMessage =
  'OpenAI API error (400): {"message":"The encrypted content for item rs_old could not be verified. ' +
  'Reason: Encrypted content could not be decrypted or parsed.","type":"invalid_request_error",' +
  '"param":null,"code":"invalid_encrypted_content"}';
const retried = handlers.message_end(
  { message: { role: "assistant", stopReason: "error", provider, errorMessage } },
  ctx,
);

// A fresh reasoning item produced after the failure belongs to the new upstream
// account and must survive.
const messages = buildMessages();
messages.push({
  role: "assistant",
  provider,
  timestamp: Date.now() + 60000,
  content: [
    { type: "thinking", thinking: "new", thinkingSignature: JSON.stringify({ type: "reasoning", id: "rs_new" }) },
  ],
});
const afterFailure = handlers.context({ messages }, ctx);

const signatures = afterFailure.messages.map((message) =>
  Array.isArray(message.content)
    ? message.content
        .filter((block) => block.type === "thinking")
        .map((block) => (block.thinkingSignature === undefined ? null : "kept"))
    : [],
);
const otherProviderUntouched = handlers.context(
  { messages: buildMessages() },
  { model: { provider: "unrelated-provider" } },
) ?? null;

console.log(JSON.stringify({
  beforeFailure,
  retriedErrorMessage: retried?.message?.errorMessage ?? null,
  signatures,
  thinkingTextKept: afterFailure.messages[1].content[0].thinking,
  textBlockKept: afterFailure.messages[1].content[1].text,
  otherProviderUntouched,
}));
"""

    result = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(extension_path)],
        check=True,
        capture_output=True,
        text=True,
    )

    output = json.loads(result.stdout)
    assert output["beforeFailure"] is None
    assert output["retriedErrorMessage"].startswith(
        "internal_error transient encrypted reasoning retry:"
    )
    # user message, poisoned assistant, foreign-provider assistant, post-failure assistant
    assert output["signatures"] == [[], [None], ["kept"], ["kept"]]
    assert output["thinkingTextKept"] == "old"
    assert output["textBlockKept"] == "old answer"
    assert output["otherProviderUntouched"] is None
