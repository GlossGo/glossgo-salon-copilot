import { timingSafeEqual } from "node:crypto";

import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import express, { type Request, type Response } from "express";

import { buildServer } from "./server.js";

const TRANSPORT = (process.env.MCP_TRANSPORT ?? "stdio").toLowerCase();
const PORT = Number.parseInt(process.env.PORT ?? "8082", 10);
const BEARER = process.env.MCP_BEARER_TOKEN ?? "";

if ((TRANSPORT === "http" || TRANSPORT === "sse") && BEARER.length < 16) {
  throw new Error(
    "mcp-comms: MCP_BEARER_TOKEN must be set (>=16 chars) when MCP_TRANSPORT is http/sse",
  );
}

const EXPECTED_AUTH = `Bearer ${BEARER}`;
const EXPECTED_BUF = Buffer.from(EXPECTED_AUTH);

function authOk(headerValue: string): boolean {
  if (!BEARER) return false;
  const headerBuf = Buffer.from(headerValue);
  if (headerBuf.length !== EXPECTED_BUF.length) return false;
  return timingSafeEqual(headerBuf, EXPECTED_BUF);
}

async function runStdio() {
  const server = buildServer();
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

async function runHttp() {
  const app = express();
  app.use(express.json({ limit: "1mb" }));
  app.get("/healthz", (_req, res) => res.json({ status: "ok", service: "mcp-comms" }));
  app.post("/mcp", async (req: Request, res: Response) => {
    if (!authOk(req.header("authorization") ?? "")) {
      res.status(401).json({ error: "unauthorized" });
      return;
    }
    const server = buildServer();
    const transport = new StreamableHTTPServerTransport({
      sessionIdGenerator: undefined,
    });
    res.on("close", () => { transport.close(); server.close(); });
    await server.connect(transport);
    await transport.handleRequest(req, res, req.body);
  });
  app.get("/mcp", (_req: Request, res: Response) => {
    res.status(405).json({ jsonrpc: "2.0", error: { code: -32000, message: "GET not supported in stateless mode" }, id: null });
  });
  app.delete("/mcp", (_req: Request, res: Response) => {
    res.status(405).json({ jsonrpc: "2.0", error: { code: -32000, message: "DELETE not supported in stateless mode" }, id: null });
  });
  app.listen(PORT, () => console.log(`mcp-comms listening on :${PORT} (http)`));
}

if (TRANSPORT === "http" || TRANSPORT === "sse") {
  runHttp().catch((err) => { console.error("mcp-comms http failed:", err); process.exit(1); });
} else {
  runStdio().catch((err) => { console.error("mcp-comms stdio failed:", err); process.exit(1); });
}
