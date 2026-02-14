# PRD Errata — CS2 AI Live Commentator

> **PUBLIC REPOSITORY** — This repo is public on GitHub. Do not include API keys, secrets, credentials, or proprietary information in any file.

> Audit performed: 2026-02-13
> Audited file: `CS-dev-PRD.md`

All items below have been corrected in the PRD unless marked "unverified".

---

## Critical Fixes

### C1: Cartesia model ID (`sonic-2` → `sonic-3`)
- **Before:** All code examples used `model_id: "sonic-2"`
- **After:** Changed to `"sonic-3"`. The PRD described Sonic 3 features but referenced the Sonic 2 model ID.
- **Source:** [Cartesia TTS Models](https://docs.cartesia.ai/build-with-cartesia/tts-models/latest)

### C2: Anthropic SDK version (`^1.x` → `^0.74.x`)
- **Before:** `"@anthropic-ai/sdk": "^1.x"`
- **After:** `"^0.74.x"` — the SDK has not reached 1.0 yet.
- **Source:** [@anthropic-ai/sdk on npm](https://www.npmjs.com/package/@anthropic-ai/sdk)

### C3: Cartesia WebSocket idle timeout
- **Before:** Assumed a single WebSocket connection for entire 30-60 min match
- **After:** Added note: Cartesia WebSocket connections have a 5-minute idle timeout. Must implement reconnection or keepalive logic.
- **Source:** [Cartesia Concurrency and Timeouts](https://docs.cartesia.ai/use-the-api/concurrency-limits-and-timeouts)

### C4: `speaker` npm package unmaintained
- **Before:** `"speaker": "^0.5.x"` listed as dependency
- **After:** Removed. Replaced with recommendation to use `sox`/`ffplay` via `child_process.spawn` or Web Audio API.
- **Source:** [speaker on npm](https://www.npmjs.com/package/speaker) — last published 2+ years ago

---

## High-Priority Fixes

### H1: Cartesia API version (`2024-06-10` → `2025-04-16`)
- Updated all `Cartesia-Version` headers and query params.
- Breaking changes in v2025-04-16: embeddings removed, `/voices/create` deprecated, stability clones removed.
- **Source:** [Cartesia Changelog](https://docs.cartesia.ai/2025-04-16/developer-tools/changelog)

### H2: SSML emotion syntax
- **Before:** `<emotion name="excitement" level="high">text</emotion>`
- **After:** `<emotion value='excited'/>text`
- Also noted `[laughter]` tag support.
- **Source:** [Cartesia Sonic 3 Docs](https://docs.cartesia.ai/build-with-cartesia/tts-models/latest)

### H3: Hume WebSocket endpoint
- **Before:** `wss://api.hume.ai/v0/tts`
- **After:** `wss://api.hume.ai/v0/tts/stream/input?version=2`
- **Source:** [Hume TTS Overview](https://dev.hume.ai/docs/text-to-speech-tts/overview)

### H4: Cartesia TTFB precision
- **Before:** "40ms TTFB" attributed generally to Sonic 3
- **After:** Clarified: 40ms is for `sonic-turbo` variant; base `sonic-3` is "sub-100ms"
- **Source:** [Cartesia Sonic 3 API Guide](https://docs.cartesia.ai/build-with-cartesia/tts-models/latest)

### H5: macOS CS2 support
- **Before:** Listed macOS Steam path for GSI config
- **After:** Clarified: CS2 has no native macOS support (dropped with Source 2/Vulkan). Server code runs on any OS, but CS2+GSI requires Windows or Linux.
- **Source:** [CS2 System Requirements](https://store.steampowered.com/app/730/CounterStrike_2/)

---

## Medium-Priority Fixes

| # | Item | Before | After | Source |
|---|------|--------|-------|--------|
| M1 | Haiku TTFT | ~600ms | ~500-600ms | [Artificial Analysis](https://artificialanalysis.ai/models/claude-4-5-haiku) |
| M2 | Groq Scout TTFT | ~200ms | ~160ms | [Groq Docs](https://console.groq.com/docs/model/meta-llama/llama-4-scout-17b-16e-instruct) |
| M3 | Hume pricing | ~$0.02/min | ~$0.01/min at scale | [Hume Pricing](https://www.hume.ai/pricing) |
| M4 | GSI config path | `csgo/cfg/` | `game/csgo/cfg/` | [CS2 GSI GitHub](https://github.com/antonpup/CounterStrike2GSI) |
| M5 | Voice clone spec | "3 seconds" | "3-5s (Instant Clone); Pro clone: 30+ min" | [Cartesia Clone Docs](https://docs.cartesia.ai/api-reference/voices/clone) |
| M6 | Clone auth header | `X-API-Key` | `Authorization: Bearer <token>` (for clone endpoint) | [Cartesia API Reference](https://docs.cartesia.ai/api-reference/voices/clone) |

---

## Low-Priority Enhancements

| # | Added |
|---|-------|
| L1 | Sonnet model ID: `claude-sonnet-4-5-20250929` |
| L2 | Groq model ID: `meta-llama/llama-4-scout-17b-16e-instruct` |
| L3 | Note: Node.js v22+ supports TS natively as `tsx` alternative |
| L4 | Added `max_buffer_delay_ms` param (set to 1000ms) in input streaming code |
| L5 | Warning: `allplayers_weapons` significantly increases GSI payload size (LAN recommended) |

---

## Unverified Items

These claims could not be fully confirmed and should be tested during implementation:

1. **GSI `previously` field** — The PRD references `previously?: Partial<GSIPayload>` for state diffing. Not explicitly confirmed in current CS2 GSI documentation. May need to implement custom state tracking.
2. **GOTV `allplayers` data access** — GOTV spectator mode should provide full player data, but the exact payload structure via GSI in GOTV context was not explicitly confirmed in search results.
3. **Bomb state granularity** — PRD lists states: `carried`, `planted`, `dropped`, `defusing`, `defused`, `exploded`. Confirmed: `planted`, `exploded`, `defused`. The states `carried`, `dropped`, `defusing` need verification during implementation.

---

## Viability Council Findings (2026-02-13)

> Six parallel research agents assessed the project from every angle. Unanimous verdict: **VIABLE WITH CAVEATS**.

### Council Members & Verdicts

| # | Agent Focus | Verdict | Key Finding |
|---|-----------|---------|-------------|
| 1 | GSI + Event Detection | VIABLE WITH CAVEATS | Use cs2-gsi-z library (MIT, 50+ event types). Custom detectors on top. |
| 2 | LLM Commentary | VIABLE WITH SIGNIFICANT CAVEATS | Prompt-only repetition prevention fails after 30 min. Need explicit dedup + phrase bank. |
| 3 | TTS + Audio Pipeline | VIABLE WITH SIGNIFICANT CAVEATS | Browser/server audio confusion in PRD. Resolved: hybrid architecture (server orchestration → browser Web Audio mixing). |
| 4 | Competition/Prior Art | VIABLE, NOT NOVEL | WSC Sports, IBM Watson (tennis), CerebriumAI (football demo) exist. No CS2-specific open-source competitor. |
| 5 | Dev Approach + Tooling | Node.js CORRECT | Pipecat evaluated and rejected (conversational agent framework, wrong abstraction). |
| 6 | Integration Risks | HIGH-RISK, FEASIBLE | No showstoppers. Concurrency management is biggest engineering challenge. |

### Key Architectural Decisions Made

1. **Hybrid server/browser audio** — Server handles GSI + LLM + TTS orchestration (stateless). Browser handles real-time audio mixing + crowd behavior via Web Audio API (stateful). Server streams TTS audio + event metadata to browser via WebSocket.

2. **cs2-gsi-z as GSI foundation** — MIT library with delta-aware state diffing and 50+ built-in event types. Custom high-level detectors (multi-kill clustering, clutch detection, economy analysis) layered on top. Saves 2-3 weeks vs building from scratch.

3. **ConcurrencyLimiter** — 5 kills in 10 seconds would fire 5 concurrent Claude + TTS requests. Added max 3 Claude req/sec, serial TTS (1 active stream per WebSocket), priority-based queue dropping.

4. **Mandatory Groq fallback** — Not optional. Auto-triggers on Claude 429 or >3s response time.

5. **Commentary deduplication** — Hash-based (Jaccard similarity on word trigrams, reject >80% overlap in rolling window of 10) + phrase bank rotation (10-15 templates per event type).

6. **CrowdBehavior engine** — Arousal model (0-1, decays over time), rhythmic clapping (60-200 BPM), proximity-based anticipation swells, ambient volume modulation. Browser-side.

7. **Pipecat rejected** — Designed for conversational voice agents (turn-based dialogue). Wrong abstraction for one-directional game state commentary.

### PRD Corrections Applied from Council

| Area | PRD Assumption | Corrected To |
|------|----------------|-------------|
| Audio architecture | sox subprocess + GainNode (mixed browser/server) | Hybrid: server TTS → browser Web Audio mixing |
| Commentary repetition | Prompt says "never repeat" | Explicit dedup + phrase bank (prompt-only fails after 30 min) |
| Concurrency | Events fire → parallel LLM + TTS | ConcurrencyLimiter (max 3 req/sec, serial TTS, priority dropping) |
| Timeline | 5 days for Phases 1-4 | 8-10 days for Phase 1-3 MVP |
| Cost | ~$0.80/hr (LLM) | $3-5/match total (~$3.50-5.80/hr). TTS dominates cost. |
| Groq fallback | Optional | Mandatory |
| TTS WebSocket | Single connection assumed | Keepalive ping every 4 min + reconnection with exponential backoff |
| Dependencies | No GSI library | cs2-gsi-z added |
| State management | Implicit | Centralized StateManager (EventEmitter-based, single source of truth) |

### Unresolved Items from Council

These items were flagged by council agents and need verification during implementation:

1. **cs2-gsi-z event type coverage** — Library has 50+ types but exact overlap with our needed event types (multi-kill, clutch, economy) needs testing. Custom detectors will likely still be needed.
2. **Web Audio API latency budget** — Server → browser WebSocket adds ~10-50ms. Need to verify this fits within the 200ms instant clip target.
3. **Crowd behavior CPU in browser** — Arousal model + proximity calculations at 10 updates/sec. Should be fine but profile in browser during sustained play.
4. **Cartesia WebSocket keepalive** — 4-min ping interval is from Pipecat's production deployment. Verify this works with current Cartesia API version (2025-04-16).
