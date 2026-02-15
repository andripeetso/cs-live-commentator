"""Configuration constants for the emotion detector pipeline."""

# Webcam capture
CAMERA_INDEX = 0
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
TARGET_FPS = 30

# Queue sizes (small = drop stale frames, always process latest)
CAPTURE_QUEUE_SIZE = 2
RESULT_QUEUE_SIZE = 2

# DeepFace settings
DETECTOR_BACKEND = "opencv"  # fastest; switch to "mediapipe" for better accuracy
ENFORCE_DETECTION = False     # don't crash when no face visible
ACTIONS = ("emotion",)        # only emotion — skip age/gender/race

# Emotion smoothing
SMOOTHING_WINDOW = 5          # rolling average over N frames
DEBOUNCE_SECONDS = 1.0        # min interval between emitted events
CONFIDENCE_THRESHOLD = 0.15   # min delta to trigger a new event

# Interleaved detection
DEEPFACE_EVERY_N = 3          # run DeepFace every Nth frame (others: MediaPipe only)

# MediaPipe Pose (Tasks API — uses pose_landmarker_lite.task model)
POSE_MIN_DETECTION_CONFIDENCE = 0.5
POSE_MIN_TRACKING_CONFIDENCE = 0.5

# Action detection
ACTION_BUFFER_SIZE = 15       # temporal buffer for multi-frame actions
ACTION_SMOOTHING_WINDOW = 8   # rolling vote window
ACTION_DEBOUNCE_SECONDS = 0.5 # min interval between action events
ACTION_MIN_VOTE_RATIO = 0.3   # min fraction of window to report action

# MediaPipe Hand Landmarks (Tasks API — uses hand_landmarker.task model)
HAND_MIN_DETECTION_CONFIDENCE = 0.5
HAND_MIN_PRESENCE_CONFIDENCE = 0.5
HAND_MIN_TRACKING_CONFIDENCE = 0.5

# Vision LLM (GPT-5-mini vision for rich action understanding)
VISION_INTERVAL = 6.0               # seconds between vision API calls
VISION_MODEL = "gpt-5-mini"          # OpenAI model for vision analysis
VISION_ENABLED = True                # set False to disable vision LLM

# AI Commentator
COMMENTATOR_MODEL = "gpt-5-mini"      # OpenAI model for commentary
COMMENTATOR_INTERVAL = 4.0            # seconds between commentary lines
COMMENTATOR_HISTORY_SIZE = 10         # recent lines kept to avoid repetition

# Display
BOX_COLOR = (0, 255, 0)       # green bounding box
TEXT_COLOR = (255, 255, 255)   # white text
BAR_BG_COLOR = (40, 40, 40)   # dark gray bar background
FONT_SCALE = 0.6
FONT_THICKNESS = 2
BAR_WIDTH = 150
BAR_HEIGHT = 18
BAR_PADDING = 5

# Emotion colors for bar chart
EMOTION_COLORS = {
    "angry": (0, 0, 255),
    "disgust": (0, 140, 255),
    "fear": (180, 105, 255),
    "happy": (0, 255, 0),
    "sad": (255, 100, 0),
    "surprise": (0, 255, 255),
    "neutral": (200, 200, 200),
}
