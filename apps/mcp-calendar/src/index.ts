import { randomUUID } from "node:crypto";

import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import express, { type Request, type Response } from "express";

import { buildServer } from "./server.js";

const TRANSPORT = (process.env.MCP_TRANSPORT ?? "stdio").toLowerCase();
const PORT = Number.parseInt(process.env.PORT ?? "8083", 10);
const BEARER = process.env.MCP_BEARER_TOKEN ?? "";

async function runStdio() {
  const server = buildServer();
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

async function runHttp() {
  const app = express();
  app.use(express.json({ limit: "1mb" }));
  app.get("/healthz", (_req, res) => res.json({ status: "ok", service: "mcp-calendar" }));
  app.post("/mcp", async (req: Request, res: Response) => {
    if (BEARER) {
      const auth = req.header("authorization") ?? "";
      if (auth !== `Bearer ${BEARER}`) {
        res.status(401).json({ error: "unauthorized" });
        return;
      }
    }
    const server = buildServer();
    const transport = new StreamableHTTPServerTransport({
      sessionIdGenerator: () => randomUUID(),
    });
    res.on("close", () => { transport.close(); server.close(); });
    await server.connect(transport);
    await transport.handleRequest(req, res, req.body);
  });
  app.listen(PORT, () => console.log(`mcp-calendar listening on :${PORT} (http)`));
}

if (TRANSPORT === "http" || TRANSPORT === "sse") {
  runHttp().catch((err) => { console.error("mcp-calendar http failed:", err); process.exit(1); });
} else {
  runStdio().catch((err) => { console.error("mcp-calendar stdio failed:", err); process.exit(1); });
}
