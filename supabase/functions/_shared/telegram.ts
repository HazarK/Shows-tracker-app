/** Telegram Bot API calls used by the webhook and the daily check. */

export type Button = {
  text: string;
  callbackData: string;
};

export type Outgoing = {
  text: string;
  buttons?: Button[][];
  parseMode?: "HTML";
};

export class TelegramSendError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "TelegramSendError";
  }
}

export class TelegramApi {
  constructor(private readonly token: string) {}

  send(chatId: number, text: string): Promise<void> {
    return this.sendMessage(chatId, { text });
  }

  sendMessage(chatId: number, outgoing: Outgoing): Promise<void> {
    return this.call("sendMessage", {
      chat_id: chatId,
      text: outgoing.text,
      ...parseMode(outgoing),
      ...replyMarkup(outgoing.buttons, false),
    });
  }

  editMessageText(
    chatId: number,
    messageId: number,
    outgoing: Outgoing,
  ): Promise<void> {
    return this.call("editMessageText", {
      chat_id: chatId,
      message_id: messageId,
      text: outgoing.text,
      ...parseMode(outgoing),
      ...replyMarkup(outgoing.buttons, true),
    });
  }

  answerCallbackQuery(callbackQueryId: string): Promise<void> {
    return this.call("answerCallbackQuery", { callback_query_id: callbackQueryId });
  }

  private async call(method: string, body: Record<string, unknown>): Promise<void> {
    let response: Response;
    try {
      response = await fetch(`https://api.telegram.org/bot${this.token}/${method}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(30_000),
      });
    } catch {
      throw new TelegramSendError("Telegram request failed");
    }
    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      throw new TelegramSendError("Telegram returned invalid JSON");
    }
    if (
      response.status >= 400 ||
      !isRecord(payload) ||
      payload.ok !== true
    ) {
      throw new TelegramSendError(`Telegram returned HTTP ${response.status}`);
    }
  }
}

function parseMode(outgoing: Outgoing): Record<string, string> {
  if (!outgoing.parseMode) {
    return {};
  }
  return { parse_mode: outgoing.parseMode };
}

function replyMarkup(
  buttons: Button[][] | undefined,
  always: boolean,
): Record<string, unknown> {
  if (!buttons || buttons.length === 0) {
    if (!always) {
      return {};
    }
    return { reply_markup: { inline_keyboard: [] } };
  }
  return {
    reply_markup: {
      inline_keyboard: buttons.map((row) =>
        row.map((button) => ({
          text: button.text,
          callback_data: button.callbackData,
        }))
      ),
    },
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
