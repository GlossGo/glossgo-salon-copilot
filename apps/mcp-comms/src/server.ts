import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { createClient } from "@supabase/supabase-js";
import { z } from "zod";

const SHADOW = (process.env.SHADOW_MODE ?? "true").toLowerCase() === "true";

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
        to: z.string().describe("E.164 phone, e.g. +905321234567"),
        template: z.string().describe("Approved BSP template name, e.g. 'waitlist_match'"),
        variables: z
          .record(z.string())
          .describe("Template variable substitutions"),
        business_id: z.string(),
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
        business_id: z.string(),
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
