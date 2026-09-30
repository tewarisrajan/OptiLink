"""
OptiLink Server - FastAPI Backend.

Provides REST and WebSocket endpoints for the React dashboard:
- File preparation and session management
- Real frame symbol matrices for client-side 60 FPS canvas rendering
- Live hardware camera processing thread with MJPEG video feed
- Browser camera frame upload and real-time processing endpoint
- Optical simulation and benchmarking execution
"""

import os
import io
import time
import base64
import threading
from typing import Optional, Dict, Any, List
import cv2
import numpy as np

from fastapi import FastAPI, UploadFile, File, Form, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..sender.transmitter import OpticalTransmitter
from ..receiver.detector import FrameDetector
from ..receiver.perspective import PerspectiveRectifier
from ..receiver.color_decoder import ColorCellDecoder
from ..receiver.reassembler import SessionReassembler
from ..receiver.camera import CameraCapture
from ..optical.colors import get_bits_per_cell, rgb_to_hex, get_palette_rgb
from ..optical.modulation import bytes_to_symbols
from ..benchmark.simulator import run_optical_simulation, OpticalChannelSimulator
from ..benchmark.experiments import BenchmarkSuite

app = FastAPI(title="OptiLink Optical Communication API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Session & Receiver Pipeline State
ACTIVE_TRANSMITTER: Optional[OpticalTransmitter] = None
ACTIVE_REASSEMBLER: Optional[SessionReassembler] = None

GLOBAL_DETECTOR = FrameDetector()
GLOBAL_RECTIFIER = PerspectiveRectifier(canonical_size=512, grid_rows=32, grid_cols=32, corner_size=8)
GLOBAL_DECODER = ColorCellDecoder(default_mode=2)

# Hardware camera background worker state
HARDWARE_CAMERA_RUNNING = False
HARDWARE_CAMERA_THREAD: Optional[threading.Thread] = None
LATEST_ANNOTATED_FRAME: Optional[bytes] = None
CAMERA_LOCK = threading.Lock()


class SimulationRequest(BaseModel):
    file_size_kb: int = 5
    modulation_mode: int = 2
    grid_size: int = 32
    fec_ratio: float = 0.20
    drop_rate: float = 0.05
    tilt_degrees: float = 10.0
    noise_sigma: float = 5.0


@app.get("/api/health")
def health():
    return {
        "status": "online",
        "system": "OptiLink Optical Communication System",
        "hardware_camera_running": HARDWARE_CAMERA_RUNNING,
    }


@app.post("/api/session/create")
async def create_session(
    file: Optional[UploadFile] = File(None),
    filename: str = Form("transfer.bin"),
    modulation_mode: int = Form(2),
    grid_size: int = Form(32),
    fps: int = Form(30),
    fec_ratio: float = Form(0.20),
    enable_encryption: bool = Form(True),
    enable_compression: bool = Form(True),
    content_text: Optional[str] = Form(None),
):
    global ACTIVE_TRANSMITTER, ACTIVE_REASSEMBLER

    if file:
        data = await file.read()
        fname = file.filename or filename
    elif content_text:
        data = content_text.encode("utf-8")
        fname = filename
    else:
        data = (b"OptiLink High-Speed Optical Wireless Data Transfer Protocol Demonstration.\n" * 30)
        fname = "optilink_demo.txt"

    transmitter = OpticalTransmitter(
        file_path_or_data=data,
        filename=fname,
        modulation_mode=modulation_mode,
        grid_rows=grid_size,
        grid_cols=grid_size,
        fps=fps,
        fec_ratio=fec_ratio,
        enable_encryption=enable_encryption,
        enable_compression=enable_compression,
    )
    transmitter.prepare()

    ACTIVE_TRANSMITTER = transmitter
    # Initialize receiver reassembler with sender session metadata for instant sync if on same host
    if ACTIVE_REASSEMBLER is None:
        ACTIVE_REASSEMBLER = SessionReassembler(metadata=transmitter.metadata)
    else:
        ACTIVE_REASSEMBLER.metadata = transmitter.metadata

    GLOBAL_RECTIFIER.update_grid(grid_rows=grid_size, grid_cols=grid_size, corner_size=8)
    GLOBAL_DECODER.update_layout(rows=grid_size, cols=grid_size, corner_size=8)
    GLOBAL_DECODER.current_mode = modulation_mode

    return {
        "status": "ready",
        "session_id": transmitter.session_id,
        "filename": transmitter.filename,
        "file_size": transmitter.file_size,
        "total_frames": transmitter.total_frames,
        "chunk_size": transmitter.metadata.chunk_size,
        "total_source_chunks": transmitter.metadata.total_source_chunks,
        "total_parity_chunks": transmitter.metadata.total_parity_chunks,
        "encryption_key": transmitter.metadata.encryption_key,
        "sha256": transmitter.metadata.file_sha256,
        "modulation_mode": transmitter.modulation_mode,
        "grid_size": f"{grid_size}x{grid_size}",
    }


@app.get("/api/session/frames_data")
def get_frames_data():
    """
    Returns symbol sequences for all prepared packets.
    Allows the React frontend canvas to render the real optical frames at 60 FPS smoothly.
    """
    global ACTIVE_TRANSMITTER
    if not ACTIVE_TRANSMITTER or not ACTIVE_TRANSMITTER.is_prepared:
        raise HTTPException(status_code=400, detail="No active transmission session prepared")

    bpc = get_bits_per_cell(ACTIVE_TRANSMITTER.modulation_mode)
    palette_rgb = get_palette_rgb(ACTIVE_TRANSMITTER.modulation_mode)
    palette_hex = [rgb_to_hex(c) for c in palette_rgb]

    frames_payload = []
    for pkt in ACTIVE_TRANSMITTER.packets:
        pkt_bytes = pkt.serialize()
        symbols = bytes_to_symbols(pkt_bytes, bpc)
        frames_payload.append({
            "seq": pkt.header.seq_num,
            "type": int(pkt.header.frame_type),
            "payload_len": pkt.header.payload_len,
            "symbols": symbols.tolist(),
        })

    return {
        "session_id": ACTIVE_TRANSMITTER.session_id,
        "filename": ACTIVE_TRANSMITTER.filename,
        "file_size": ACTIVE_TRANSMITTER.file_size,
        "total_frames": ACTIVE_TRANSMITTER.total_frames,
        "fps": ACTIVE_TRANSMITTER.fps,
        "grid_size": ACTIVE_TRANSMITTER.grid_rows,
        "modulation_mode": ACTIVE_TRANSMITTER.modulation_mode,
        "palette": palette_hex,
        "frames": frames_payload,
    }


@app.get("/api/session/frame/{index}")
def get_frame(index: int, target_size: int = 768):
    global ACTIVE_TRANSMITTER
    if not ACTIVE_TRANSMITTER or not ACTIVE_TRANSMITTER.is_prepared:
        raise HTTPException(status_code=400, detail="No active transmission session prepared")

    idx = index % len(ACTIVE_TRANSMITTER.packets)
    pkt = ACTIVE_TRANSMITTER.packets[idx]
    img = ACTIVE_TRANSMITTER.generator.generate_grid_image(pkt, target_size=target_size)

    ret, buf = cv2.imencode(".png", img)
    return StreamingResponse(io.BytesIO(buf.tobytes()), media_type="image/png")


# --- RECEIVER ENDPOINTS ---

@app.post("/api/receiver/reset")
def reset_receiver():
    """Resets reassembler state for a new transfer."""
    global ACTIVE_REASSEMBLER
    meta = ACTIVE_TRANSMITTER.metadata if ACTIVE_TRANSMITTER else None
    ACTIVE_REASSEMBLER = SessionReassembler(metadata=meta)
    return {"status": "reset", "message": "Receiver state cleared"}


@app.get("/api/receiver/status")
def get_receiver_status():
    global ACTIVE_REASSEMBLER
    if not ACTIVE_REASSEMBLER:
        return {"active": False, "message": "Receiver idle"}
    return {
        "active": True,
        "hardware_camera_running": HARDWARE_CAMERA_RUNNING,
        **ACTIVE_REASSEMBLER.get_telemetry(),
    }


@app.post("/api/receiver/process_frame")
async def process_frame(file: UploadFile = File(...)):
    """
    Accepts a video frame captured by the browser's webcam or phone camera.
    Processes the frame through the real CV detection, homography rectification,
    and demodulation pipeline.
    """
    global ACTIVE_REASSEMBLER, GLOBAL_DETECTOR, GLOBAL_RECTIFIER, GLOBAL_DECODER

    if ACTIVE_REASSEMBLER is None:
        meta = ACTIVE_TRANSMITTER.metadata if ACTIVE_TRANSMITTER else None
        ACTIVE_REASSEMBLER = SessionReassembler(metadata=meta)

    # Read uploaded image bytes
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if frame is None:
        raise HTTPException(status_code=400, detail="Failed to decode image frame")

    # 1. Detect optical transmission frame
    detected, quad_pts, method = GLOBAL_DETECTOR.detect(frame)

    packet_decoded = False
    status_str = "SEARCHING"
    confidence = 0.0

    if detected and quad_pts is not None:
        # 2. Rectify perspective
        warped, _ = GLOBAL_RECTIFIER.rectify(frame, quad_pts, method=method)

        # 3. Decode cells
        pkt, conf, dec_status = GLOBAL_DECODER.decode_frame(warped)
        confidence = float(conf)

        if pkt is not None:
            packet_decoded = True
            new_pkt, msg = ACTIVE_REASSEMBLER.process_packet(pkt)
            status_str = msg
        else:
            status_str = f"LOCKED ({conf:.2f}) - {dec_status}"
    else:
        status_str = "SEARCHING FOR FIDUCIAL MARKERS"

    telemetry = ACTIVE_REASSEMBLER.get_telemetry()

    return {
        "detected": bool(detected),
        "quad_pts": quad_pts.tolist() if quad_pts is not None else None,
        "method": method,
        "confidence": round(confidence, 2),
        "packet_decoded": packet_decoded,
        "status": status_str,
        "telemetry": telemetry,
    }


# --- HARDWARE WEBCAM BACKGROUND WORKER ---

def _hardware_camera_worker(device_index: int = 0):
    global HARDWARE_CAMERA_RUNNING, LATEST_ANNOTATED_FRAME, ACTIVE_REASSEMBLER

    cam = CameraCapture(device_index=device_index, target_width=1280, target_height=720, target_fps=30)
    if not cam.open():
        HARDWARE_CAMERA_RUNNING = False
        return

    HARDWARE_CAMERA_RUNNING = True

    while HARDWARE_CAMERA_RUNNING:
        ret, frame = cam.read_frame()
        if not ret or frame is None:
            time.sleep(0.01)
            continue

        detected, quad_pts, method = GLOBAL_DETECTOR.detect(frame)
        status_str = "SEARCHING"

        if detected and quad_pts is not None:
            warped, _ = GLOBAL_RECTIFIER.rectify(frame, quad_pts, method=method)
            pkt, conf, dec_status = GLOBAL_DECODER.decode_frame(warped)

            if pkt is not None and ACTIVE_REASSEMBLER is not None:
                new_pkt, msg = ACTIVE_REASSEMBLER.process_packet(pkt)
                telem = ACTIVE_REASSEMBLER.get_telemetry()
                status_str = f"RX #{pkt.header.seq_num} | {telem['progress_percent']}% | {telem['speed_kbps']} KB/s"
            else:
                status_str = f"LOCKED ({conf:.2f})"
        else:
            status_str = "SEARCHING"

        # Draw overlay HUD
        annotated = GLOBAL_DETECTOR.draw_overlay(frame, detected, quad_pts, status_str)

        # Encode to JPEG for MJPEG stream
        ret_enc, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ret_enc:
            with CAMERA_LOCK:
                LATEST_ANNOTATED_FRAME = buf.tobytes()

        time.sleep(0.01)

    cam.close()
    HARDWARE_CAMERA_RUNNING = False


@app.post("/api/receiver/start_hardware_camera")
def start_hardware_camera(device_index: int = 0):
    global HARDWARE_CAMERA_THREAD, HARDWARE_CAMERA_RUNNING, ACTIVE_REASSEMBLER
    if HARDWARE_CAMERA_RUNNING:
        return {"status": "running", "message": "Hardware camera is already active"}

    if ACTIVE_REASSEMBLER is None:
        meta = ACTIVE_TRANSMITTER.metadata if ACTIVE_TRANSMITTER else None
        ACTIVE_REASSEMBLER = SessionReassembler(metadata=meta)

    HARDWARE_CAMERA_THREAD = threading.Thread(
        target=_hardware_camera_worker,
        args=(device_index,),
        daemon=True,
    )
    HARDWARE_CAMERA_THREAD.start()
    return {"status": "starting", "message": f"Hardware camera {device_index} starting"}


@app.post("/api/receiver/stop_hardware_camera")
def stop_hardware_camera():
    global HARDWARE_CAMERA_RUNNING
    HARDWARE_CAMERA_RUNNING = False
    return {"status": "stopped", "message": "Hardware camera stopped"}


@app.get("/api/receiver/video_feed")
def video_feed():
    """MJPEG streaming endpoint for live camera receiver preview."""
    def frame_generator():
        while True:
            frame_bytes = None
            with CAMERA_LOCK:
                if LATEST_ANNOTATED_FRAME is not None:
                    frame_bytes = LATEST_ANNOTATED_FRAME

            if frame_bytes is not None:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
                )
            time.sleep(0.033)  # ~30 FPS

    return StreamingResponse(
        frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/api/receiver/download")
def download_received_file():
    global ACTIVE_REASSEMBLER
    if not ACTIVE_REASSEMBLER or not ACTIVE_REASSEMBLER.is_complete:
        raise HTTPException(status_code=400, detail="No completed file available for download")

    filename = ACTIVE_REASSEMBLER.metadata.filename if ACTIVE_REASSEMBLER.metadata else "optilink_received.bin"
    return StreamingResponse(
        io.BytesIO(ACTIVE_REASSEMBLER.reconstructed_file_bytes),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --- SIMULATION & BENCHMARKS ---

@app.post("/api/simulate/run")
def run_simulation(req: SimulationRequest):
    size_bytes = max(100, req.file_size_kb * 1024)
    test_data = os.urandom(size_bytes)

    channel = OpticalChannelSimulator(
        frame_drop_rate=req.drop_rate,
        tilt_degrees=req.tilt_degrees,
        noise_sigma=req.noise_sigma,
    )

    results = run_optical_simulation(
        file_bytes=test_data,
        filename=f"sim_{req.file_size_kb}kb.bin",
        modulation_mode=req.modulation_mode,
        grid_rows=req.grid_size,
        grid_cols=req.grid_size,
        fec_ratio=req.fec_ratio,
        simulator=channel,
    )
    return results


@app.post("/api/benchmark/run")
def trigger_benchmarks():
    suite = BenchmarkSuite("docs/benchmark_results")
    graph_map = suite.run_all_benchmarks()
    return {
        "status": "completed",
        "graphs": {k: f"/api/benchmark/image/{os.path.basename(v)}" for k, v in graph_map.items()},
    }


@app.get("/api/benchmark/image/{filename}")
def get_benchmark_image(filename: str):
    path = os.path.join("docs", "benchmark_results", filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Benchmark graph not found")
    return FileResponse(path, media_type="image/png")


# Serve built React frontend if available
frontend_dist = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
if os.path.exists(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
