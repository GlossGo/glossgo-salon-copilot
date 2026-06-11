import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { createClient } from "@supabase/supabase-js";
import { z } from "zod";

const SHADOW = (process.env.SHADOW_MODE ?? "true").toLowerCase() === "true";

const UUID_V4 =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const uuid = () => z.string().regex(UUID_V4, "must be a UUID");
const iso = () =>
  z
    .string()
    .regex(
      /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})$/,
      "must be ISO 8601 timestamp",
    );

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
        business_id: uuid(),
        customer_id: uuid(),
        service_id: uuid(),
        staff_id: uuid().optional(),
        starts_at: iso().describe("ISO timestamp"),
        ends_at: iso().describe("ISO timestamp"),
        idempotency_key: z
          .string()
          .min(8)
          .max(64)
          .describe(
            "A unique, single-use key for THIS booking attempt — generate a fresh UUID/random string per attempt, never reuse a generic label across runs or customers. The server namespaces it to the caller's tenant, but reusing a key within the same tenant will return the earlier booking instead of creating a new one.",
          ),
        source: z.literal("agent").default("agent"),
      },
    },
    async (input) => {
      if (!supabase) return ok({ ...input, status: SHADOW ? "shadow" : "confirmed" });
      // Namespace the idempotency key to the caller's tenant so a key chosen by
      // the LLM can never collide with (or resolve to) another tenant's booking.
      const { idempotency_key, ...rest } = input;
      const scopedKey = `${input.business_id}:${idempotency_key}`;
      const { data: existing, error: lookupError } = await supabase
        .from("bookings")
        .select("id, status")
        .eq("business_id", input.business_id)
        .eq("idempotency_key", scopedKey)
        .maybeSingle();
      if (lookupError) return err(lookupError.message);
      if (existing) return ok({ id: existing.id, status: existing.status, deduped: true });

      const status = SHADOW ? "shadow" : "confirmed";
      const { data, error } = await supabase
        .from("bookings")
        .insert({ ...rest, idempotency_key: scopedKey, status })
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
        business_id: uuid(),
        staff_id: uuid(),
        starts_at: iso(),
        ends_at: iso(),
        reason: z.string().min(1).max(240),
      },
    },
    async (input) => {
      console.error("[mcp-calendar] block_slot", JSON.stringify(input));
      if (supabase) {
        const { error } = await supabase
          .from("staff_blocks")
          .insert({ ...input, shadow: SHADOW });
        if (error) return err(error.message);
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
        business_id: uuid(),
        cancelled_booking_id: uuid(),
        candidate_customer_id: uuid(),
        score: z.number().min(0).max(1),
        rationale: z.string().min(1).max(500),
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
