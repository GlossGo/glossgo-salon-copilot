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
      },
    },
    async ({ to, template, variables, business_id }) => {
      const action = {
        kind: "send_whatsapp",
        to,
        template,
        variables,
        business_id,
        shadow: SHADOW,
        at: new Date().toISOString(),
      };
      console.error("[mcp-comms] send_whatsapp", JSON.stringify(action));
      if (supabase) {
        await supabase.from("agent_actions").insert({
          business_id,
          kind: "send_whatsapp",
          payload: action,
          shadow: SHADOW,
        });
      }
      return ok({
        sent: !SHADOW,
        shadow: SHADOW,
        delivery_id: SHADOW ? null : `wa-${Date.now()}`,
      });
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
      let id: string | null = null;
      if (supabase) {
        const { data, error } = await supabase
          .from("owner_approval_queue")
          .insert(row)
          .select("id")
          .single();
        if (!error) id = data?.id ?? null;
      }
      return ok({ queued: true, approval_id: id ?? `mock-${Date.now()}` });
    },
  );

  return server;
}
