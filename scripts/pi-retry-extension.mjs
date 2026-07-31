const TOKYO_PROVIDER_PREFIX = "mms-newapi-personal-tokyo";

function normalizeTokyoParserString(value) {
  return value
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, (character) => {
      return `\\u${character.codePointAt(0).toString(16).padStart(4, "0")}`;
    })
    .replace(/\\x([0-9a-f]{2})/gi, (_match, hex) => `\\u00${hex.toLowerCase()}`)
    .replace(/\\([aev])/gi, (_match, escape) => {
      const code = { a: "0007", e: "001b", v: "000b" }[escape.toLowerCase()];
      return `\\u${code}`;
    })
    .replace(/\\0(?![0-9])/g, "\\u0000");
}

function normalizeTokyoParserPayload(value) {
  if (typeof value === "string") {
    return normalizeTokyoParserString(value);
  }
  if (Array.isArray(value)) {
    return value.map(normalizeTokyoParserPayload);
  }
  if (!value || Object.getPrototypeOf(value) !== Object.prototype) {
    return value;
  }
  return Object.fromEntries(
    Object.entries(value).map(([key, child]) => [key, normalizeTokyoParserPayload(child)]),
  );
}

// Responses-API relays that front a pool of upstream accounts encrypt each
// reasoning item for the account that produced it. When the pool rotates or
// fails over mid-session, replaying that item returns
// `invalid_encrypted_content`. Dropping the stored signature removes the item
// from the next payload entirely, because the Responses converter only emits a
// reasoning item when `thinkingSignature` is present.
const ENCRYPTED_REASONING_ERROR =
  /invalid_encrypted_content|encrypted content for item \S+ could not be verified/i;

const encryptedReasoningPoisonEpoch = new Map();

function stripPoisonedThinkingSignatures(messages, provider, epoch) {
  let changed = false;
  const next = messages.map((message) => {
    if (!message || message.role !== "assistant" || !Array.isArray(message.content)) {
      return message;
    }
    const messageProvider = String(message.provider || provider).trim();
    if (messageProvider !== provider) {
      return message;
    }
    // Items produced after the failure belong to the account we were rerouted
    // to, so only strip history recorded before it. Messages restored from a
    // session file carry no `timestamp`, so they count as pre-failure history
    // and get stripped; that is the safe direction, since their signatures come
    // from an even older upstream account.
    const timestamp = typeof message.timestamp === "number" ? message.timestamp : 0;
    if (timestamp > epoch) {
      return message;
    }
    let messageChanged = false;
    const content = message.content.map((block) => {
      if (block?.type !== "thinking" || !block.thinkingSignature) {
        return block;
      }
      messageChanged = true;
      const { thinkingSignature, ...rest } = block;
      return rest;
    });
    if (!messageChanged) {
      return message;
    }
    changed = true;
    return { ...message, content };
  });
  return changed ? next : undefined;
}

export default function (pi) {
  pi.on("context", (event, ctx) => {
    const provider = String(ctx.model?.provider || "").trim();
    const epoch = provider ? encryptedReasoningPoisonEpoch.get(provider) : undefined;
    if (!epoch) {
      return;
    }
    const messages = stripPoisonedThinkingSignatures(event.messages, provider, epoch);
    return messages ? { messages } : undefined;
  });

  pi.on("before_provider_request", (event, ctx) => {
    const provider = String(ctx.model?.provider || "").trim();
    if (!provider.startsWith(TOKYO_PROVIDER_PREFIX)) {
      return;
    }
    return normalizeTokyoParserPayload(event.payload);
  });

  pi.on("message_end", (event, ctx) => {
    const message = event.message;
    if (!message || message.role !== "assistant" || message.stopReason !== "error") {
      return;
    }

    const provider = String(message.provider || ctx.model?.provider || "").trim();
    const errorMessage = String(message.errorMessage || "").trim();
    if (!provider || !errorMessage) {
      return;
    }

    if (
      provider.startsWith("mms-us-cpa-local-codex") &&
      /token has been invalidated/i.test(errorMessage)
    ) {
      return {
        message: {
          ...message,
          errorMessage: `internal_error transient auth retry: ${errorMessage}`,
        },
      };
    }

    if (
      provider.startsWith("mms-us-cpa-local-antigravity") &&
      /auth_unavailable|model_capacity_exhausted|no capacity available/i.test(errorMessage)
    ) {
      return {
        message: {
          ...message,
          errorMessage: `internal_error transient auth retry: ${errorMessage}`,
        },
      };
    }

    // Any Responses-API relay backed by an upstream account pool can hand back
    // a reasoning item the next account cannot decrypt. Match on the upstream
    // error code rather than a provider allowlist, because the affected
    // provider id is user-defined.
    if (ENCRYPTED_REASONING_ERROR.test(errorMessage)) {
      encryptedReasoningPoisonEpoch.set(provider, Date.now());
      return {
        message: {
          ...message,
          errorMessage: `internal_error transient encrypted reasoning retry: ${errorMessage}`,
        },
      };
    }

    // NewAPI intermittently rejects an already-valid Pi request while decoding
    // tool history. Limit retries to its known parser signatures and provider.
    if (
      provider.startsWith(TOKYO_PROVIDER_PREFIX) &&
      /invalid character .* in string (literal|escape code)/i.test(errorMessage)
    ) {
      return {
        message: {
          ...message,
          errorMessage: `internal_error transient relay parser retry: ${errorMessage}`,
        },
      };
    }
  });
}
