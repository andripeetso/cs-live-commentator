"""
Webcam Emotion Detector + AI Commentator
Usage: python main.py [--camera 0]
"""

import argparse
import os

from dotenv import load_dotenv

# Load .env before any other imports that might need env vars
load_dotenv()

from emotion_detector import config
from emotion_detector.pipeline import EmotionPipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Real-time webcam emotion detection")
    parser.add_argument("--camera", type=int, default=config.CAMERA_INDEX, help="Camera index")
    args = parser.parse_args()

    pipeline = EmotionPipeline(camera_index=args.camera)
    pipeline.run()


if __name__ == "__main__":
    main()
