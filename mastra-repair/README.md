# Molt Mastra repair sidecar

This optional TypeScript service gives Molt's repair proposal path a Mastra
agent with typed, read-only inspection tools. It does **not** activate recipes,
write CSV files, or replace Molt's verifier.

## Start

```bash
cd mastra-repair
npm install
MOLT_MASTRA_MODEL="groq/openai/gpt-oss-120b" npm run dev
```

The sidecar listens on `http://127.0.0.1:4112` by default. Point Molt at it with:

```bash
MOLT_MASTRA_REPAIR_URL=http://127.0.0.1:4112
```

Then request a repair with `model: "mastra"` through Molt's existing repair API.
The dashboard also shows **Suggest Mastra repair** on a blocked run when the
sidecar is configured.

## Safety boundary

The request contains only the automation ID, recipe contract, structural drift
report and masked profile. The response is a candidate recipe. Molt still runs
`validate_recipe`, the complete regression suite, and explicit approval before
the candidate can become active.

The model provider is intentionally configured outside the repository through
`MOLT_MASTRA_MODEL`. Mastra expects a provider/model identifier, and the
provider's required environment variables must also be present. No API key or
provider has been committed here. For a fully local Gemma path, the chosen
Mastra model adapter must be configured to use the local Ollama endpoint before
enabling the sidecar.

For Groq, set the key in the sidecar process environment, never in committed
files:

```powershell
$env:GROQ_API_KEY = "your-new-key"
$env:MOLT_MASTRA_MODEL = "groq/openai/gpt-oss-120b"
npm run dev
```

Mastra's model router accepts the `provider/model` string and resolves the
provider API key from its environment. The sidecar still returns only a
candidate recipe; Molt performs validation, regression verification, and human
approval.
