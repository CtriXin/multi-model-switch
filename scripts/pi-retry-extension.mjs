const MMS_PROVIDER_PREFIX = "mms-";

// A relay rejecting the request body outright. Observed on more than one MMS
// route, with the offending byte spread across the whole byte space, so this is
// transport-level corruption of an otherwise valid request rather than anything
// the payload can be normalized out of. Keep the signatures narrow: they must
// only match "the body did not parse", never a genuine validation error.
const MALFORMED_BODY_SIGNATURE =
  /invalid character .* in string (literal|escape code)|invalid json/i;

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

    if (provider.startsWith(MMS_PROVIDER_PREFIX) && MALFORMED_BODY_SIGNATURE.test(errorMessage)) {
      return {
        message: {
          ...message,
          errorMessage: `internal_error transient relay parser retry: ${errorMessage}`,
        },
      };
    }
  });
}
