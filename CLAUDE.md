# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **PUBLIC REPOSITORY** — This repo is public on GitHub. Never commit API keys, secrets, credentials, .env files, or any proprietary/sensitive information. Use environment variables for all secrets and ensure `.gitignore` covers sensitive files.

## Project Overview

CS2 AI Live Commentator — a real-time streaming pipeline that watches CS2 matches via Game State Integration (GSI), generates commentary with an LLM, converts it to speech via Cartesia TTS, and mixes it with crowd sounds + a live crowd behavior engine for broadcast-quality audio.

**Documents** (all in `docs/`):
- `docs/CS-dev-PRD.md` — Full technical specification (WHAT to build)
- `docs/PRD-ERRATA.md` — Audit trail of corrections + viability council findings
- `docs/EXECUTION-GUIDE.md` — Master build guide (HOW to build it, step by step)

> **IMPORTANT**: Before starting any implementation work, read `docs/EXECUTION-GUIDE.md` for build instructions and `docs/CS-dev-PRD.md` for full component specs, code templates, and API details. Check `docs/PRD-ERRATA.md` for known gotchas and unverified items. All project docs live in `docs/`, not root. Only this file (`CLAUDE.md`) stays in root.

**Status**: Greenfield — PRD complete, no source code implemented yet.

## Architecture (Hybrid Server/Browser)

```
CS2 (GOTV spectator, Windows/Linux only) → GSI HTTP POST (10 req/sec)
  → Fastify server (port 3001)
    → cs2-gsi-z (state diffing, 50+ built-in event types)
      → Custom Event Detectors (multi-kill, clutch, economy)
        → ConcurrencyLimiter (max 3 Claude req/sec, priority-based dropping)
          ├─ CRITICAL/HIGH → Pre-cached clip + LLM commentary
          └─ MEDIUM/LOW → LLM commentary only
              → Claude Haiku 4.5 (primary) / Groq Llama 4 Scout (fallback)
                → Commentary Dedup (hash-based, reject >80% overlap)
                  → Cartesia TTS (WebSocket, keepalive ping every 4 min)
                    → WebSocket to Browser
                      → Web Audio API Mixer (commentary + crowd + ambient)
                        → CrowdBehavior engine (arousal model, rhythmic clapping, proximity)
                          → Output (local speaker / OBS captures browser audio)
```

**Key architectural decisions**:
- **Server**: Stateless orchestration (GSI + LLM + TTS)
- **Browser**: Stateful audio mixing + crowd behavior via Web Audio API
- **StateManager**: Centralized in-memory state (EventEmitter-based, single source of truth)
- **Pipecat evaluated and rejected** — designed for conversational voice agents, wrong abstraction for game state commentary

## Commands

```bash
npm install                              # Install dependencies
npx tsx src/index.ts                     # Start the commentator server
npx tsx scripts/generate-clips.ts        # Pre-generate instant reaction TTS clips (one-time)
npx tsx scripts/test-gsi.ts              # Mock GSI replayer for dev without live CS2
npx vitest                               # Run tests
npx vitest run                           # Run tests once (no watch)
npm run build && npm start               # Compile and run
```

## Environment Variables (.env)

```
ANTHROPIC_API_KEY=sk-ant-...       # Claude API (commentary LLM)
CARTESIA_API_KEY=...               # Cartesia TTS
CARTESIA_VOICE_ID=...              # Cloned voice ID (after voice-clone setup)
GROQ_API_KEY=...                   # Mandatory fallback LLM
```

## Key Components

| Component | Planned Path | Purpose |
|-----------|-------------|---------|
| GSI Server | `src/gsi-server.ts` | Fastify HTTP POST endpoint receiving CS2 game state |
| StateManager | `src/state/manager.ts` | Centralized in-memory state, EventEmitter-based |
| Event Detector | `src/events/detector.ts` | High-level detectors on top of cs2-gsi-z |
| Proximity | `src/events/proximity.ts` | Player proximity detection from GSI positions |
| ConcurrencyLimiter | `src/events/queue.ts` | Priority queue, max 3 LLM req/sec, priority-based dropping |
| Commentary Engine | `src/commentary/engine.ts` | Claude Haiku 4.5 streaming commentary |
| Groq Fallback | `src/commentary/fallback.ts` | Groq Llama 4 Scout (mandatory, triggers on 429/timeout) |
| Commentary Dedup | `src/commentary/dedup.ts` | Hash-based dedup + phrase bank rotation |
| Prompts | `src/commentary/prompts.ts` | Commentator persona (Anders Blume/HenryG style) |
| Context Builder | `src/commentary/context.ts` | Sliding window: last 30s events + last 5 commentaries |
| Cartesia TTS | `src/tts/cartesia.ts` | WebSocket TTS (keepalive every 4 min, reconnect with backoff) |
| Clip Manager | `src/tts/clips.ts` | Pre-cached instant reaction clip loader/selector |
| Audio Mixer | `src/audio/mixer.ts` | Browser-side: Web Audio API real-time mixing |
| CrowdBehavior | `src/audio/crowd-behavior.ts` | Browser-side: arousal model, rhythmic clapping, proximity |
| Entry Point | `src/index.ts` | Orchestrates all server-side components |

## Key Design Decisions

- **cs2-gsi-z as GSI foundation**: MIT library with 50+ event types and delta-aware state diffing. Custom detectors (multi-kill clustering, clutch detection, economy analysis) layered on top. Saves weeks vs building from scratch.
- **Hybrid server/browser audio**: Server handles GSI + LLM + TTS orchestration (stateless). Browser handles audio mixing + crowd behavior via Web Audio API (stateful). Server streams TTS audio + event metadata to browser via WebSocket.
- **ConcurrencyLimiter**: 5 kills in 10 seconds = 5 concurrent LLM + TTS requests = chaos. Limit to max 3 Claude req/sec, serial TTS (1 active stream per WebSocket), priority-based queue dropping for lower-priority events.
- **Commentary dedup**: Hash last 10 commentaries, reject >80% overlap (Jaccard similarity on word trigrams) + phrase bank with 10-15 templates per event type, rotated.
- **Groq fallback is mandatory**: Groq Llama 4 Scout (`meta-llama/llama-4-scout-17b-16e-instruct`, ~160ms TTFT) auto-triggers on Claude 429 or >3s response time. Not optional.
- **Streaming-first**: LLM tokens stream directly to Cartesia TTS input streaming → audio chunks stream to browser. No buffering between stages.
- **Claude Haiku 4.5 as primary LLM** (`claude-haiku-4-5-20251001`, ~500-600ms TTFT, max_tokens=100). Sonnet 4.5 (`claude-sonnet-4-5-20250929`) for analysis during freezetime only.
- **Cartesia Sonic 3**: `sonic-turbo` for 40ms TTFB / `sonic-3` for sub-100ms. Keepalive ping every 4 min (5-min idle timeout). Reconnection with exponential backoff (1s/2s/4s, 3 attempts). API version: `2025-04-16`. Serial TTS only.
- **SSML emotion tags**: `<emotion value='excited'/>text` — Cartesia interprets these for prosody. Also supports `[laughter]`.
- **Crowd behavior engine**: Arousal model (0-1, decays over time), rhythmic clapping (60-200 BPM scaled by arousal), proximity-based anticipation swells, ambient volume modulation. Runs in browser.
- **Audio output via Web Audio API primarily**: sox/ffplay as fallback for server-side testing. The `speaker` npm package is unmaintained — avoid it.
- **Spectator mode required**: GOTV spectator client provides full 10-player data. CS2 requires Windows/Linux (no macOS). Server code runs on any OS.
- **Anthropic SDK**: `@anthropic-ai/sdk` ^0.74.x (not at 1.x yet).
- **Cost**: $3-5/match (~$3.50-5.80/hr). TTS dominates cost (~$1.80-3.50/hr). LLM is ~$0.40-0.90/hr.

## Event Priority System

- **CRITICAL**: Multi-kills (3+), aces, clutch situations → instant clip + immediate LLM commentary
- **HIGH**: Single kills, headshots, bomb planted/defused → instant clip, LLM queued
- **MEDIUM**: Round start/end, economy analysis → LLM commentary only
- **LOW**: General context → batched, used as filler during quiet moments

## Build Phases (Realistic Timeline: 8-10 days for MVP)

1. **Phase 1 (Days 1-3)**: GSI + cs2-gsi-z + Event Detection + StateManager + ConcurrencyLimiter + mock replayer + tests
2. **Phase 2 (Days 4-5)**: LLM Commentary + Groq fallback + dedup + phrase bank
3. **Phase 3 (Days 6-7)**: TTS with WebSocket lifecycle (keepalive, reconnect) + basic audio output
4. **Phase 4 (Days 8-9)**: Two-tier clips + browser audio mixing + crowd behavior engine
5. **Phase 5 (Days 10+)**: Polish — web dashboard, OBS, player knowledge, multi-language

## CS2 GSI Setup

Copy `config/gamestate_integration_commentator.cfg` to your CS2 cfg directory:
- Linux: `~/.steam/steamapps/common/Counter-Strike Global Offensive/game/csgo/cfg/`
- Windows: `C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\game\csgo\cfg\`
- Note: CS2 has no native macOS support.

## Dependencies

Production: `fastify`, `@anthropic-ai/sdk` (^0.74.x), `groq-sdk`, `cs2-gsi-z`, `ws`, `pcm-convert`, `dotenv`
Dev: `typescript`, `tsx`, `vitest`, `@types/ws`
Audio: Web Audio API (browser) / `sox`/`ffplay` via child_process (server testing fallback)

---

## Python Emotion Detector (Step 1 MVP)

Standalone Python webcam emotion detection. Will eventually feed into the commentator system.

**Location**: `python/`
**Docs**: `docs/EMOTION-DETECTOR-PRD.md`

### Commands

```bash
cd python && python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt        # First run downloads DeepFace model (~100MB)
python main.py                         # Start emotion detection (press 'q' to quit)
python main.py --camera 1              # Use alternate camera
python -m pytest tests/ -v             # Run tests
```

### Architecture

Three-thread pipeline: `WebcamCapture` (daemon) → `EmotionDetector`/DeepFace (daemon) → `AnnotatedDisplay` (main thread).
Emits `EmotionEvent` JSON to stdout on emotion changes (debounced, smoothed).

### Roadmap

1. **Step 1 (current)**: Webcam → face detection → emotion recognition → live annotated preview
2. **Step 2**: Add screen capture (`mss` library) to see what user is doing
3. **Step 3**: Feed emotions + screen context into LLM for spoken "work mode" commentary via WebSocket bridge to Node.js
