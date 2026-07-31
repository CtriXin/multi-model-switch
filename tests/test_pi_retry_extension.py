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
