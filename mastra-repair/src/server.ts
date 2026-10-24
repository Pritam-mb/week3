import { createServer } from "node:http";
import { randomUUID } from "node:crypto";
import { readFileSync, existsSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { repairRequestSchema } from "./contracts.ts";
import { proposeRepair } from "./agent.ts";

// Auto-load root .env if present
for (const envPath of [resolve(process.cwd(), ".env"), resolve(process.cwd(), "../.env"), resolve(dirname(fileURLToPath(import.meta.url)), "../../.env")]) {
  if (existsSync(envPath)) {
    try {
      const lines = readFileSync(envPath, "utf8").split(/\r?\n/);
      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith("#") || !trimmed.includes("=")) continue;
        const [k, ...v] = trimmed.split("=");
        const key = k.trim();
        const val = v.join("=").trim().replace(/^["']|["']$/g, "");
        if (key && !(key in process.env)) process.env[key] = val;
      }
    } catch (_) { /* ignore parse errors */ }
  }
}

const port = Number(process.env.MOLT_MASTRA_PORT ?? 4112);
const host = process.env.MOLT_MASTRA_HOST ?? "127.0.0.1";

function send(response: import("node:http").ServerResponse, status: number, body: unknown) {
  response.writeHead(status, { "content-type": "application/json; charset=utf-8" });
  response.end(JSON.stringify(body));
}
const server = createServer(async (request, response) => {
  const acceptsHtml = (request.headers.accept ?? "").includes("text/html");

  if (request.method === "GET" && (request.url === "/" || request.url === "/health")) {
    const model = process.env.MOLT_MASTRA_MODEL ?? "groq/openai/gpt-oss-120b";
    if (acceptsHtml && request.url === "/") {
      response.writeHead(200, { "content-type": "text/html; charset=utf-8" });
      return response.end(`<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Molt Mastra Repair Sidecar</title>
  <style>
    :root {
      --bg: #090a0f;
      --card: #12141c;
      --border: #232738;
      --text: #f0f2f8;
      --text-muted: #8b92a5;
      --accent: #6366f1;
      --success: #10b981;
    }
    body {
      margin: 0;
      padding: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      display: flex;
      min-height: 100vh;
      align-items: center;
      justify-content: center;
    }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 40px;
      max-width: 520px;
      width: 90%;
      box-shadow: 0 20px 40px rgba(0,0,0,0.5);
    }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 12px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 600;
      background: rgba(16, 185, 129, 0.15);
      color: var(--success);
      border: 1px solid rgba(16, 185, 129, 0.3);
      margin-bottom: 16px;
    }
    .dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--success);
      box-shadow: 0 0 8px var(--success);
    }
    h1 {
      margin: 0 0 8px;
      font-size: 24px;
      font-weight: 700;
    }
    p {
      color: var(--text-muted);
      line-height: 1.6;
      margin: 0 0 24px;
      font-size: 14px;
    }
    .info-row {
      background: rgba(255,255,255,0.03);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 12px 16px;
      margin-bottom: 12px;
      display: flex;
      justify-content: space-between;
      font-size: 13px;
    }
    .info-label { color: var(--text-muted); }
    .info-value { font-family: monospace; font-weight: 600; color: #a5b4fc; }
    .actions {
      display: flex;
      gap: 12px;
      margin-top: 24px;
    }
    .btn {
      flex: 1;
      text-align: center;
      padding: 10px 16px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 600;
      text-decoration: none;
      transition: all 0.2s;
    }
    .btn-primary {
      background: var(--accent);
      color: #fff;
    }
    .btn-primary:hover { background: #4f46e5; }
    .btn-secondary {
      background: rgba(255,255,255,0.05);
      color: var(--text);
      border: 1px solid var(--border);
    }
    .btn-secondary:hover { background: rgba(255,255,255,0.1); }
  </style>
</head>
<body>
  <div class="card">
    <div class="badge"><div class="dot"></div> ONLINE & READY</div>
    <h1>Molt Mastra Repair Sidecar</h1>
    <p>This service operates as the Mastra agent sidecar for Molt. It receives structural drift reports and proposes safe repair recipes using reasoning LLMs.</p>
    <div class="info-row">
      <span class="info-label">Status</span>
      <span class="info-value">Operational</span>
    </div>
    <div class="info-row">
      <span class="info-label">Active Model</span>
      <span class="info-value">\${model}</span>
    </div>
    <div class="info-row">
      <span class="info-label">Endpoint</span>
      <span class="info-value">POST /repair-proposals</span>
    </div>
    <div class="actions">
      <a class="btn btn-primary" href="http://127.0.0.1:8765" target="_blank">Open Molt Dashboard ↗</a>
      <a class="btn btn-secondary" href="/health">Health JSON</a>
    </div>
  </div>
</body>
</html>`);
    }
    return send(response, 200, {
      status: "ok",
      service: "molt-mastra-repair",
      version: "1.0.0",
      model,
      endpoints: {
        health: "GET /health",
        repair_proposals: "POST /repair-proposals",
      },
      molt_dashboard: "http://127.0.0.1:8765",
    });
  }
  if (request.method !== "POST" || request.url !== "/repair-proposals") {
    return send(response, 404, { error: "NOT_FOUND", message: "Use GET / or GET /health for status, or POST /repair-proposals for repair requests." });
  }

  try {
    const chunks: Buffer[] = [];
    for await (const chunk of request) chunks.push(Buffer.from(chunk));
    const parsed = repairRequestSchema.parse(JSON.parse(Buffer.concat(chunks).toString("utf8")));
    const result = await proposeRepair(parsed);
    return send(response, 200, {
      status: "PROPOSED",
      recipe: result.proposal.recipe,
      reason: result.proposal.reason,
      changes: result.proposal.changes,
      assumptions: result.proposal.assumptions,
      model: result.model,
      llm_calls: result.llm_calls,
      trace_id: randomUUID(),
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Mastra repair failed.";
    return send(response, 422, { error: "REPAIR_PROPOSAL_FAILED", message });
  }
});

server.listen(port, host, () => {
  console.log(`Molt Mastra repair sidecar listening on http://${host}:${port}`);
});
