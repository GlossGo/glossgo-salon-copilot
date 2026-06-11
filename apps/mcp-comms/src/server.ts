import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { createClient } from "@supabase/supabase-js";
import { z } from "zod";

const SHADOW = (process.env.SHADOW_MODE ?? "true").toLowerCase() === "true";

/** Approved WhatsApp Business templates this server is allowed to send. */
const WHATSAPP_TEMPLATES = [
  "waitlist_match",
  "review_response_request",
  "campaign_blast",
  "booking_reminder",
] as const;

const E164 = /^\+[1-9]\d{6,14}$/;
const UUID_V4 =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const supabase = (() => {
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) return null;
  return createClient(url, key, {
    auth: { persistSession: false },
    db: { schema: "copilot" },
  });
})();

const ok = (data: unknown) => ({
  content: [{ type: "text" as const, text: JSON.stringify(data, null, 2) }],
});

const err = (message: string) => ({
  isError: true,
  content: [{ type: "text" as const, text: `error: ${message}` }],
});

export function buildServer(): McpServer {
  const server = new McpServer({
    name: "glossgo-copilot-mcp-comms",
    version: "0.1.0",
  });

  server.registerTool(
    "send_whatsapp",
    {
      title: "Send WhatsApp",
      description:
        "Send a WhatsApp Business message. In SHADOW_MODE=true, the message is logged + recorded in copilot.agent_actions but not actually sent.",
      inputSchema: {
        to: z
          .string()
          .regex(E164, "must be an E.164 phone (e.g. +905321234567)")
          .describe("E.164 phone, e.g. +905321234567"),
        template: z
          .enum(WHATSAPP_TEMPLATES)
          .describe("Server-side allowlisted BSP template name"),
        variables: z
          .record(z.string())
          .describe("Template variable substitutions"),
        business_id: z
          .string()
          .regex(UUID_V4, "must be a UUID")
          .describe("Caller tenant; must match the authenticated session"),
        decision_summary_en: z
          .string()
          .max(300)
          .optional()
          .describe(
            "ONE short English sentence (max ~25 words) describing what the agent decided and why. Surfaced in the owner dashboard so an English-speaking observer can verify the decision without reading the Turkish draft.",
          ),
      },
    },
    async ({ to, template, variables, business_id, decision_summary_en }) => {
      const action = {
        kind: "send_whatsapp",
        to,
        template,
        variables,
        business_id,
        decision_summary_en: decision_summary_en ?? null,
        shadow: SHADOW,
        at: new Date().toISOString(),
      };
      console.error("[mcp-comms] send_whatsapp", JSON.stringify(action));
      if (supabase) {
        const { error } = await supabase.from("agent_actions").insert({
          business_id,
          kind: "send_whatsapp",
          payload: action,
          shadow: SHADOW,
        });
        if (error) return err(`failed to record agent action: ${error.message}`);
      }
      if (SHADOW) {
        // Shadow mode: the message is logged + recorded above, never sent.
        return ok({ sent: false, shadow: true, delivery_id: null });
      }
      // Live mode: there is no WhatsApp BSP integration wired yet (the Day-3
      // BSP send path never landed). Fail loudly instead of fabricating a
      // delivery — returning sent:true with a fake id would make recovered-slot
      // offers silently go nowhere while the agent reports success.
      return err(
        "send_whatsapp live mode is not implemented: no WhatsApp BSP send path is wired. " +
          "Run with SHADOW_MODE=true, or wire a real BSP integration before disabling shadow mode.",
      );
    },
  );

  server.registerTool(
    "enqueue_owner_approval",
    {
      title: "Enqueue owner approval",
      description:
        "Drop a draft (review reply, campaign blast, etc.) into the salon owner's approval queue.",
      inputSchema: {
        business_id: z.string().regex(UUID_V4, "must be a UUID"),
        channel: z.enum(["review", "campaign", "whatsapp", "other"]),
        payload: z.record(z.unknown()),
      },
    },
    async ({ business_id, channel, payload }) => {
      const row = {
        business_id,
        channel,
        payload,
        status: "pending",
      };
      console.error("[mcp-comms] enqueue_owner_approval", JSON.stringify(row));
      if (!supabase) {
        return err(
          "owner approval queue is unavailable: SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not configured",
        );
      }
      const { data, error } = await supabase
        .from("owner_approval_queue")
        .insert(row)
        .select("id")
        .single();
      if (error) return err(`failed to enqueue owner approval: ${error.message}`);
      if (!data?.id) {
        return err("failed to enqueue owner approval: insert returned no id");
      }
      return ok({ queued: true, approval_id: data.id });
    },
  );

  return server;
}
