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

const err = (m: string) => ({
  isError: true,
  content: [{ type: "text" as const, text: `error: ${m}` }],
});

export function buildServer(): McpServer {
  const server = new McpServer({
    name: "glossgo-copilot-mcp-calendar",
    version: "0.1.0",
  });

  server.registerTool(
    "create_booking",
    {
      title: "Create booking",
      description:
        "Create a new booking. Idempotent via idempotency_key. In SHADOW_MODE=true the booking is recorded with status=shadow.",
      inputSchema: {
        business_id: z.string(),
        customer_id: z.string(),
        service_id: z.string(),
        staff_id: z.string().optional(),
        starts_at: z.string().describe("ISO timestamp"),
        ends_at: z.string().describe("ISO timestamp"),
        idempotency_key: z.string(),
        source: z.literal("agent").default("agent"),
      },
    },
    async (input) => {
      if (!supabase) return ok({ ...input, status: SHADOW ? "shadow" : "confirmed" });
      const { data: existing } = await supabase
        .from("bookings")
        .select("id, status")
        .eq("idempotency_key", input.idempotency_key)
        .maybeSingle();
      if (existing) return ok({ id: existing.id, status: existing.status, deduped: true });

      const status = SHADOW ? "shadow" : "confirmed";
      const { data, error } = await supabase
        .from("bookings")
        .insert({ ...input, status })
        .select("id, status")
        .single();
      if (error) return err(error.message);
      return ok({ ...data, deduped: false });
    },
  );

  server.registerTool(
    "block_slot",
    {
      title: "Block slot",
      description: "Block a slot on a staff calendar (e.g. reserved-for-waitlist).",
      inputSchema: {
        business_id: z.string(),
        staff_id: z.string(),
        starts_at: z.string(),
        ends_at: z.string(),
        reason: z.string(),
      },
    },
    async (input) => {
      console.error("[mcp-calendar] block_slot", JSON.stringify(input));
      if (supabase) {
        await supabase.from("staff_blocks").insert({ ...input, shadow: SHADOW });
      }
      return ok({ blocked: true, shadow: SHADOW });
    },
  );

  server.registerTool(
    "propose_waitlist_match",
    {
      title: "Propose waitlist match",
      description:
        "Record the agent's chosen waitlist candidate for an open slot, before any messaging.",
      inputSchema: {
        business_id: z.string(),
        cancelled_booking_id: z.string(),
        candidate_customer_id: z.string(),
        score: z.number().min(0).max(1),
        rationale: z.string(),
      },
    },
    async (input) => {
      console.error("[mcp-calendar] propose_waitlist_match", JSON.stringify(input));
      if (supabase) {
        const { error } = await supabase.from("waitlist_match_proposals").insert(input);
        if (error) return err(error.message);
      }
      return ok({ proposed: true });
    },
  );

  return server;
}
