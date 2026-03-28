import asyncio
import base64
import io
import json
import tempfile
import os
from pathlib import Path

import cv2
import httpx
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

OLLAMA_BASE = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")


def extract_keyframes(video_path: str, fps: int = 1) -> list[str]:
    """Extract keyframes from video at given fps, return base64-encoded JPEGs."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError("Could not open video file")

    video_fps = cap.get(cv2.CAP_PROP_FPS) or 30
    frame_interval = max(1, int(video_fps / fps))
    frames_b64: list[str] = []
    frame_idx = 0
    max_frames = 10  # cap at 10 frames to avoid overloading the LLM

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % frame_interval == 0:
            # Resize to max 512px on longest side for efficiency
            h, w = frame.shape[:2]
            scale = 512 / max(h, w)
            if scale < 1:
                frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
            _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            frames_b64.append(base64.b64encode(buf.tobytes()).decode())
            if len(frames_b64) >= max_frames:
                break
        frame_idx += 1

    cap.release()
    return frames_b64


async def check_and_pull_model(client: httpx.AsyncClient, model: str) -> None:
    """Check if model exists locally; if not, pull it."""
    try:
        resp = await client.post(f"{OLLAMA_BASE}/api/show", json={"name": model}, timeout=10)
        if resp.status_code == 200:
            return  # model already available
    except httpx.RequestError:
        pass

    # Pull the model (this can take a while on first run)
    async with client.stream(
        "POST", f"{OLLAMA_BASE}/api/pull", json={"name": model}, timeout=600
    ) as resp:
        async for _ in resp.aiter_lines():
            pass  # consume the stream to complete the pull


async def ollama_generate(client: httpx.AsyncClient, model: str, prompt: str, images: list[str] | None = None) -> str:
    """Call Ollama /api/generate and collect the full response."""
    payload: dict = {"model": model, "prompt": prompt, "stream": False}
    if images:
        payload["images"] = images

    resp = await client.post(
        f"{OLLAMA_BASE}/api/generate",
        json=payload,
        timeout=300,
    )
    resp.raise_for_status()
    return resp.json().get("response", "")


@app.get("/api/health")
async def health():
    """Health check – also verifies Ollama is reachable."""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{OLLAMA_BASE}/api/tags", timeout=5)
            r.raise_for_status()
            return {"status": "ok", "ollama": "connected"}
    except Exception as e:
        return {"status": "degraded", "ollama": str(e)}


@app.post("/api/analyze")
async def analyze_video(file: UploadFile = File(...)):
    """Upload a video, extract frames, analyze with VL LLM, return titles & hashtags."""

    async def event_stream():
        vision_model = "llava"
        text_model = "llama3.2"

        try:
            # Step 1 – save uploaded video to a temp file
            yield _sse("status", "Saving uploaded video...")
            suffix = Path(file.filename or "video.mp4").suffix or ".mp4"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                contents = await file.read()
                tmp.write(contents)
                tmp_path = tmp.name

            # Step 2 – extract keyframes
            yield _sse("status", "Extracting keyframes from video...")
            frames = extract_keyframes(tmp_path, fps=1)
            os.unlink(tmp_path)

            if not frames:
                yield _sse("error", "No frames could be extracted from the video.")
                return

            yield _sse("status", f"Extracted {len(frames)} keyframes. Preparing AI models...")

            async with httpx.AsyncClient() as client:
                # Step 3 – ensure models are available
                yield _sse("status", "Checking vision model (llava)... This may take a while on first run.")
                await check_and_pull_model(client, vision_model)

                yield _sse("status", "Checking text model (llama3.2)... This may take a while on first run.")
                await check_and_pull_model(client, text_model)

                # Step 4 – vision analysis (send frames to llava)
                yield _sse("status", "Analyzing video frames with vision AI...")

                vision_prompt = (
                    "You are analyzing frames extracted from a short-form video (TikTok/Reel/Short). "
                    "Describe in detail what is happening in this video: the subject, actions, setting, "
                    "mood, any text overlays, trends, or notable visual elements. Be specific and thorough."
                )

                # Send first frame with all context, then summarize across frames
                if len(frames) == 1:
                    visual_summary = await ollama_generate(client, vision_model, vision_prompt, images=frames)
                else:
                    # Analyze a subset of frames individually then combine
                    sample_indices = [0, len(frames) // 2, -1] if len(frames) >= 3 else list(range(len(frames)))
                    descriptions = []
                    for i, idx in enumerate(sample_indices):
                        yield _sse("status", f"Analyzing frame {i + 1}/{len(sample_indices)}...")
                        desc = await ollama_generate(
                            client, vision_model,
                            f"{vision_prompt}\n\nThis is frame {i + 1} of {len(sample_indices)} from the video.",
                            images=[frames[idx]],
                        )
                        descriptions.append(desc)
                    visual_summary = "\n\n".join(
                        f"Frame {i + 1}: {d}" for i, d in enumerate(descriptions)
                    )

                yield _sse("visual_summary", visual_summary)

                # Step 5 – generate titles & hashtags using text model
                yield _sse("status", "Generating optimized titles and hashtags...")

                hashtag_prompt = f"""Based on the following visual analysis of a short-form video, generate engaging, viral-optimized content.

VISUAL ANALYSIS:
{visual_summary}

Please provide:
1. **5 Title Options** - Short, catchy, click-worthy titles optimized for YouTube Shorts, TikTok, and Instagram Reels. Focus on curiosity, emotion, and CTR optimization.
2. **30 Hashtags** - A mix of:
   - High-volume trending hashtags
   - Niche-specific hashtags related to the content
   - Engagement-boosting hashtags
   Format them as a single block of #hashtags separated by spaces.
3. **Video Description** - A short, engaging description (2-3 sentences) optimized for discoverability.

Format your response clearly with headers for each section."""

                result = await ollama_generate(client, text_model, hashtag_prompt)
                yield _sse("result", result)
                yield _sse("status", "Done!")

        except httpx.ConnectError:
            yield _sse("error", "Cannot connect to Ollama. Make sure Ollama is running on localhost:11434.")
        except Exception as e:
            yield _sse("error", f"An error occurred: {str(e)}")

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _sse(event: str, data: str) -> str:
    """Format a Server-Sent Event."""
    payload = json.dumps({"type": event, "content": data})
    return f"data: {payload}\n\n"
