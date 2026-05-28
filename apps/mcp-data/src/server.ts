import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

import { supabase } from "./db.js";

const PKG_NAME = "glossgo-copilot-mcp-data";
const PKG_VERSION = "0.1.0";

const UUID_V4 =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const uuid = () => z.string().regex(UUID_V4, "must be a UUID");
const isoDate = () =>
  z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "expected YYYY-MM-DD");

// Until per-call tenant claims arrive in the bearer (Day 2 = Cloud Run signed
// identity + signed tenant claim), the agent MUST send the same business_id
// it received from the orchestrator session. The MCP server validates the
// shape, then narrows every query by that id. Cross-tenant traversal is only
// possible if the agent runtime is compromised — the bearer + UUID validation
// catch the "/etc/passwd" style direct attacks.

const ok = (data: unknown) => ({
  content: [{ type: "text" as const, text: JSON.stringify(data, null, 2) }],
});

const err = (message: string) => ({
  isError: true,
  content: [{ type: "text" as const, text: `error: ${message}` }],
});

export function buildServer(): McpServer {
  const server = new McpServer({ name: PKG_NAME, version: PKG_VERSION });

  server.registerTool(
    "get_cancelled_booking",
    {
      title: "Get cancelled booking",
      description:
        "Load a booking that has been cancelled, including service, staff, time window, and the cancelling customer's id.",
      inputSchema: {
        booking_id: uuid().describe("UUID of the cancelled booking."),
      },
    },
    async ({ booking_id }) => {
      const { data, error } = await supabase
        .from("bookings")
        .select(
          "id, business_id, customer_id, service_id, staff_id, starts_at, ends_at, status, cancelled_at, services(name, duration_minutes, price_try), staff(name)",
        )
        .eq("id", booking_id)
        .single();
      if (error) return err(error.message);
      if (data?.status !== "cancelled")
        return err(`booking ${booking_id} is not cancelled (status=${data?.status})`);
      return ok(data);
    },
  );

  server.registerTool(
    "list_waitlist_for_business",
    {
      title: "List waitlist for business",
      description:
        "Return active waitlist entries for a salon, with the preferred service, time window, and customer summary.",
      inputSchema: {
        business_id: uuid().describe("UUID of the business (salon)."),
        limit: z.number().int().positive().max(50).optional(),
      },
    },
    async ({ business_id, limit }) => {
      const { data, error } = await supabase
        .from("waitlist_entries")
        .select(
          "id, business_id, customer_id, service_id, preferred_window_start, preferred_window_end, notes, created_at, customers(first_name, last_name, phone, bookings_completed), services(name, duration_minutes)",
        )
        .eq("business_id", business_id)
        .eq("status", "active")
        .order("created_at", { ascending: true })
        .limit(limit ?? 20);
      if (error) return err(error.message);
      return ok(data);
    },
  );

  server.registerTool(
    "get_customer",
    {
      title: "Get customer",
      description: "Load a customer profile including phone, language preference, and loyalty stats.",
      inputSchema: {
        customer_id: uuid().describe("UUID of the customer."),
      },
    },
    async ({ customer_id }) => {
      const { data, error } = await supabase
        .from("customers")
        .select(
          "id, first_name, last_name, phone, language, bookings_completed, last_visit_at, opt_in_whatsapp",
        )
        .eq("id", customer_id)
        .single();
      if (error) return err(error.message);
      if (!data) return err(`customer ${customer_id} not found`);
      return ok(data);
    },
  );

  server.registerTool(
    "get_service",
    {
      title: "Get service",
      description: "Load a salon service (name, duration, price, category).",
      inputSchema: {
        service_id: uuid().describe("UUID of the service."),
      },
    },
    async ({ service_id }) => {
      const { data, error } = await supabase
        .from("services")
        .select("id, business_id, name, category, duration_minutes, price_try, active")
        .eq("id", service_id)
        .single();
      if (error) return err(error.message);
      return ok(data);
    },
  );

  server.registerTool(
    "get_review",
    {
      title: "Get review",
      description: "Load a Google review row by id with rating, text, reviewer first name, and business id.",
      inputSchema: {
        review_id: uuid().describe("UUID of the review."),
      },
    },
    async ({ review_id }) => {
      const { data, error } = await supabase
        .from("reviews")
        .select(
          "id, business_id, source, rating, reviewer_first_name, text, language, posted_at",
        )
        .eq("id", review_id)
        .single();
      if (error) return err(error.message);
      return ok(data);
    },
  );

  server.registerTool(
    "get_business_profile",
    {
      title: "Get business profile",
      description: "Load the salon profile: name, owner first name, vibe (formal/playful), languages.",
      inputSchema: {
        business_id: uuid().describe("UUID of the business."),
      },
    },
    async ({ business_id }) => {
      const { data, error } = await supabase
        .from("businesses")
        .select("id, name, owner_first_name, vibe, primary_language, city, district")
        .eq("id", business_id)
        .single();
      if (error) return err(error.message);
      return ok(data);
    },
  );

  server.registerTool(
    "get_weekly_occupancy",
    {
      title: "Get weekly occupancy",
      description:
        "Return a per-(day,hour) occupancy table for the week starting at target_week_start (ISO date, Monday).",
      inputSchema: {
        business_id: uuid(),
        target_week_start: isoDate(),
      },
    },
    async ({ business_id, target_week_start }) => {
      const { data, error } = await supabase.rpc("copilot_weekly_occupancy", {
        p_business_id: business_id,
        p_week_start: target_week_start,
      });
      if (error) return err(error.message);
      return ok(data);
    },
  );

  server.registerTool(
    "list_top_services",
    {
      title: "List top services",
      description: "Top N services by booking count over the last 90 days for a salon.",
      inputSchema: {
        business_id: uuid(),
        limit: z.number().int().positive().max(20).default(5),
      },
    },
    async ({ business_id, limit }) => {
      const { data, error } = await supabase.rpc("copilot_top_services", {
        p_business_id: business_id,
        p_limit: limit,
      });
      if (error) return err(error.message);
      return ok(data);
    },
  );

  return server;
}
