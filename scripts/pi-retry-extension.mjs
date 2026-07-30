export default function (pi) {
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

    // The CRS relay intermittently rejects otherwise valid Responses tool payloads.
    if (
      provider.startsWith("mms-uscrsopenai") &&
      /invalid character ['"]?\\(?:t|x[0-9a-f]{2})['"]? in string literal/i.test(errorMessage)
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
