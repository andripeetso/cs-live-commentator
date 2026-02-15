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

# Smoothing
SMOOTHING_WINDOW = 5          # rolling average over N frames
DEBOUNCE_SECONDS = 1.0        # min interval between emitted events
CONFIDENCE_THRESHOLD = 0.15   # min delta to trigger a new event

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
