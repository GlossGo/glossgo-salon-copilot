/**
 * Entry point for the data MCP server.
 *
 * MCP_TRANSPORT=stdio  -> local dev, runs as a child process of the ADK agent
 * MCP_TRANSPORT=http   -> Cloud Run, exposes POST /mcp Streamable HTTP endpoint
 */

import { randomUUID } from "node:crypto";

import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import express, { type Request, type Response } from "express";

import { buildServer } from "./server.js";

const TRANSPORT = (process.env.MCP_TRANSPORT ?? "stdio").toLowerCase();
const PORT = Number.parseInt(process.env.PORT ?? "8081", 10);
const BEARER = process.env.MCP_BEARER_TOKEN ?? "";

async function runStdio() {
  const server = buildServer();
  const transport = new StdioServerTransport();
  await server.connect(transport);
  // stdio servers stay alive until the parent process closes stdin
}

async function runHttp() {
  const app = express();
  app.use(express.json({ limit: "1mb" }));

  app.get("/healthz", (_req, res) => {
    res.json({ status: "ok", service: "mcp-data" });
  });

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
    res.on("close", () => {
      transport.close();
      server.close();
    });
    await server.connect(transport);
    await transport.handleRequest(req, res, req.body);
  });

  app.listen(PORT, () => {
    console.log(`mcp-data listening on :${PORT} (http transport)`);
  });
}

if (TRANSPORT === "http" || TRANSPORT === "sse") {
  runHttp().catch((err) => {
    console.error("mcp-data http failed:", err);
    process.exit(1);
  });
} else {
  runStdio().catch((err) => {
    console.error("mcp-data stdio failed:", err);
    process.exit(1);
  });
}
