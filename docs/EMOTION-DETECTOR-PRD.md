# Emotion Detector PRD — Step 1 MVP

> **PUBLIC REPOSITORY** — No API keys, secrets, or credentials in any file.

> Created: 2026-02-13
> Status: Implemented — `python/` directory

---

## Overview

Real-time webcam emotion detection as Step 1 of a 3-step roadmap toward a "work mode" AI live commentator that observes and comments on a user's work experience.

### Roadmap

| Step | What | Status |
|------|------|--------|
| **1 (this)** | Webcam → face detection → emotion recognition → live annotated preview | MVP built |
| 2 | Add screen capture to see what user is doing on their computer | Planned |
| 3 | Feed emotions + screen context into LLM for spoken "work mode" commentary | Planned |

---

## Architecture

Three-thread producer-consumer pipeline:

```
Capture Thread (daemon)  →  Queue(2)  →  Detector Thread (daemon)  →  Queue(2)  →  Display (main thread)
cv2.VideoCapture(0)          drop-old     DeepFace.analyze()           drop-old     cv2.imshow + overlays
640x480 @ 30 FPS                          ~30-50ms per frame                        bounding box, labels, bars
```

- **Capture → Detector**: Small queue (maxsize=2), drops oldest frame when full. Detector always gets latest.
- **Detector → Display**: Same pattern. Display always renders the most recent result.
- **Display on main thread**: Required by macOS for cv2.imshow.
- **Emotion smoothing**: Rolling average over 5 frames prevents label flickering.
- **Event debouncing**: Emotion change events emitted max 1/sec via callback system.

---

## Components

| File | Purpose |
|------|---------|
| `python/main.py` | Entry point — `python main.py [--camera N]` |
| `python/emotion_detector/config.py` | All constants (resolution, FPS, thresholds, colors) |
| `python/emotion_detector/capture.py` | `WebcamCapture` — threaded webcam reader |
| `python/emotion_detector/detector.py` | `EmotionDetector` — DeepFace wrapper in processing thread |
| `python/emotion_detector/display.py` | `AnnotatedDisplay` — renders overlays on main thread |
| `python/emotion_detector/pipeline.py` | `EmotionPipeline` — orchestrator wiring all components |
| `python/emotion_detector/events.py` | `EmotionEvent` dataclass + `EventEmitter` callbacks |
| `python/emotion_detector/smoothing.py` | `EmotionSmoother` — rolling avg + debounced emission |

---

## Emotion Detection

Uses **DeepFace** library with OpenCV backend:

```python
DeepFace.analyze(frame, actions=("emotion",), enforce_detection=False, detector_backend="opencv", silent=True)
```

**7 detected emotions**: angry, disgust, fear, happy, sad, surprise, neutral

**Performance**: ~30-50ms per frame on Apple Silicon CPU = 20-30 FPS processing.

**First run**: Automatically downloads emotion model (~100MB) to `~/.deepface/weights/`.

---

## Event Output

Emotion changes emit as JSON to stdout:

```json
{
  "timestamp": 1707936000.123,
  "dominant_emotion": "happy",
  "confidence": 0.87,
  "all_scores": {"angry":0.01,"disgust":0.00,"fear":0.02,"happy":0.87,"sad":0.03,"surprise":0.04,"neutral":0.03},
  "face_region": [120, 45, 200, 200]
}
```

The `EventEmitter` supports registering additional callbacks for future WebSocket integration.

---

## Dependencies

```
opencv-python>=4.9.0,<5.0.0
deepface>=0.0.93,<1.0.0
tf-keras>=2.16.0
numpy>=1.24.0,<2.0.0
```

100% local processing. No cloud APIs. No data retention.

---

## Privacy

- All processing is on-device (DeepFace runs locally)
- No frames leave the machine
- No emotion history is stored to disk
- Camera can be stopped at any time ('q' key or Ctrl+C)
- Future: user consent modal before camera activation

---

## Future Integration (Steps 2-3)

### Step 2: Screen Capture
- Add `mss` library for screen capture
- Combine emotion + screen context
- Run both webcam + screen capture in parallel threads

### Step 3: Node.js Bridge
- WebSocket connection from Python to Node.js Fastify server
- Send emotion events as JSON over `ws://localhost:3001/emotion`
- Node.js LLM prompt: "User is {emotion} while working on {screen_context}"
- Reuse existing Cartesia TTS + Web Audio mixer for spoken commentary

---

## Committee Research (2026-02-13)

5 research agents evaluated approaches. Unanimous decisions:

- **OpenCV** for webcam capture (industry standard, threaded, 30 FPS)
- **DeepFace** for emotion recognition (75-94% accuracy, pip install, fastest setup)
- **Threading** over asyncio (OpenCV/TF release GIL during C ops)
- **cv2.imshow** for MVP display (simplest, browser dashboard in Step 3)
- **WebSocket** for future Node.js bridge (matches existing Cartesia pattern)
- **Local processing only** (privacy-first, no cloud API costs)

Key rejected alternatives:
- YOLOv8 (no facial landmarks, heavier dependency)
- Hume AI API ($2.70/hr too expensive for continuous use)
- asyncio pipeline (doesn't help with compute-bound ML inference)
- Pipecat/LiveKit (wrong abstraction for this use case)
