import { handleCheck } from "../_shared/check_handler.ts";

Deno.serve((request) => handleCheck(request));
