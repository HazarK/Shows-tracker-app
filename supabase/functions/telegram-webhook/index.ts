import { handleWebhook } from "../_shared/webhook.ts";

Deno.serve((request) => handleWebhook(request));
