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

export default function (pi) {
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
