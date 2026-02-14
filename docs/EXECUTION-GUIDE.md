# CS2 AI Live Commentator -- Master Execution Guide

> **Version**: 1.0 | **Created**: 2026-02-13
> **Status**: Greenfield -- PRD finalized, no source code implemented yet.

---

## Document Map

| Document | Location | Purpose |
|----------|----------|---------|
| `CLAUDE.md` | Root (`./CLAUDE.md`) | Quick reference for Claude Code -- commands, key paths, design decisions, build phases at a glance |
| `CS-dev-PRD.md` | `docs/` | Full technical specification -- architecture, component specs, GSI payload schemas, code templates, dependency versions, cost estimates |
| `PRD-ERRATA.md` | `docs/` | Audit trail of all corrections applied to the PRD (model IDs, API versions, deprecated packages, unverified claims) |
| `EXECUTION-GUIDE.md` | `docs/` | **This file** -- step-by-step build instructions, architecture rationale, verification criteria, failure playbook, configuration reference |

> All project docs live in `docs/`. Only `CLAUDE.md` stays in root (required by Claude Code).

**Reading order for a new contributor**: EXECUTION-GUIDE (this file) first, then CS-dev-PRD for implementation details, CLAUDE.md while coding, PRD-ERRATA for gotchas.

---

## Prerequisites

### Software

| Requirement | Version | Notes |
|-------------|---------|-------|
| Node.js | v20+ (v22+ recommended) | v22+ has native TypeScript support as a `tsx` alternative |
| npm | v10+ | Ships with Node.js |
| CS2 | Latest | **Windows or Linux only** -- CS2 dropped macOS with the Source 2/Vulkan migration. The commentator server itself runs on any OS. |
| Git | Any | Version control |
| sox or ffplay | Any | Audio playback -- the `speaker` npm package is unmaintained (2+ years), do not use it |

### API Keys

| Variable | Required | Source |
|----------|----------|--------|
| `ANTHROPIC_API_KEY` | Yes | https://console.anthropic.com/ |
| `CARTESIA_API_KEY` | Yes | https://play.cartesia.ai/ |
| `CARTESIA_VOICE_ID` | Yes (after Phase 3) | Created during voice cloning setup |
| `GROQ_API_KEY` | Optional | https://console.groq.com/ -- speed fallback LLM |

### CS2 Game State Integration

CS2 must be running on Windows or Linux with a spectator client (GOTV) for full 10-player data access. Copy the GSI config file to:

- **Linux**: `~/.steam/steamapps/common/Counter-Strike Global Offensive/game/csgo/cfg/`
- **Windows**: `C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\game\csgo\cfg\`

**Known issue**: Linux dedicated server GSI has a bug (Valve GitHub issue #4071). Use Windows or LAN mode for reliable GSI delivery.

---

## Quick Start

```bash
# 1. Clone and install
git clone <repo-url> cs2-commentator
cd cs2-commentator
npm install

# 2. Configure environment
cp .env.example .env
# Edit .env with your API keys

# 3. Start the commentator server
npx tsx src/index.ts

# 4. Test without a live match
npx tsx scripts/test-gsi.ts

# 5. Pre-generate instant reaction clips (one-time)
npx tsx scripts/generate-clips.ts
```

---

## Architecture Decision Record

These decisions were made by a 6-agent viability council evaluating technology choices against the project's real-time streaming requirements.

### ADR-1: Node.js/TypeScript over Python/Pipecat

| | Decision | Alternative Considered |
|---|---|---|
| **Runtime** | Node.js + TypeScript | Python + Pipecat |
| **Rationale** | Pipecat is designed for conversational AI agents (turn-based dialogue), not unidirectional game commentary. Node.js has superior WebSocket ecosystem, native async streaming, and TypeScript provides type safety for the complex GSI payload schemas. The entire pipeline (HTTP server, WebSocket TTS, audio streaming) is I/O-bound, which is Node.js's strength. |

### ADR-2: cs2-gsi-z for GSI Event Handling

| | Decision | Alternative Considered |
|---|---|---|
| **Library** | cs2-gsi-z | Raw Fastify POST parsing, node-csgo-gsi |
| **Rationale** | cs2-gsi-z is a TypeScript-native, MIT-licensed library with 50+ built-in high-level events (kills, bomb, clutches, economy). It transforms raw GSI JSON into structured, context-aware events, significantly reducing the amount of state-diff logic we need to write ourselves. Includes a GSI config file generator (`GSIConfigWriter.generate()`). Modular and event-driven via `GsiService` + `EVENTS.*` pattern. We still layer custom detectors (multi-kill windows, low-HP plays) on top of its event stream. |

### ADR-3: Hybrid Audio Architecture

| | Decision | Alternative Considered |
|---|---|---|
| **Architecture** | Server handles GSI + LLM + TTS. Browser Web Audio API handles mixing + crowd + output. | Full server-side audio with `speaker` npm package |
| **Rationale** | The `speaker` npm package is unmaintained (2+ years). Web Audio API provides real-time mixing with GainNode ducking, precise timing, cross-platform output, and a natural dashboard UI surface. Server sends PCM/audio buffers to the browser via WebSocket; browser handles final mix and playback. This splits concerns cleanly: server = data pipeline, browser = audio output. |

### ADR-4: Cartesia Sonic 3 as Primary TTS

| | Decision | Alternatives Evaluated |
|---|---|---|
| **TTS Provider** | Cartesia Sonic 3 | ElevenLabs, Hume Octave 2 |
| **Rationale** | Cartesia offers 40ms TTFB (`sonic-turbo`) / sub-100ms (`sonic-3`), the fastest available for real-time commentary. 60+ SSML emotion controls (`<emotion value='excited'/>`) give explicit prosody control for different game events. WebSocket-native streaming with input streaming support (send LLM tokens as they arrive). Instant Voice Cloning from 3-5s of audio. $0.03/min. ElevenLabs is slower and more expensive. Hume auto-detects emotion (less control) and is listed as a fallback if manual SSML tagging proves tedious. |

### ADR-5: Centralized StateManager

| | Decision | Alternative Considered |
|---|---|---|
| **State Pattern** | EventEmitter + in-memory state object | Redux-style store, distributed state |
| **Rationale** | Single-process architecture with no horizontal scaling requirement. An EventEmitter-based StateManager holds current match state (scores, alive counts, economy, round history, player stats) and emits typed events. All components subscribe to the events they care about. Simple, fast, debuggable. The state object serves as the "single source of truth" for the LLM context builder. |

### ADR-6: ConcurrencyLimiter Between Event Queue and LLM/TTS

| | Decision | Alternative Considered |
|---|---|---|
| **Rate Control** | ConcurrencyLimiter: max 3 Claude req/sec, serial TTS | Unbounded parallel requests, external queue (Redis/RabbitMQ) |
| **Rationale** | During rapid multi-kill sequences, 5+ events can fire within 1 second. Without rate limiting, this floods Claude API (429 errors) and creates overlapping TTS audio. The ConcurrencyLimiter sits between the priority event queue and the LLM/TTS pipeline: max 3 concurrent Claude requests per second, serial TTS output (one voice stream at a time). Higher-priority events preempt lower-priority ones in the queue. Local rate limiter also enforces max 45 req/min to stay under Claude's rate limits with safety margin. |

---

## Phase-by-Phase Build Instructions

### Phase 1: GSI + Event Detection (Days 1-3)

**Goal**: CS2 sends game state data, the server detects and logs meaningful events.

#### Steps

1. **Initialize the project**
   ```bash
   mkdir cs2-commentator && cd cs2-commentator
   npm init -y
   npm i fastify@^5 ws@^8 @anthropic-ai/sdk@^0.74 dotenv@^16 pcm-convert@^1 cs2-gsi-z
   npm i -D typescript@^5 tsx@^4 @types/ws@^8 vitest
   ```

2. **Create `tsconfig.json`** with strict mode, ESM module resolution, outDir `dist/`.

3. **Create `src/gsi-server.ts`**
   - Fastify HTTP POST endpoint on port 3001 at `/gsi`.
   - Integrate cs2-gsi-z `GsiService` for structured event parsing.
   - cs2-gsi-z provides `GSIConfigWriter.generate()` to create the GSI config file automatically.

4. **Create `src/events/types.ts`**
   - Define `GameEvent`, `EventPriority` (CRITICAL, HIGH, MEDIUM, LOW) interfaces.

5. **Create `src/events/detector.ts`**
   - Layer custom detectors on top of cs2-gsi-z's built-in events:
     - Multi-kill tracking (2+ kills within 5-second window per player).
     - Clutch detection (1vN situations).
     - Low-HP plays (kill with attacker health <= 20).
     - Economy analysis during freezetime (eco/force/full buy thresholds).

6. **Create `src/events/queue.ts`**
   - Priority queue with debouncing. CRITICAL events always process immediately.

7. **Create the mock GSI replayer** (`scripts/test-gsi.ts`)
   - Reads recorded or synthetic GSI payloads from JSON.
   - POSTs to `localhost:3001/gsi` at configurable intervals (default 100ms).
   - Simulates: warmup, pistol round, kills, bomb plant, defuse, eco, force buy, clutch, overtime.

8. **Generate GSI config** (`config/gamestate_integration_commentator.cfg`)
   - Use cs2-gsi-z's `GSIConfigWriter.generate()` or create manually per the PRD spec.
   - Copy to CS2 cfg directory (Windows/Linux only).

#### Verification Criteria

- [ ] Server starts on port 3001 without errors.
- [ ] Mock replayer sends payloads and server responds 200 OK.
- [ ] Kill events print to console with attacker, victim, weapon, headshot flag.
- [ ] Round start/end events print with round number and score.
- [ ] Bomb plant/defuse/explode events print with state and countdown.
- [ ] Multi-kill events (3+) detected within 5-second windows.
- [ ] Clutch situations (1vN) detected with player name and opponent count.
- [ ] No duplicate events for the same state transition.

---

### Phase 2: LLM Commentary (Days 4-5)

**Goal**: Game events produce natural, varied commentary text via Claude Haiku 4.5.

#### Steps

1. **Create `src/commentary/prompts.ts`**
   - System prompt defining the commentator persona (Anders Blume / HenryG style).
   - Output rules: kill = 1 sentence (5-15 words), clutch = 2-3 sentences, freezetime = 2-3 sentences analysis.
   - SSML emotion tags for Cartesia: `<emotion value='excited'/>`, `<emotion value='tense'/>`, `<emotion value='calm'/>`, `<emotion value='sad'/>`.
   - Anti-repetition rule: never repeat the exact same phrase twice in a match.

2. **Create `src/commentary/context.ts`**
   - `CommentaryContext` interface: current map, round, score, phase, players alive, bomb state.
   - Sliding window: last 30 seconds of events, last 5 commentary outputs.
   - Running match context: round history, player K/D/A stats.

3. **Create `src/commentary/engine.ts`**
   - Streaming client using `@anthropic-ai/sdk`.
   - Primary: Claude Haiku 4.5 (`claude-haiku-4-5-20251001`), `max_tokens: 100`.
   - Analysis (freezetime only): Claude Sonnet 4.5 (`claude-sonnet-4-5-20250929`).
   - Implement deduplication: compare against recent commentary, use a phrase bank to track used expressions.

4. **Implement ConcurrencyLimiter**
   - Max 3 concurrent Claude requests per second.
   - Local rate limiter: max 45 requests per minute.
   - Priority-based preemption: CRITICAL events skip the queue.

5. **Implement Groq fallback**
   - When Claude returns 429 or latency exceeds threshold: fall back to Groq Llama 4 Scout (`meta-llama/llama-4-scout-17b-16e-instruct`, ~160ms TTFT).
   - Groq fallback is mandatory when Claude rate limit is hit, not optional.

6. **Wire the pipeline**: event queue -> ConcurrencyLimiter -> commentary engine -> console output.

#### Verification Criteria

- [ ] Each game event produces commentary text in the console.
- [ ] Kill commentary is 1 sentence, 5-15 words.
- [ ] Clutch commentary is 2-3 sentences with tension language.
- [ ] Freezetime triggers economy/strategy analysis (2-3 sentences).
- [ ] No two identical commentary strings within a match session.
- [ ] CS2 terminology used naturally ("traded out", "eco round", "force buy", "rotate").
- [ ] Commentary references earlier match events ("after that rough pistol round...").
- [ ] Groq fallback activates when Claude returns 429 (test by lowering rate limit).
- [ ] ConcurrencyLimiter prevents more than 3 simultaneous Claude requests.
- [ ] Empty string returned during uneventful periods (no filler).

---

### Phase 3: TTS + Audio (Days 6-7)

**Goal**: Commentary text is converted to speech and played through speakers.

#### Steps

1. **Sign up for Cartesia** at https://play.cartesia.ai/.

2. **Clone a voice**
   - Upload 3-5 seconds of clean caster audio (Instant Clone).
   - For higher fidelity: Pro Clone requires 30+ minutes of audio.
   - Save the returned `voiceId` as `CARTESIA_VOICE_ID` in `.env`.
   - API version: `2025-04-16`. Auth: `Authorization: Bearer <token>`.

3. **Create `src/tts/cartesia.ts`**
   - WebSocket client connecting to `wss://api.cartesia.ai/tts/websocket?api_key=...&cartesia_version=2025-04-16`.
   - Input streaming: send LLM tokens as they arrive (`continue: true`), signal end with `continue: false`.
   - Output format: `pcm_f32le` at 44100 Hz.
   - `context_id` per utterance for voice consistency.
   - `max_buffer_delay_ms: 1000` (lower than default 3000ms for live commentary responsiveness).
   - **Keepalive**: Send a ping every 4 minutes to prevent the 5-minute idle timeout.
   - **Reconnection**: Exponential backoff with 3 attempts on WebSocket drop.

4. **Create browser-side Web Audio dashboard** (`src/web/`)
   - HTML page with Web Audio API AudioContext.
   - Receives PCM audio buffers from server via WebSocket.
   - Plays through AudioBufferSourceNode with GainNode for volume control.

5. **Wire the full pipeline**: event -> LLM streaming tokens -> Cartesia WebSocket -> PCM chunks -> browser WebSocket -> Web Audio playback.

#### Verification Criteria

- [ ] Cartesia WebSocket connects successfully.
- [ ] Audio plays within 2-3 seconds of a game event.
- [ ] Voice matches the cloned caster profile.
- [ ] SSML emotion tags produce audible prosody changes (excited vs. calm).
- [ ] Keepalive prevents disconnection during a 10-minute idle test.
- [ ] Reconnection recovers from a simulated WebSocket drop within 5 seconds.
- [ ] No audio artifacts or gaps between streaming chunks.
- [ ] Browser dashboard displays connection status.

---

### Phase 4: Two-Tier + Crowd (Days 8-9)

**Goal**: Instant reactions play immediately, contextual commentary follows, crowd sounds create atmosphere.

#### Steps

1. **Create `scripts/generate-clips.ts`**
   - For each category (kill, headshot, multi_kill, ace, clutch_start, clutch_win, bomb_planted, bomb_defused, round_start, whiff, save), generate 5-10 clips via Cartesia API.
   - Save as `.wav` files in `assets/clips/{category}/{index}.wav`.
   - Use the cloned voice for consistency.

2. **Run clip generation**: `npx tsx scripts/generate-clips.ts` -- fills `assets/clips/`.

3. **Source crowd sound effects** and place in `assets/crowd/`:
   - `ambient.wav` -- low murmur loop
   - `cheer-small.wav` -- polite clap (kills)
   - `cheer-big.wav` -- loud cheer (multi-kills)
   - `roar.wav` -- stadium roar (aces, clutch wins)
   - `gasp.wav` -- near-misses, bomb plant
   - `groan.wav` -- whiffs, failed clutches
   - `tension-rise.wav` -- building tension loop (clutch situations)
   - `explosion.wav` -- bass hit (bomb explode)

4. **Create `src/tts/clips.ts`**
   - Loads all pre-cached clips into memory at startup.
   - Random selection within each category (no immediate repeats).

5. **Create `src/audio/crowd.ts`** -- Crowd behavior engine:
   - **Arousal model**: Numeric arousal level (0.0-1.0) that decays over time. Events increase arousal; crowd intensity tracks arousal level.
   - **Arousal decay**: Configurable decay rate (default: 0.05/sec toward baseline 0.2).
   - **Proximity detection**: If multiple events happen within a short window, arousal stacks.
   - **Rhythmic clapping**: At sustained mid-arousal (0.4-0.6), trigger rhythmic clap pattern.
   - Event-to-crowd mapping: kill -> cheer-small (arousal +0.15), multi-kill -> cheer-big (arousal +0.35), ace -> roar (arousal = 1.0), clutch_start -> tension-rise (loop), clutch_win -> roar (arousal = 1.0), bomb_planted -> gasp (arousal +0.2), bomb_exploded -> explosion (arousal +0.3).

6. **Create `src/audio/mixer.ts`** -- Browser-side Web Audio mixer:
   - Three GainNodes: ambient (base 0.3), commentary (base 1.0), crowd (dynamic).
   - Ducking: lower ambient to 0.1-0.2 during commentary, restore over 500ms after.
   - Two-tier playback: instant clip plays immediately on event, LLM+TTS commentary plays after clip finishes (crossfade if needed).

7. **Wire two-tier flow**:
   - Event fires -> instant clip plays in <200ms.
   - Simultaneously: event -> LLM -> TTS -> full commentary plays ~2s later.
   - Crowd sounds trigger based on arousal model.
   - Ambient loop plays continuously at low volume.

#### Verification Criteria

- [ ] Kill event -> instant clip plays in <200ms.
- [ ] Full LLM commentary follows ~2 seconds after the instant clip.
- [ ] No audio overlap between instant clip and full commentary.
- [ ] Crowd cheers audible after kills, roars after aces.
- [ ] Tension loop starts during clutch situations, stops on resolution.
- [ ] Ambient crowd murmur plays continuously at low volume.
- [ ] Commentary volume ducks ambient during speech.
- [ ] Arousal model increases on rapid events, decays during quiet periods.
- [ ] Rhythmic clapping triggers at sustained mid-arousal.
- [ ] No clip repeats back-to-back within the same category.

---

### Phase 5: Polish (Days 10+)

**Goal**: Production readiness, extended features.

| Feature | Description |
|---------|-------------|
| Web dashboard | Live game state visualization, event log, commentary log, audio controls |
| OBS integration | Virtual audio cable (VB-Cable on Windows, BlackHole on macOS) for stream overlay |
| Player knowledge base | Team names, player histories, playstyles for informed commentary |
| Economy tracking | Buy round predictions based on loss bonus mechanics |
| Multi-language | Switch commentary language; leverage Cartesia's multi-language support |
| Commentary intensity slider | Adjustable frequency/verbosity from "minimal" to "hype" |
| Style presets | Hype caster, analytical caster, meme caster personas |
| Dual caster mode | Two LLM agents -- play-by-play + analyst -- that "converse" with each other |

---

## Testing Strategy

### Unit Tests (vitest)

| Component | What to Test |
|-----------|-------------|
| Event Detector | State diff produces correct events for known GSI payload pairs |
| Multi-kill Tracker | 5-second window correctly groups kills by player |
| Clutch Detector | 1vN detection across CT and T sides |
| Economy Analyzer | Eco/force/full buy thresholds with edge cases |
| Context Builder | Sliding window correctly limits to 30s events and 5 recent commentaries |
| ConcurrencyLimiter | Max 3 concurrent, priority preemption, 45/min rate limit |
| Clip Selector | No immediate repeats, all categories covered |
| Arousal Model | Decay rate, stacking, clamp to 0.0-1.0 range |

### Integration Tests

| Test | Method |
|------|--------|
| GSI -> Events | Mock replayer posts synthetic payloads, assert correct events emitted |
| Events -> Commentary | Feed known events to commentary engine, assert text output matches style rules |
| Commentary -> TTS | Send known text to Cartesia, assert audio buffer returned |
| Full pipeline | Mock replayer -> server -> events -> LLM (mocked) -> TTS (mocked) -> audio output |

### End-to-End Tests

| Test | Method |
|------|--------|
| Recorded match replay | Replay a full recorded GSI session, verify commentary covers all major events |
| Stress test | Replay at 5x speed, verify no crashes, no audio overlap, rate limits respected |
| Long session | 60-minute simulated match, verify no memory leaks, commentary stays varied |

### Mock GSI Replayer

The mock replayer (`scripts/test-gsi.ts`) is the primary development tool. It supports:
- Configurable playback speed (1x, 2x, 5x).
- Scenario selection: pistol round, eco round, clutch, overtime.
- Recording mode: log live GSI payloads to JSON for later replay.

---

## Configuration Reference

All configuration should be centralizable in a config file or environment variables. Below is the complete reference.

### LLM Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `LLM_PRIMARY_MODEL` | `claude-haiku-4-5-20251001` | Primary commentary model |
| `LLM_ANALYSIS_MODEL` | `claude-sonnet-4-5-20250929` | Deeper analysis during freezetime |
| `LLM_FALLBACK_MODEL` | `meta-llama/llama-4-scout-17b-16e-instruct` | Groq speed fallback |
| `LLM_MAX_TOKENS` | `100` | Max output tokens per commentary request |
| `LLM_RATE_LIMIT_PER_SEC` | `3` | Max concurrent Claude requests per second |
| `LLM_RATE_LIMIT_PER_MIN` | `45` | Max total Claude requests per minute |
| `LLM_STYLE` | `hype` | Commentary style: `hype`, `analytical`, `balanced`, `meme` |
| `LLM_BACKOFF_DURATION_MS` | `30000` | Backoff duration on 429 rate limit |

### TTS Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `TTS_PROVIDER` | `cartesia` | TTS provider: `cartesia`, `hume` |
| `TTS_MODEL` | `sonic-3` | Cartesia model: `sonic-3`, `sonic-turbo` |
| `TTS_SAMPLE_RATE` | `44100` | Audio sample rate in Hz |
| `TTS_ENCODING` | `pcm_f32le` | Audio encoding format |
| `TTS_MAX_BUFFER_DELAY_MS` | `1000` | Max buffer delay for input streaming |
| `TTS_KEEPALIVE_INTERVAL_MS` | `240000` | WebSocket keepalive ping interval (4 minutes) |
| `TTS_RECONNECT_ATTEMPTS` | `3` | Max reconnection attempts on drop |
| `TTS_LATENCY_TARGET_MS` | `200` | Target latency for instant clips |

### Audio Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `AUDIO_AMBIENT_VOLUME` | `0.3` | Ambient crowd loop base volume (0.0-1.0) |
| `AUDIO_COMMENTARY_VOLUME` | `1.0` | Commentary voice volume (0.0-1.0) |
| `AUDIO_CROWD_VOLUME` | `0.6` | Crowd reaction max volume (0.0-1.0) |
| `AUDIO_DUCK_TARGET` | `0.15` | Ambient volume during commentary ducking |
| `AUDIO_DUCK_RESTORE_MS` | `500` | Time to restore ambient volume after commentary |

### Crowd Behavior Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `CROWD_AROUSAL_BASELINE` | `0.2` | Resting arousal level |
| `CROWD_AROUSAL_DECAY_PER_SEC` | `0.05` | Arousal decay rate per second toward baseline |
| `CROWD_AROUSAL_MAX` | `1.0` | Maximum arousal level |
| `CROWD_PROXIMITY_WINDOW_MS` | `3000` | Window for detecting rapid event proximity |
| `CROWD_CLAP_AROUSAL_MIN` | `0.4` | Minimum sustained arousal to trigger rhythmic clapping |
| `CROWD_CLAP_AROUSAL_MAX` | `0.6` | Maximum arousal for clapping (above this: cheering instead) |
| `CROWD_CLAP_SUSTAIN_MS` | `5000` | How long arousal must stay in clap range before triggering |

### Debug Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `DEBUG_LOG_GSI_PAYLOADS` | `false` | Log raw GSI payloads to console |
| `DEBUG_LOG_EVENTS` | `true` | Log detected game events |
| `DEBUG_LOG_COMMENTARY` | `true` | Log generated commentary text |
| `DEBUG_LOG_TTS_LATENCY` | `false` | Log TTS TTFB and total latency |
| `DEBUG_LOG_AUDIO_LEVELS` | `false` | Log audio mixer gain levels |
| `DEBUG_SKIP_TTS` | `false` | Skip TTS (text-only mode for faster dev) |
| `DEBUG_SKIP_AUDIO` | `false` | Skip all audio output |

---

## Failure Playbook

### Cartesia WebSocket Drops

**Symptoms**: TTS audio stops mid-match. WebSocket `close` event fires.

**Cause**: Cartesia enforces a 5-minute idle timeout. Network instability can also cause drops.

**Recovery**:
1. Keepalive ping every 4 minutes (`TTS_KEEPALIVE_INTERVAL_MS`).
2. On `close` event: exponential backoff reconnection (1s, 2s, 4s), max 3 attempts (`TTS_RECONNECT_ATTEMPTS`).
3. During reconnection: queue commentary text, play from queue once reconnected.
4. After 3 failed attempts: log error, fall back to text-only mode, alert via dashboard.

```typescript
// Reconnection pseudocode
async function reconnectCartesia(attempt = 1): Promise<void> {
  if (attempt > TTS_RECONNECT_ATTEMPTS) {
    logger.error("Cartesia reconnection failed after 3 attempts, falling back to text-only");
    return;
  }
  const delay = Math.pow(2, attempt - 1) * 1000; // 1s, 2s, 4s
  await sleep(delay);
  try {
    await connectWebSocket();
    logger.info("Cartesia reconnected on attempt " + attempt);
  } catch {
    await reconnectCartesia(attempt + 1);
  }
}
```

### Claude 429 Rate Limit

**Symptoms**: Claude API returns HTTP 429 Too Many Requests.

**Cause**: Exceeded API rate limits. Rapid game events (multi-kill sequences) can fire 5+ LLM requests in 1 second.

**Recovery**:
1. Local rate limiter prevents most 429s: max 45 req/min, max 3 concurrent/sec.
2. On 429: backoff for 30 seconds (`LLM_BACKOFF_DURATION_MS`).
3. **Groq fallback is mandatory** during backoff -- switch all commentary to Groq Llama 4 Scout.
4. After backoff: resume Claude requests, keeping Groq as hot standby.
5. Log rate limit events for tuning the local limiter.

### GSI Stops Sending Data

**Symptoms**: No GSI payloads received for an extended period.

**Cause**: CS2 crashed, match ended, network issue, or GSI config not loaded.

**Recovery**:
1. Heartbeat timeout: if no GSI payload received in 30 seconds, trigger warning.
2. After 30s timeout: emit `gsi_timeout` event.
3. Dashboard shows "GSI disconnected" status.
4. Graceful shutdown: fade out crowd sounds, stop commentary engine, keep server running for reconnection.
5. When GSI resumes: automatically re-initialize state, log gap duration.

### Audio Output Crash

**Symptoms**: Browser tab crashes or audio context suspends.

**Cause**: Browser auto-suspend policy, memory pressure, tab backgrounded.

**Recovery**:
1. Browser Web Audio API `AudioContext.state` monitoring -- if `suspended`, call `resume()`.
2. If browser tab crashes: server continues buffering audio, new tab connects and resumes.
3. Fallback: server-side `sox` / `ffplay` playback via `child_process.spawn`.

---

## Known Limitations

### Platform Constraints
- **CS2 requires Windows or Linux**. macOS has no native CS2 support (dropped with Source 2/Vulkan). The commentator server itself runs on any OS including macOS -- only the game client with GSI needs Windows/Linux.
- **Linux dedicated server GSI bug** (Valve GitHub issue #4071). GSI payloads may not send reliably from Linux dedicated servers. Workaround: use Windows, or test on LAN with a local client.

### GSI Data Gaps
- **Bomb states**: `planted`, `exploded`, and `defused` are confirmed. The states `carried`, `dropped`, and `defusing` are **unverified** in CS2 GSI and need testing during implementation (see PRD-ERRATA, Unverified Item #3).
- **`previously` field**: The GSI `previously` object for state diffing is not explicitly confirmed in current CS2 documentation. cs2-gsi-z may handle this internally; otherwise implement custom state tracking.
- **GOTV `allplayers` access**: Expected to provide full 10-player data but exact payload structure in GOTV context needs verification.

### TTS Constraints
- **Cartesia WebSocket 5-minute idle timeout**. Must implement keepalive (ping every 4 min) and reconnection logic.
- **Cartesia API version**: `2025-04-16`. Breaking changes from earlier versions: embeddings removed, `/voices/create` deprecated, stability clones removed. Only similarity clones supported.

### Commentary Quality
- **Repetition after 45+ minutes**. Despite deduplication (phrase bank, recent commentary window), Claude's outputs tend to converge on similar phrases in long sessions. Mitigations: larger phrase bank, style rotation, explicit "do not use" lists seeded with recent outputs.
- **Emotion tag fidelity**. SSML emotion tags produce noticeable but not dramatic prosody changes. Intense moments may need ALL CAPS + exclamation marks in addition to emotion tags.

### Cost
- **$3-5 per match** ($3.50-5.80/hr). TTS dominates cost at ~$1.80/hr (Cartesia). LLM costs ~$0.80-1.80/hr depending on Sonnet 4.5 usage.
- **Cost reduction options**: Switch to Hume ($0.01/min) or self-hosted Fish Audio ($0/min) for TTS. Use Groq free tier as primary LLM (quality tradeoff).

---

## Dependency Reference

### Production Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `fastify` | `^5.x` | HTTP server for GSI POST endpoint |
| `@anthropic-ai/sdk` | `^0.74.x` | Claude API client (not at 1.x yet) |
| `ws` | `^8.x` | WebSocket client for Cartesia TTS |
| `cs2-gsi-z` | latest | CS2 GSI event handling (50+ built-in events, TypeScript, MIT) |
| `pcm-convert` | `^1.x` | PCM audio format conversion |
| `dotenv` | `^16.x` | Environment variable loading |

### Dev Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `typescript` | `^5.x` | Type checking and compilation |
| `tsx` | `^4.x` | TypeScript execution for development |
| `@types/ws` | `^8.x` | WebSocket type definitions |
| `vitest` | latest | Test runner |

### System Dependencies

| Tool | Purpose | Notes |
|------|---------|-------|
| `sox` or `ffplay` | Audio playback fallback | Server-side playback if browser unavailable |

---

## Project Structure

```
cs2-commentator/
├── package.json
├── tsconfig.json
├── .env                              # API keys (never commit)
├── .env.example                      # Template for required env vars
├── CS-dev-PRD.md                     # Full technical specification
├── CLAUDE.md                         # Claude Code quick reference
├── PRD-ERRATA.md                     # Audit trail of PRD corrections
├── EXECUTION-GUIDE.md                # This file
├── src/
│   ├── index.ts                      # Entry point, wires all components
│   ├── gsi-server.ts                 # Fastify + cs2-gsi-z GSI server
│   ├── state-manager.ts              # Centralized EventEmitter + state
│   ├── concurrency-limiter.ts        # Rate limiter for LLM/TTS pipeline
│   ├── events/
│   │   ├── types.ts                  # GameEvent, EventPriority interfaces
│   │   ├── detector.ts              # Custom event detectors (multi-kill, clutch, economy)
│   │   └── queue.ts                 # Priority event queue with debouncing
│   ├── commentary/
│   │   ├── engine.ts                # Claude Haiku 4.5 streaming + Groq fallback
│   │   ├── prompts.ts               # System prompts, persona definitions
│   │   └── context.ts               # Sliding window context builder
│   ├── tts/
│   │   ├── cartesia.ts              # Cartesia WebSocket client (keepalive + reconnection)
│   │   ├── clips.ts                 # Pre-cached instant reaction clip manager
│   │   └── voice-clone.ts           # One-time voice cloning utility
│   ├── audio/
│   │   ├── mixer.ts                 # Audio mixing logic (server-side coordination)
│   │   ├── crowd.ts                 # Crowd behavior engine (arousal model)
│   │   └── output.ts               # Output routing (WebSocket to browser, fallback to sox)
│   └── web/
│       ├── index.html               # Browser dashboard
│       └── dashboard.ts             # Web Audio API mixer + playback
├── assets/
│   ├── clips/                        # Pre-generated instant reaction .wav files
│   │   ├── kill/
│   │   ├── headshot/
│   │   ├── ace/
│   │   ├── clutch_start/
│   │   ├── clutch_win/
│   │   ├── bomb_planted/
│   │   ├── bomb_defused/
│   │   ├── round_start/
│   │   ├── whiff/
│   │   └── save/
│   └── crowd/                        # Crowd sound effects
│       ├── ambient.wav
│       ├── cheer-small.wav
│       ├── cheer-big.wav
│       ├── roar.wav
│       ├── gasp.wav
│       ├── groan.wav
│       ├── tension-rise.wav
│       └── explosion.wav
├── config/
│   └── gamestate_integration_commentator.cfg
├── scripts/
│   ├── generate-clips.ts            # Pre-generate TTS clips via Cartesia API
│   └── test-gsi.ts                  # Mock GSI replayer for development
└── tests/
    ├── events/
    │   ├── detector.test.ts
    │   └── queue.test.ts
    ├── commentary/
    │   ├── engine.test.ts
    │   └── context.test.ts
    ├── tts/
    │   └── cartesia.test.ts
    └── audio/
        ├── crowd.test.ts
        └── mixer.test.ts
```

---

## Latency Budget Summary

| Pipeline Stage | Target | Cumulative |
|----------------|--------|------------|
| GSI delivery (CS2 -> server) | 100ms | 100ms |
| Event detection (state diff) | <10ms | 110ms |
| **Tier 1: Pre-cached clip** | **<200ms total** | **<200ms** |
| LLM streaming TTFT | 500-1500ms | 1600ms |
| TTS streaming TTFB | 40-100ms | 1700ms |
| Audio mixing + playback | <20ms | 1720ms |
| **Tier 2: Full commentary** | **~2-3s total** | **~2-3s** |

The two-tier strategy ensures immediate audio feedback (<200ms) for every significant event, while rich contextual commentary follows within 2-3 seconds.

---

## Cost Summary

| Component | Provider | Cost/Hour |
|-----------|----------|-----------|
| LLM (primary) | Claude Haiku 4.5 | ~$0.80 |
| LLM (analysis, freezetime only) | Claude Sonnet 4.5 | ~$1.00 |
| TTS | Cartesia Sonic 3 | ~$1.80 |
| **Total** | | **$3.50-5.80/hr** |

Per match (assuming 45-60 minutes): **$3-5**.

**Budget alternatives**: Hume Octave 2 TTS ($0.01/min) reduces total to ~$1.40/hr. Groq free tier as primary LLM reduces to near-zero LLM cost (quality tradeoff).
