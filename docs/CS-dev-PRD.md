# CS2 AI Live Commentator — Product Requirements Document

> **PUBLIC REPOSITORY** — This repo is public on GitHub. Do not include API keys, secrets, credentials, or proprietary information anywhere in the codebase. All secrets must be provided via environment variables at runtime.

> A complete, execution-ready PRD. Pick this up at any time and build it.

## 1. Product Overview

### What
An AI system that watches CS2 matches via Game State Integration (GSI), generates real-time commentary using an LLM, converts it to speech via streaming TTS, and mixes it with crowd sounds for a full broadcast-quality audio experience.

### Why
No open-source AI CS2 commentator exists. The pieces are all available (GSI, fast LLMs, sub-100ms TTS with voice cloning), but nobody has wired them together. This would be novel and immediately useful for private servers, practice matches, and content creation.

### Setup Context
- Private CS2 servers with a dedicated spectator client (GOTV) — full data access to all 10 players
- Premium models (no cost constraints)
- No ElevenLabs (Cartesia Sonic 3 is faster, cheaper, more controllable)

---

## 2. Architecture

```
┌─────────────┐     HTTP POST      ┌──────────────┐     events     ┌───────────────┐
│   CS2 Game  │ ──────────────────→ │  GSI Server  │ ─────────────→ │ Event Detector│
│  (spectator)│    ~10 req/sec      │  (Fastify)   │                │  (state diff) │
└─────────────┘                     └──────────────┘                └───────┬───────┘
                                                                           │
                                                              ┌────────────┴────────────┐
                                                              │                         │
                                                         HIGH priority            LOW priority
                                                              │                         │
                                                    ┌─────────▼─────────┐    ┌──────────▼──────────┐
                                                    │  Pre-cached Clip  │    │    LLM Commentary   │
                                                    │   (<200ms play)   │    │  (Claude Haiku 4.5) │
                                                    └─────────┬─────────┘    └──────────┬──────────┘
                                                              │                         │
                                                              │              ┌──────────▼──────────┐
                                                              │              │   Cartesia TTS      │
                                                              │              │  (Sonic 3, 40ms)    │
                                                              │              └──────────┬──────────┘
                                                              │                         │
                                                    ┌─────────▼─────────────────────────▼─────────┐
                                                    │              Audio Mixer                     │
                                                    │  (commentary + crowd sounds + ambient)       │
                                                    └─────────────────────┬────────────────────────┘
                                                                         │
                                                              ┌──────────▼──────────┐
                                                              │      Output         │
                                                              │ Speaker / OBS / Web │
                                                              └─────────────────────┘
```

### Key Architectural Additions (from viability council)

**ConcurrencyLimiter** — Sits between Event Queue and LLM/TTS. Max 3 Claude requests/sec (well under 50 req/min API limit). Serial TTS: 1 active Cartesia stream per WebSocket (don't multiplex). CRITICAL events never drop; LOW events auto-drop if queue exceeds 3 pending.

**StateManager** — Centralized in-memory state store (EventEmitter-based). Single source of truth for: match state, player stats, event queue status, commentary history, TTS connection state. Persists to disk for crash recovery. Exposed via WebSocket to browser dashboard.

**Hybrid Audio Architecture** — Server stays stateless (GSI + LLM + TTS orchestration only). Server streams TTS audio chunks + event metadata to browser via WebSocket. Browser uses Web Audio API for real-time mixing (commentary + clips + crowd + ambient) with GainNode ducking. OBS captures browser audio output.

**cs2-gsi-z Integration** — Use the cs2-gsi-z TypeScript library (MIT, 50+ built-in event types, delta-aware state diffing) as the GSI foundation. Custom high-level detectors (multi-kill clustering, clutch detection, economy analysis) are layered on top.

### Latency Budget

| Step | Target | Notes |
|------|--------|-------|
| GSI delivery | 100ms | Configurable throttle in GSI config |
| Event detection | <10ms | In-memory state diff |
| **Tier 1: Pre-cached clip** | **<200ms total** | Instant reaction, covers the gap |
| LLM generation (streaming) | 500-1500ms TTFT | Stream tokens as they arrive |
| TTS (streaming) | 40ms TTFB | Cartesia `sonic-turbo` (or sub-100ms with `sonic-3`), starts on first LLM tokens |
| Audio mixing | <20ms | Real-time buffer mixing |
| **Tier 2: Full commentary** | **~2-3s total** | Plays after instant reaction |

---

## 3. Component Specifications

### 3.1 GSI Server

**What**: HTTP server that receives CS2 Game State Integration POST requests.

**GSI Config File**: `game/csgo/cfg/gamestate_integration_commentator.cfg`
```
"CS2_AI_Commentator"
{
    "uri"           "http://localhost:3001/gsi"
    "timeout"       "1.0"
    "buffer"        "0.0"
    "throttle"      "0.1"
    "heartbeat"     "5.0"
    "data"
    {
        "provider"            "1"
        "map"                 "1"
        "round"               "1"
        "player_id"           "1"
        "player_state"        "1"
        "player_weapons"      "1"
        "player_match_stats"  "1"
        "allplayers_id"       "1"
        "allplayers_state"    "1"
        "allplayers_match_stats" "1"
        "allplayers_weapons"  "1"    // Warning: significantly increases payload size; recommended for LAN only
        "allplayers_position" "1"
        "bomb"                "1"
        "phase_countdowns"    "1"
    }
}
```

**GSI Payload Structure** (what CS2 sends):
```typescript
interface GSIPayload {
  provider: { name: string; appid: number; timestamp: number };
  map: {
    name: string;           // "de_dust2", "de_mirage", etc.
    phase: "warmup" | "live" | "intermission" | "gameover";
    round: number;
    team_ct: { score: number; consecutive_round_losses: number; timeouts_remaining: number };
    team_t: { score: number; consecutive_round_losses: number; timeouts_remaining: number };
  };
  round: {
    phase: "freezetime" | "live" | "over";
    win_team?: "CT" | "T";
    bomb?: "planted" | "exploded" | "defused";
  };
  player: {                 // Current spectated player (or self if playing)
    steamid: string;
    name: string;
    team: "CT" | "T";
    activity: "playing" | "textinput" | "menu";
    state: {
      health: number;       // 0-100
      armor: number;        // 0-100
      helmet: boolean;
      flashed: number;      // 0-255
      smoked: number;       // 0-255
      burning: number;      // 0-255
      money: number;
      round_kills: number;
      round_killhs: number;
      round_totaldmg: number;
      equip_value: number;
    };
    weapons: Record<string, {
      name: string;         // "weapon_ak47", "weapon_awp", etc.
      paintkit: string;
      type: "Knife" | "Pistol" | "Rifle" | "SniperRifle" | "Submachine Gun" | "Shotgun" | "Machine Gun" | "Grenade" | "C4";
      state: "active" | "holstered";
      ammo_clip?: number;
      ammo_clip_max?: number;
      ammo_reserve?: number;
    }>;
    match_stats: {
      kills: number;
      assists: number;
      deaths: number;
      mvps: number;
      score: number;
    };
    position: string;       // "x, y, z" — SPECTATOR ONLY for allplayers
    forward: string;        // "x, y, z" — view direction
  };
  allplayers: Record<string, {  // SPECTATOR MODE ONLY — keyed by slot "0"-"9"
    steamid: string;
    name: string;
    team: "CT" | "T";
    state: { health: number; armor: number; helmet: boolean; money: number; round_kills: number; round_killhs: number; round_totaldmg: number; equip_value: number };
    weapons: Record<string, { name: string; type: string; state: string; ammo_clip?: number; ammo_reserve?: number }>;
    match_stats: { kills: number; assists: number; deaths: number; mvps: number; score: number };
    position: string;
    forward: string;
  }>;
  bomb?: {
    state: "carried" | "planted" | "dropped" | "defusing" | "defused" | "exploded";
    position: string;
    player?: string;        // steamid of carrier/defuser
    countdown?: string;     // seconds remaining (planted/defusing)
  };
  phase_countdowns?: {
    phase: string;
    phase_ends_in: string;  // seconds
  };
  previously?: Partial<GSIPayload>;  // Previous state for diffing
  added?: Partial<GSIPayload>;       // Newly added fields
}
```

**Server implementation**:
```typescript
// src/gsi-server.ts
import Fastify from "fastify";
import { EventEmitter } from "events";

const server = Fastify();
const gameEvents = new EventEmitter();

let previousState: GSIPayload | null = null;

server.post("/gsi", async (request, reply) => {
  const payload = request.body as GSIPayload;

  if (previousState) {
    const events = detectEvents(previousState, payload);
    for (const event of events) {
      gameEvents.emit("game-event", event);
    }
  }

  previousState = payload;
  return { status: "ok" };
});

server.listen({ port: 3001, host: "0.0.0.0" });
export { gameEvents };
```

### 3.2 Event Detector

**What**: Compares consecutive GSI payloads to detect meaningful game events. Built on top of the **cs2-gsi-z** library (MIT, 50+ built-in event types, delta-aware processing) with custom high-level detectors layered on top for multi-kill clustering, clutch detection, and economy analysis.

**Event Types & Detection Logic**:

```typescript
// src/events.ts

type EventPriority = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";

interface GameEvent {
  type: string;
  priority: EventPriority;
  timestamp: number;
  data: Record<string, any>;
  description: string;  // Human-readable for LLM context
}

// Detection rules:

// KILL — compare round_kills for each player between ticks
// If player.round_kills increased by 1+, a kill happened.
// Cross-reference: find which player's health dropped to 0 in same tick.
detectKill(prev, curr): GameEvent | null {
  for (const [slot, player] of Object.entries(curr.allplayers)) {
    const prevPlayer = prev.allplayers?.[slot];
    if (!prevPlayer) continue;

    const killDelta = player.state.round_kills - prevPlayer.state.round_kills;
    if (killDelta > 0) {
      // Find victim: who went from health>0 to health=0
      const victim = findNewDead(prev.allplayers, curr.allplayers);
      const weapon = Object.values(player.weapons).find(w => w.state === "active");
      const headshot = player.state.round_killhs > prevPlayer.state.round_killhs;

      return {
        type: "kill",
        priority: "HIGH",
        timestamp: Date.now(),
        data: {
          attacker: player.name,
          attackerTeam: player.team,
          attackerHealth: player.state.health,
          victim: victim?.name,
          victimTeam: victim?.team,
          weapon: weapon?.name,
          headshot,
          attackerRoundKills: player.state.round_kills,
        },
        description: `${player.name} killed ${victim?.name} with ${weapon?.name}${headshot ? " (headshot)" : ""}`
      };
    }
  }
}

// MULTI-KILL — track kills per player within 5-second windows
// 2 kills = "double kill", 3 = "triple", 4 = "quad", 5 = "ACE"
detectMultiKill(recentEvents: GameEvent[]): GameEvent | null {
  const killsByPlayer = new Map<string, GameEvent[]>();
  const fiveSecondsAgo = Date.now() - 5000;

  for (const event of recentEvents) {
    if (event.type === "kill" && event.timestamp > fiveSecondsAgo) {
      const attacker = event.data.attacker;
      if (!killsByPlayer.has(attacker)) killsByPlayer.set(attacker, []);
      killsByPlayer.get(attacker)!.push(event);
    }
  }

  for (const [player, kills] of killsByPlayer) {
    if (kills.length >= 3) {
      const labels = { 3: "triple kill", 4: "quad kill", 5: "ACE" };
      return {
        type: "multi_kill",
        priority: "CRITICAL",
        data: { player, killCount: kills.length, label: labels[kills.length] || `${kills.length}k` },
        description: `${player} gets a ${labels[kills.length] || kills.length + " kill"}!`
      };
    }
  }
}

// CLUTCH — detect 1vN situations
// When one team has exactly 1 player alive and the other has 2+
detectClutch(curr): GameEvent | null {
  const ctAlive = countAlive(curr.allplayers, "CT");
  const tAlive = countAlive(curr.allplayers, "T");

  if (ctAlive === 1 && tAlive >= 2) {
    const clutcher = findAlive(curr.allplayers, "CT");
    return { type: "clutch", priority: "CRITICAL", data: { player: clutcher.name, team: "CT", opponents: tAlive, health: clutcher.state.health } };
  }
  // Same for T side...
}

// BOMB — state change detection
detectBombEvent(prev, curr): GameEvent | null {
  if (prev.bomb?.state !== curr.bomb?.state) {
    return {
      type: `bomb_${curr.bomb.state}`,  // bomb_planted, bomb_defused, bomb_exploded
      priority: "HIGH",
      data: { state: curr.bomb.state, player: curr.bomb.player, countdown: curr.bomb.countdown }
    };
  }
}

// ROUND — phase changes
detectRoundEvent(prev, curr): GameEvent | null {
  if (prev.round?.phase !== curr.round?.phase) {
    if (curr.round.phase === "live") return { type: "round_start", priority: "MEDIUM", data: { round: curr.map.round, score: `${curr.map.team_ct.score}-${curr.map.team_t.score}` } };
    if (curr.round.phase === "over") return { type: "round_end", priority: "MEDIUM", data: { winner: curr.round.win_team, round: curr.map.round } };
  }
}

// ECONOMY — analyze at freezetime
detectEconomy(curr): GameEvent | null {
  if (curr.round?.phase !== "freezetime") return null;
  const ctMoney = sumTeamMoney(curr.allplayers, "CT");
  const tMoney = sumTeamMoney(curr.allplayers, "T");
  // eco < $10000 team total, force buy = $10000-$18000, full buy > $18000
  // Report if one team is on eco or force
}

// LOW HP PLAY — player alive with < 20 HP and gets a kill
detectLowHPPlay(event: GameEvent, curr): GameEvent | null {
  if (event.type === "kill" && event.data.attackerHealth <= 20) {
    return { type: "low_hp_kill", priority: "MEDIUM", data: { ...event.data, health: event.data.attackerHealth } };
  }
}
```

**Event Priority Queue**:
```typescript
// Events are queued by priority. Higher priority events interrupt lower ones.
// CRITICAL events (ace, clutch win) get both instant clip AND immediate LLM commentary.
// HIGH events (kills, bomb) get instant clip, LLM commentary queued.
// MEDIUM events (round start, economy) get LLM commentary only, no clip.
// LOW events are batched and used as context filler during quiet moments.
```

### 3.3 Commentary Engine (LLM)

**What**: Takes game events + context and generates natural commentary text.

**Model Selection**:

| Use Case | Model | Why |
|----------|-------|-----|
| Primary commentary | Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) | Best quality/speed, ~500-600ms TTFT, great persona adherence |
| Speed fallback | Groq Llama 4 Scout (`meta-llama/llama-4-scout-17b-16e-instruct`) | ~160ms TTFT, for when multiple events stack up |
| Analysis segments | Claude Sonnet 4.5 (`claude-sonnet-4-5-20250929`) | During freezetime, can do deeper analysis |
| Pre-game/halftime | GPT-5 mini | Structured stat summaries |

**System Prompt**:
```
You are an elite CS2 esports commentator. You provide live play-by-play and color commentary for Counter-Strike 2 matches.

## Voice & Style
- Energetic and knowledgeable, like Anders Blume or HenryG
- Short, punchy sentences for action moments (kills, clutches)
- Longer analysis during quiet moments (freezetime, eco rounds)
- Use CS2 terminology naturally: "traded out", "lurking", "rotate", "anti-eco", "force buy", "default setup", "double peek", "one-tap", "whiff"
- Build narrative: reference earlier events in the match ("after that rough pistol round...")
- Express genuine excitement for big plays, tension for clutch situations

## Output Rules
- ALWAYS respond with ONLY the commentary text. No labels, no prefixes, no metadata.
- Keep kill commentary to 1 sentence (5-15 words). The instant reaction clip handles the initial "bang".
- Keep clutch commentary to 2-3 sentences max.
- During freezetime: 2-3 sentences about economy/strategy.
- NEVER repeat the exact same phrase twice in a match. Vary your language.
- NEVER use generic filler. If nothing interesting is happening, output nothing (empty string).

## Emotion Tags (Cartesia SSML)
Wrap text in emotion tags that Cartesia TTS will interpret for prosody:
- Kills: <emotion value='excited'/>text
- Clutch: <emotion value='tense'/>text
- Ace: <emotion value='excited'/>text (+ caps/exclamation for extra intensity)
- Analysis: <emotion value='calm'/>text
- Disappointment: <emotion value='sad'/>text
Note: Also supports [laughter] tags for AI laughter.
```

**Context Window** (sent with each LLM request):
```typescript
interface CommentaryContext {
  // Current state
  map: string;
  roundNumber: number;
  score: { ct: number; t: number };
  phase: string;
  playersAlive: { ct: number; t: number };
  bombState: string | null;

  // Recent history (sliding window)
  recentEvents: GameEvent[];         // Last 30 seconds of events
  recentCommentary: string[];        // Last 5 commentary outputs (avoid repetition)

  // Match context
  roundHistory: RoundResult[];       // All rounds this match
  playerStats: PlayerMatchStats[];   // Running K/D/A for all players

  // Current event being commented on
  event: GameEvent;
}
```

**Commentary Deduplication & Phrase Bank**:

To prevent repetitive commentary over 30+ minute matches, implement two layers of dedup:

1. **Hash-based dedup**: Maintain a rolling window of the last 10 commentary outputs. Before sending new commentary to TTS, compute a normalized similarity score against each. Reject any output with >80% overlap (e.g., Jaccard similarity on word trigrams).

2. **Phrase bank rotation**: Maintain 10-15 template phrases per event type. The LLM should be guided toward variety via the system prompt, but the phrase bank acts as a fallback — if the LLM produces near-duplicate output, substitute a phrase bank entry that hasn't been used recently.

```typescript
// src/commentary/dedup.ts
class CommentaryDedup {
  private recentHashes: string[] = [];  // Rolling window of last 10
  private usedPhrases: Map<string, Set<number>> = new Map();  // event type → used phrase indices

  isDuplicate(text: string): boolean {
    const normalized = text.toLowerCase().replace(/[^a-z0-9\s]/g, "");
    const trigrams = this.getTrigrams(normalized);
    for (const prev of this.recentHashes) {
      if (this.jaccardSimilarity(trigrams, this.getTrigrams(prev)) > 0.8) return true;
    }
    this.recentHashes.push(normalized);
    if (this.recentHashes.length > 10) this.recentHashes.shift();
    return false;
  }

  getFallbackPhrase(eventType: string): string {
    // Returns least-recently-used phrase from the phrase bank for this event type
    const used = this.usedPhrases.get(eventType) ?? new Set();
    const bank = PHRASE_BANKS[eventType];
    const unusedIdx = bank.findIndex((_, i) => !used.has(i));
    const idx = unusedIdx >= 0 ? unusedIdx : 0;  // Reset if all used
    if (unusedIdx < 0) used.clear();
    used.add(idx);
    this.usedPhrases.set(eventType, used);
    return bank[idx];
  }

  private getTrigrams(text: string): Set<string> { /* ... */ }
  private jaccardSimilarity(a: Set<string>, b: Set<string>): number { /* ... */ }
}
```

**Groq Fallback** (mandatory, not optional):

When Claude returns 429 (rate limited) or response time exceeds 3s, automatically fall back to Groq Llama 4 Scout (~160ms TTFT). This fallback must be implemented from Phase 2 onwards — do not treat it as a future enhancement.

```typescript
// src/commentary/fallback.ts
import Groq from "groq-sdk";

const groq = new Groq();

async function* generateCommentaryFallback(context: CommentaryContext): AsyncGenerator<string> {
  const stream = await groq.chat.completions.create({
    model: "meta-llama/llama-4-scout-17b-16e-instruct",
    messages: [
      { role: "system", content: COMMENTATOR_SYSTEM_PROMPT },
      { role: "user", content: `Current match state:\n${JSON.stringify(context, null, 2)}\n\nProvide live commentary for: ${context.event.description}` }
    ],
    stream: true,
    max_tokens: 100,
  });
  for await (const chunk of stream) {
    const text = chunk.choices[0]?.delta?.content;
    if (text) yield text;
  }
}
```

**LLM Call** (streaming):
```typescript
// src/commentary.ts
import Anthropic from "@anthropic-ai/sdk";

const anthropic = new Anthropic();

async function* generateCommentary(context: CommentaryContext): AsyncGenerator<string> {
  const stream = anthropic.messages.stream({
    model: "claude-haiku-4-5-20251001",
    max_tokens: 100,  // Short outputs for speed
    system: COMMENTATOR_SYSTEM_PROMPT,
    messages: [{
      role: "user",
      content: `Current match state:\n${JSON.stringify(context, null, 2)}\n\nProvide live commentary for: ${context.event.description}`
    }]
  });

  for await (const chunk of stream) {
    if (chunk.type === "content_block_delta" && chunk.delta.type === "text_delta") {
      yield chunk.delta.text;
    }
  }
}
```

### 3.4 TTS Engine (Cartesia Sonic 3)

**What**: Converts commentary text to speech in real-time via WebSocket streaming.

**Why Cartesia**:
- 40ms TTFB with `sonic-turbo` / sub-100ms with `sonic-3` (fastest available)
- 60+ emotion controls via SSML tags
- Instant Voice Cloning from 3-5 seconds of audio (Pro clone: 30+ min for higher fidelity)
- SSM architecture (state space model, not transformer) — linear scaling, purpose-built for streaming
- WebSocket native with 5-minute idle timeout (must implement reconnection/keepalive for long matches)
- $0.03/min (~3-8x cheaper than ElevenLabs)

**API Setup**:
```bash
# Get API key from https://play.cartesia.ai/
# Cartesia WebSocket endpoint: wss://api.cartesia.ai/tts/websocket
```

**Voice Cloning** (one-time setup):
```typescript
// Clone a caster's voice from a clean audio clip
// Use the Cartesia dashboard or API:
const response = await fetch("https://api.cartesia.ai/voices/clone", {
  method: "POST",
  headers: {
    "Authorization": `Bearer ${CARTESIA_API_KEY}`,
    "Cartesia-Version": "2025-04-16",
    "Content-Type": "multipart/form-data"
  },
  body: formData  // FormData with: clip (audio file), name, description, language
  // Instant Clone: 3-5 seconds of clean caster audio recommended
  // Note: As of API v2025-04-16, only similarity clones are supported (stability mode removed)
});
const { id: voiceId } = await response.json();
// Save voiceId for all future TTS calls
```

**Streaming TTS**:
```typescript
// src/tts.ts
import WebSocket from "ws";

class CartesiaTTS {
  private ws: WebSocket;
  private voiceId: string;

  constructor(apiKey: string, voiceId: string) {
    this.voiceId = voiceId;
    this.ws = new WebSocket(
      `wss://api.cartesia.ai/tts/websocket?api_key=${apiKey}&cartesia_version=2025-04-16`
    );
  }

  // Stream text → get audio chunks back
  async *speak(text: string, contextId: string): AsyncGenerator<Buffer> {
    const request = {
      model_id: "sonic-3",  // or use "sonic-turbo" for lowest latency
      transcript: text,
      voice: {
        mode: "id",
        id: this.voiceId
      },
      output_format: {
        container: "raw",
        encoding: "pcm_f32le",
        sample_rate: 44100
      },
      context_id: contextId,  // Maintains voice consistency across chunks
      continue: false
    };

    this.ws.send(JSON.stringify(request));

    // Receive audio chunks as they're generated
    for await (const message of this.listen()) {
      const data = JSON.parse(message.toString());
      if (data.type === "chunk") {
        yield Buffer.from(data.data, "base64");
      }
      if (data.type === "done") break;
    }
  }

  // Input streaming: send LLM tokens as they arrive
  async streamFromLLM(llmStream: AsyncGenerator<string>, contextId: string): AsyncGenerator<Buffer> {
    // Cartesia supports input streaming — send partial text, get partial audio
    // Model buffers text until optimal length; max_buffer_delay_ms controls max wait (default 3000ms)
    for await (const token of llmStream) {
      this.ws.send(JSON.stringify({
        model_id: "sonic-3",
        transcript: token,
        voice: { mode: "id", id: this.voiceId },
        output_format: { container: "raw", encoding: "pcm_f32le", sample_rate: 44100 },
        context_id: contextId,
        continue: true,  // More text coming
        max_buffer_delay_ms: 1000  // Lower than default 3000ms for live commentary responsiveness
      }));
    }
    // Signal end of input
    this.ws.send(JSON.stringify({
      model_id: "sonic-3",
      transcript: "",
      context_id: contextId,
      continue: false
    }));
  }
}
```

**WebSocket Reconnection & Keepalive**:

Cartesia WebSocket connections have a 5-minute idle timeout. For matches lasting 30-60 minutes, implement:

```typescript
// src/tts/cartesia.ts — add to CartesiaTTS class

private keepaliveInterval: NodeJS.Timeout | null = null;
private reconnectAttempts = 0;
private readonly MAX_RECONNECT_ATTEMPTS = 3;
private readonly RECONNECT_DELAYS = [1000, 2000, 4000]; // Exponential backoff

startKeepalive() {
  // Ping every 4 minutes (before 5-min idle timeout)
  this.keepaliveInterval = setInterval(() => {
    if (this.ws.readyState === WebSocket.OPEN) {
      this.ws.ping();
    }
  }, 4 * 60 * 1000);
}

async reconnect(): Promise<void> {
  if (this.reconnectAttempts >= this.MAX_RECONNECT_ATTEMPTS) {
    throw new Error("Cartesia WebSocket reconnection failed after 3 attempts");
  }
  const delay = this.RECONNECT_DELAYS[this.reconnectAttempts];
  this.reconnectAttempts++;
  await new Promise(r => setTimeout(r, delay));
  this.ws = new WebSocket(
    `wss://api.cartesia.ai/tts/websocket?api_key=${this.apiKey}&cartesia_version=2025-04-16`
  );
  await new Promise<void>((resolve, reject) => {
    this.ws.once("open", () => { this.reconnectAttempts = 0; resolve(); });
    this.ws.once("error", reject);
  });
  this.startKeepalive();
}

// IMPORTANT: Serial TTS only — 1 active stream per WebSocket connection.
// Do NOT multiplex multiple speak() calls on the same connection.
```

**Alternative: Hume Octave 2** (if you prefer auto-emotion):
```typescript
// Hume doesn't need SSML emotion tags — it understands text semantics
// Just send "AND HE GETS THE ACE!!!" and it delivers with excitement automatically
// API: https://dev.hume.ai/docs/text-to-speech-tts/overview
// WebSocket: wss://api.hume.ai/v0/tts/stream/input?version=2
// Voice cloning: 15 seconds of audio
// Cost: ~$0.01/min at scale
```

### 3.5 Pre-cached Instant Reactions

**What**: ~50-100 pre-generated TTS clips for instant event reactions.

**Why**: LLM + TTS takes 2-3s. Instant clips play in <200ms while the full commentary generates.

**Clip Categories**:
```typescript
const INSTANT_CLIPS = {
  kill: [
    "And he's down!",
    "Beautiful shot!",
    "What a pick!",
    "Gets the frag!",
    "Taken down!",
    "Clean kill!",
    "And that's another one!",
  ],
  headshot: [
    "One tap!",
    "Right on the head!",
    "HEADSHOT!",
    "What precision!",
  ],
  multi_kill: [
    "He's on fire!",
    "They can't stop him!",
    "WHAT IS HAPPENING!",
  ],
  ace: [
    "THE ACE! THE ACE!",
    "ALL FIVE! HE GETS ALL FIVE!",
    "ABSOLUTELY INSANE!",
  ],
  clutch_start: [
    "It's all on him now...",
    "Can he do it?",
    "This is the clutch situation...",
  ],
  clutch_win: [
    "HE DOES IT!",
    "THE CLUTCH! UNBELIEVABLE!",
    "WHAT A PLAYER!",
  ],
  bomb_planted: [
    "Bomb is down!",
    "The bomb has been planted!",
    "They've got the plant!",
  ],
  bomb_defused: [
    "Defused! Just in time!",
    "He gets the defuse!",
    "AND IT'S DEFUSED!",
  ],
  round_start: [
    "Here we go!",
    "Next round...",
    "And we're live!",
  ],
  whiff: [
    "Oh no...",
    "That's unfortunate.",
    "He had him!",
  ],
  save: [
    "Saving the AWP...",
    "Smart save.",
    "Living to fight another round.",
  ],
};
```

**Pre-generation script** (run once):
```typescript
// scripts/generate-clips.ts
// For each clip text, call Cartesia TTS and save as .wav
// Use the cloned voice ID
// Store in assets/clips/{category}/{index}.wav
// At runtime, randomly select from category and play immediately
```

### 3.6 Audio Mixer

**What**: Combines commentary audio, instant clips, and crowd sounds into a single output stream.

**Crowd Sound Design**:
```
assets/crowd/
  ambient.wav          — Low murmur, loops continuously
  cheer-small.wav      — Polite clap, for kills
  cheer-big.wav        — Loud cheer, for multi-kills
  roar.wav             — Stadium roar, for aces/clutch wins
  gasp.wav             — For near-misses, bomb plant
  groan.wav            — For whiffs, failed clutches
  tension-rise.wav     — Building tension loop, for clutch situations
  explosion.wav        — Bass hit for bomb explode
```

**Mixing Logic**:
```typescript
// src/audio-mixer.ts

class AudioMixer {
  private ambientGain: GainNode;      // Always playing, low volume
  private commentaryGain: GainNode;    // TTS output
  private crowdGain: GainNode;         // Reactive crowd sounds

  // On event:
  onEvent(event: GameEvent) {
    switch (event.type) {
      case "kill":
        this.playCrowd("cheer-small", 0.4);
        this.duckAmbient(0.2, 2000);    // Lower ambient during commentary
        break;
      case "multi_kill":
      case "ace":
        this.playCrowd("roar", 0.9);
        this.duckAmbient(0.1, 4000);
        break;
      case "clutch":
        this.playCrowd("tension-rise", 0.5);  // Loop until clutch resolves
        break;
      case "clutch_win":
        this.stopCrowd("tension-rise");
        this.playCrowd("roar", 1.0);
        break;
      case "bomb_planted":
        this.playCrowd("gasp", 0.5);
        break;
      case "bomb_exploded":
        this.playCrowd("explosion", 0.7);
        break;
    }
  }

  // Duck ambient volume during commentary, restore after
  duckAmbient(targetVolume: number, durationMs: number) {
    this.ambientGain.gain.linearRampToValueAtTime(targetVolume, currentTime + 0.1);
    setTimeout(() => {
      this.ambientGain.gain.linearRampToValueAtTime(0.3, currentTime + 0.5);
    }, durationMs);
  }
}
```

### 3.7 Crowd Behavior Engine

**What**: Simulates a live stadium crowd that reacts to game events in real time. Runs in the browser via Web Audio API.

**Arousal Model**:
```typescript
// src/audio/crowd-behavior.ts (browser-side)

class CrowdBehavior {
  private arousal = 0;        // 0 (calm) to 1 (hyped)
  private readonly DECAY_RATE = 0.02;  // Per second, crowd calms down naturally
  private readonly DECAY_INTERVAL = 100; // ms

  // Arousal modifiers by event type
  private readonly AROUSAL_MAP: Record<string, number> = {
    kill: 0.1,
    headshot_kill: 0.15,
    multi_kill: 0.3,
    ace: 0.8,
    clutch: 0.25,       // Builds tension
    clutch_win: 0.6,    // Releases tension as hype
    clutch_fail: -0.1,  // Groan
    bomb_planted: 0.15,
    bomb_defused: 0.3,
    bomb_exploded: 0.2,
    round_start: 0.05,
  };

  constructor() {
    // Continuous decay — crowd naturally calms between events
    setInterval(() => {
      this.arousal = Math.max(0, this.arousal - this.DECAY_RATE * (this.DECAY_INTERVAL / 1000));
      this.updateAmbient();
    }, this.DECAY_INTERVAL);
  }

  onEvent(event: { type: string; data: any }) {
    const delta = this.AROUSAL_MAP[event.type] ?? 0;
    this.arousal = Math.min(1, Math.max(0, this.arousal + delta));

    // Trigger discrete crowd behaviors based on arousal level
    if (this.arousal > 0.7) this.startRhythmicClapping();
    if (this.arousal > 0.9) this.triggerStadiumRoar();
    if (this.arousal < 0.2) this.stopRhythmicClapping();
  }

  // --- Rhythmic Clapping ---
  // BPM scales with arousal: 60 BPM (calm) → 200 BPM (hyped)
  // 8-beat pattern, tempo increases as arousal rises
  private clappingInterval: number | null = null;

  startRhythmicClapping() {
    if (this.clappingInterval) return;  // Already clapping
    const updateClapping = () => {
      const bpm = 60 + (this.arousal * 140);  // 60-200 BPM
      const interval = 60000 / bpm;
      this.playClap(0.3 + this.arousal * 0.4);  // Volume scales with arousal
      this.clappingInterval = window.setTimeout(updateClapping, interval);
    };
    updateClapping();
  }

  stopRhythmicClapping() {
    if (this.clappingInterval) {
      clearTimeout(this.clappingInterval);
      this.clappingInterval = null;
    }
  }

  // --- Ambient Evolution ---
  // Layer multiple ambient tracks, modulate gain by arousal
  updateAmbient() {
    // Low murmur: always present, louder when calm
    this.ambientLowGain.gain.value = 0.3 * (1 - this.arousal * 0.5);
    // Excited chatter: fades in as arousal rises
    this.ambientHighGain.gain.value = this.arousal * 0.4;
  }

  // --- Proximity-Based Anticipation ---
  // When enemy players are within range, crowd builds tension
  onProximityUpdate(minEnemyDistance: number) {
    if (minEnemyDistance < 800) {  // Units: game units, ~800 = close engagement range
      const intensity = 1 - (minEnemyDistance / 800);
      this.playAnticipationSwell(intensity * 0.3);
    }
  }

  private playClap(volume: number) { /* Web Audio: play clap sample at volume */ }
  private triggerStadiumRoar() { /* Web Audio: play roar.wav at full volume */ }
  private playAnticipationSwell(volume: number) { /* Web Audio: fade in tension-rise.wav */ }
}
```

**Proximity Detection** (server-side, sent to browser via WebSocket):
```typescript
// src/events/proximity.ts
function calculateMinEnemyDistance(allplayers: GSIPayload["allplayers"]): number | null {
  const positions = new Map<string, { x: number; y: number; z: number; team: string }>();
  for (const [, player] of Object.entries(allplayers)) {
    if (player.state.health <= 0) continue;
    const [x, y, z] = player.position.split(", ").map(Number);
    positions.set(player.name, { x, y, z, team: player.team });
  }
  let minDist = Infinity;
  for (const [, a] of positions) {
    for (const [, b] of positions) {
      if (a.team === b.team) continue;
      const dist = Math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2);
      minDist = Math.min(minDist, dist);
    }
  }
  return minDist === Infinity ? null : minDist;
}
```

### 3.8 Output Options

| Output | How | Use Case |
|--------|-----|----------|
| **Local speaker** | sox/ffplay via child_process or Web Audio API | Personal listening while watching |
| **OBS Virtual Audio** | Virtual audio cable (VB-Cable/BlackHole) | Stream with AI commentary overlay |
| **Web UI** | Browser app with Web Audio API | Dashboard showing game state + audio |
| **Discord** | Discord.js voice connection | Share commentary in Discord voice channel |

---

## 4. Project Structure

```
cs2-commentator/
├── package.json
├── tsconfig.json
├── .env                          # API keys
├── src/
│   ├── index.ts                  # Entry point, wires everything together
│   ├── gsi-server.ts             # Fastify server receiving CS2 GSI POST
│   ├── state/
│   │   └── manager.ts            # Centralized StateManager (single source of truth)
│   ├── events/
│   │   ├── detector.ts           # High-level detectors on top of cs2-gsi-z
│   │   ├── proximity.ts          # Player proximity detection from GSI positions
│   │   ├── types.ts              # GameEvent, EventPriority types
│   │   └── queue.ts              # Priority event queue with ConcurrencyLimiter
│   ├── commentary/
│   │   ├── engine.ts             # LLM commentary generation (streaming)
│   │   ├── fallback.ts           # Groq Llama 4 Scout fallback (mandatory)
│   │   ├── dedup.ts              # Hash-based dedup + phrase bank rotation
│   │   ├── prompts.ts            # System prompts, persona definition
│   │   └── context.ts            # Sliding window context builder
│   ├── tts/
│   │   ├── cartesia.ts           # Cartesia Sonic 3 WebSocket client (with keepalive + reconnect)
│   │   ├── clips.ts              # Pre-cached clip manager
│   │   └── voice-clone.ts        # One-time voice cloning utility
│   ├── audio/
│   │   ├── mixer.ts              # Browser-side: real-time Web Audio API mixing
│   │   ├── crowd-behavior.ts     # Browser-side: arousal model, rhythmic clapping, proximity
│   │   └── output.ts             # Speaker/OBS/Web output routing
│   └── web/                      # Browser audio dashboard
│       ├── index.html
│       └── dashboard.ts
├── assets/
│   ├── clips/                    # Pre-generated instant reaction .wav files
│   │   ├── kill/
│   │   ├── headshot/
│   │   ├── ace/
│   │   ├── clutch/
│   │   ├── bomb/
│   │   └── ...
│   └── crowd/                    # Crowd sound effects
│       ├── ambient.wav
│       ├── cheer-small.wav
│       ├── cheer-big.wav
│       ├── roar.wav
│       ├── gasp.wav
│       ├── groan.wav
│       └── tension-rise.wav
├── config/
│   └── gamestate_integration_commentator.cfg  # Copy to CS2 cfg folder
└── scripts/
    ├── generate-clips.ts         # Pre-generate TTS clips
    └── test-gsi.ts               # Send fake GSI payloads for testing
```

---

## 5. Dependencies

```json
{
  "dependencies": {
    "fastify": "^5.x",              // GSI HTTP server
    "@anthropic-ai/sdk": "^0.74.x", // Claude API (commentary LLM) — not at 1.x yet
    "groq-sdk": "^0.x",             // Groq API (mandatory LLM fallback)
    "cs2-gsi-z": "latest",          // CS2 GSI library — 50+ event types, delta-aware state diffing
    "ws": "^8.x",                   // WebSocket for Cartesia TTS + browser streaming
    "pcm-convert": "^1.x",          // PCM audio format conversion
    "dotenv": "^16.x"               // Environment variables
    // Audio output: use sox (play command) or ffplay via child_process.spawn for server-side
    // The `speaker` npm package (^0.5.x) is unmaintained (2+ years). Avoid it.
    // Primary audio output: Web Audio API in browser (hybrid architecture)
  },
  "devDependencies": {
    "typescript": "^5.x",
    "tsx": "^4.x",                   // TS execution (or use Node.js v22+ native TS support)
    "vitest": "^3.x",               // Test framework
    "@types/ws": "^8.x"
  }
}
```

**Environment Variables** (`.env`):
```
ANTHROPIC_API_KEY=sk-ant-...
CARTESIA_API_KEY=...
CARTESIA_VOICE_ID=...           # After cloning
GROQ_API_KEY=...                # Optional, for speed fallback
```

---

## 6. Build Phases (Detailed)

### Phase 1: GSI + Event Detection (Days 1-3)

**Goal**: CS2 sends data → you see events in terminal.

1. `mkdir cs2-commentator && cd cs2-commentator && npm init -y`
2. Install deps: `npm i fastify ws @anthropic-ai/sdk groq-sdk cs2-gsi-z dotenv typescript tsx`
3. Install dev deps: `npm i -D vitest @types/ws`
4. Create `src/gsi-server.ts` — Fastify POST endpoint on `:3001/gsi`
5. Integrate cs2-gsi-z — use its built-in state diffing and event types as foundation
6. Create `src/events/detector.ts` — Custom high-level detectors on top of cs2-gsi-z (multi-kill clustering, clutch detection, economy analysis)
7. Create `src/events/queue.ts` — Priority queue with ConcurrencyLimiter (max 3 LLM req/sec, priority-based dropping)
8. Create `src/state/manager.ts` — Centralized StateManager (single source of truth, EventEmitter-based)
9. Create `config/gamestate_integration_commentator.cfg`
10. Copy config to CS2 (Windows/Linux only — CS2 has no native macOS support):
    - Linux: `cp config/gamestate_integration_commentator.cfg ~/.steam/steamapps/common/Counter-Strike Global Offensive/game/csgo/cfg/`
    - Windows: copy to `C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\game\csgo\cfg\`
    - Note: The commentator server itself can run on any OS; only CS2 + GSI requires Windows/Linux
11. Create `scripts/test-gsi.ts` — Mock GSI replayer for testing without CS2
12. Write unit tests with vitest for event detection and state management
13. Run server: `npx tsx src/index.ts`
14. Test with mock replayer OR launch CS2 → join a deathmatch → watch events appear in terminal

**Verification**: Every kill, round start/end, bomb event, and multi-kill/clutch should print to console. Mock replayer reproduces all scenarios.

### Phase 2: LLM Commentary (Days 4-5)

**Goal**: Events generate spoken commentary with fallback.

1. Create `src/commentary/engine.ts` — Claude Haiku 4.5 streaming client
2. Create `src/commentary/fallback.ts` — Groq Llama 4 Scout fallback (mandatory)
3. Create `src/commentary/prompts.ts` — Commentator persona prompt
4. Create `src/commentary/context.ts` — Sliding window of recent events + commentary
5. Create `src/commentary/dedup.ts` — Hash-based deduplication + phrase bank rotation
6. Wire: event → ConcurrencyLimiter → commentary engine (with fallback) → dedup check → console output
7. Test: play a match (or use mock replayer), verify commentary text appears for each event
8. Tune prompt: adjust verbosity, style, terminology

**Verification**: Commentary text should be varied, contextual, and use proper CS2 terminology. Groq fallback triggers correctly on simulated Claude failure. No duplicate phrases in 10-event window.

### Phase 3: TTS + Audio (Days 6-7)

**Goal**: Commentary is spoken aloud with proper WebSocket lifecycle.

1. Sign up for Cartesia (https://play.cartesia.ai/)
2. Clone a voice (upload 3-5s of clean caster audio for Instant Clone)
3. Create `src/tts/cartesia.ts` — WebSocket streaming client with keepalive (ping every 4 min) and reconnection (3 attempts, exponential backoff)
4. Wire: LLM streaming tokens → Cartesia WebSocket → audio buffer → speaker (sox/ffplay initially)
5. Test: play a match, hear commentary through speakers
6. Verify WebSocket stays alive for 10+ minutes without dropping

**Verification**: Audio should play within 3-4 seconds of each game event. WebSocket reconnects automatically if dropped. Voice should match cloned caster.

### Phase 4: Two-Tier + Crowd (Days 8-9)

**Goal**: Instant reactions + contextual commentary + crowd atmosphere with browser-based audio mixing.

1. Create `scripts/generate-clips.ts` — generate all instant reaction clips via Cartesia API
2. Run: `npx tsx scripts/generate-clips.ts` → fills `assets/clips/`
3. Download/create crowd sound effects → `assets/crowd/`
4. Create `src/tts/clips.ts` — clip selector (random per category)
5. Create `src/web/` — Browser-based audio mixing dashboard (Web Audio API)
6. Create `src/audio/mixer.ts` — Browser-side real-time audio mixing (commentary + clips + crowd + ambient)
7. Create `src/audio/crowd-behavior.ts` — Browser-side crowd behavior engine (arousal model, rhythmic clapping, proximity anticipation)
8. Server → Browser WebSocket: stream TTS audio chunks + event metadata + proximity data
9. Wire: event → (instant clip plays immediately in browser) + (LLM → TTS → streams to browser → plays after clip)
10. Add ambient crowd loop with arousal-based volume modulation

**Verification**: Kill happens → instant "Beautiful shot!" plays in <200ms → 2 seconds later contextual commentary plays → crowd cheers in background. Crowd builds rhythmic clapping during intense moments. Proximity-based tension swells when enemies approach.

### Phase 5: Polish (Days 10+)

- Web dashboard showing live game state, event log, commentary log
- OBS integration (virtual audio device)
- Player knowledge base (team names, player histories, playstyles)
- Economy tracking with buy round predictions
- Multi-language support
- Adjustable commentary intensity/frequency slider
- Commentary style presets (hype caster, analytical caster, meme caster)

---

## 7. Testing Without a Live Match

**Fake GSI sender** for development:
```typescript
// scripts/test-gsi.ts
// Reads a recorded GSI session (or generates fake payloads)
// POSTs to localhost:3001/gsi at configurable speed
// Simulates: warmup → pistol round → kills → bomb plant → defuse → eco → force buy → clutch → overtime

import scenarios from "./test-scenarios.json";

async function replay(scenario: GSIPayload[], speedMultiplier = 1) {
  for (let i = 0; i < scenario.length; i++) {
    await fetch("http://localhost:3001/gsi", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(scenario[i])
    });
    await sleep(100 / speedMultiplier);  // 100ms between payloads (normal GSI rate)
  }
}
```

You can also record a real GSI session by logging all payloads to a JSON file, then replay them.

---

## 8. TTS Provider Comparison (No ElevenLabs)

| | Cartesia Sonic 3 | Hume Octave 2 | Inworld 1.5-Max | Fish Audio S1 |
|---|---|---|---|---|
| **TTFB** | **40ms (sonic-turbo)** / sub-100ms (sonic-3) | ~100ms | ~200ms | <150ms (local) |
| **Quality ELO** | 1,054 | 1,046 | **1,160** | 1,074 |
| **Voice Clone** | 3-5s audio (Instant) | 15s audio | Zero-shot | 10-30s audio |
| **Emotion** | 60+ SSML controls | Auto (LLM-driven) | Good | Explicit markers |
| **Cost/min** | $0.03 | ~$0.01 | **$0.01** | Free (self-host) |
| **Streaming** | WebSocket native | Full stream | Full stream | WebSocket |
| **Best for** | Explicit control | Set-and-forget | Budget quality | Self-hosted |

**Recommendation**: Start with **Cartesia Sonic 3** for explicit emotion control. If you find manual emotion tagging tedious, switch to **Hume Octave 2** which auto-detects emotion from text.

---

## 9. Cost Estimates

> **Note**: TTS dominates cost. LLM costs are lower than initially estimated. Budget $3-5 per match (~$3.50-5.80/hr).

### Per Hour of Live Commentary

| Component | Provider | Cost/hour | Notes |
|-----------|----------|-----------|-------|
| LLM (primary) | Claude Haiku 4.5 | ~$0.40-0.90 | Depends on commentary frequency |
| LLM (analysis) | Claude Sonnet 4.5 | ~$0.50 (freezetime only) | Only during round breaks |
| TTS | Cartesia Sonic 3 | ~$1.80-3.50 | Dominates total cost |
| **Total** | | **~$3.50-5.80/hr** | **~$3-5 per match** |

### Alternative Setups

| Setup | Cost/hour | Cost/match |
|-------|-----------|------------|
| Haiku 4.5 + Cartesia | ~$3.50 | ~$3-4 |
| Haiku 4.5 + Hume | ~$1.00-1.50 | ~$1-1.50 |
| Haiku 4.5 + Inworld | ~$1.00-1.50 | ~$1-1.50 |
| Groq (free) + Fish Audio (self-hosted) | ~$0 | ~$0 |

---

## 10. Future Ideas

- **Dual caster mode**: Two LLM agents — one play-by-play, one analyst — that "talk" to each other
- **HLTV integration**: Pull real player/team stats, recent match history for informed commentary
- **Demo file parsing**: Post-match highlight reel with AI commentary (non-realtime, higher quality)
- **Twitch extension**: Overlay showing AI predictions + commentary text
- **Fantasy mode**: Fictional caster persona (medieval herald, nature documentary, drill sergeant)
- **Training mode**: Coach commentary — points out mistakes, suggests improvements
- **Multi-language**: Switch language mid-match based on player nationalities
