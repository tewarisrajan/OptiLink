"""
OptiLink CLI - Unified Command-Line Interface.

Provides commands for:
- sender: Transmit files optically on screen
- receiver: Capture and reconstruct files via camera
- simulate: Test degraded optical link in software
- benchmark: Run empirical benchmarks and produce graphs
- server: Launch FastAPI backend server
"""

import argparse
import sys
import os
import time
import cv2

from .sender.transmitter import OpticalTransmitter
from .receiver.camera import CameraCapture
from .receiver.detector import FrameDetector
from .receiver.perspective import PerspectiveRectifier
from .receiver.color_decoder import ColorCellDecoder
from .receiver.reassembler import SessionReassembler
from .benchmark.simulator import run_optical_simulation, OpticalChannelSimulator
from .benchmark.experiments import BenchmarkSuite


def cmd_send(args):
    print(f"\n[OptiLink Sender] Loading '{args.file}'...")
    mode_map = {"binary": 1, "4color": 2, "8color": 3, "adaptive": 4}
    mode = mode_map.get(args.mode.lower(), 2)

    transmitter = OpticalTransmitter(
        file_path_or_data=args.file,
        modulation_mode=mode,
        grid_rows=args.grid,
        grid_cols=args.grid,
        fps=args.fps,
        fec_ratio=args.fec,
        enable_encryption=not args.no_encrypt,
        enable_compression=not args.no_compress,
    )
    transmitter.prepare()

    meta = transmitter.metadata
    print(f"[OptiLink Sender] Prepared session ID: {meta.session_id}")
    print(f"  File: {meta.filename} ({meta.file_size:,} bytes, SHA-256: {meta.file_sha256[:12]}...)")
    print(f"  Mode: {args.mode.upper()} | Grid: {args.grid}x{args.grid} | Target FPS: {args.fps}")
    print(f"  Packets: {meta.total_source_chunks} source + {meta.total_parity_chunks} parity = {transmitter.total_frames} total")
    if meta.encryption_enabled:
        print(f"  AES-256-GCM Key: {meta.encryption_key}")

    print("\nStarting transmission display... Press 'q' or ESC in the window to quit.")
    cv2.namedWindow("OptiLink Transmitter", cv2.WINDOW_NORMAL)
    if args.fullscreen:
        cv2.setWindowProperty("OptiLink Transmitter", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    delay_ms = max(1, int(1000.0 / args.fps))
    stream = transmitter.get_transmission_stream(target_size=args.size, loop=True)

    for frame_idx, img, pkt, telem in stream:
        cv2.imshow("OptiLink Transmitter", img)
        key = cv2.waitKey(delay_ms) & 0xFF
        if key in (ord("q"), 27):
            break

        # Log progress to terminal
        if frame_idx % 15 == 0:
            sys.stdout.write(
                f"\r[Transmitting] Frame #{frame_idx} | Seq #{telem['seq_num']}/{telem['total_frames']} "
                f"| {telem['progress_percent']}% | {telem['fps']} FPS | {telem['raw_bitrate_kbps']} Kbps"
            )
            sys.stdout.flush()

    cv2.destroyAllWindows()
    print("\n[OptiLink Sender] Transmission ended.")


def cmd_receive(args):
    print(f"\n[OptiLink Receiver] Initializing camera device {args.camera}...")
    cam = CameraCapture(device_index=args.camera, target_width=1280, target_height=720, target_fps=30)
    if not cam.open():
        print(f"[Error] Failed to open camera device index {args.camera}")
        return

    detector = FrameDetector()
    rectifier = PerspectiveRectifier(canonical_size=512, grid_rows=args.grid, grid_cols=args.grid, corner_size=8)
    decoder = ColorCellDecoder(default_mode=2)
    reassembler = SessionReassembler()

    print("[OptiLink Receiver] Camera online. Searching for OptiLink optical frame...")
    print("Point camera at display screen. Press 'q' or ESC to exit.\n")

    cv2.namedWindow("OptiLink Receiver Feed", cv2.WINDOW_NORMAL)

    while True:
        ret, frame = cam.read_frame()
        if not ret or frame is None:
            continue

        detected, quad_pts, method = detector.detect(frame)

        if detected and quad_pts is not None:
            warped, _ = rectifier.rectify(frame, quad_pts)
            pkt, conf, status = decoder.decode_frame(warped)

            if pkt is not None:
                new_pkt, msg = reassembler.process_packet(pkt)
                telem = reassembler.get_telemetry()
                status_str = f"{telem['progress_percent']}% | {telem['speed_kbps']} KB/s"

                if reassembler.is_complete:
                    print(f"\n\n[SUCCESS] Transfer Complete! Verified SHA-256: {telem['sha256']}")
                    out_path = args.output or f"received_{reassembler.metadata.filename}"
                    with open(out_path, "wb") as f:
                        f.write(reassembler.reconstructed_file_bytes)
                    print(f"Saved reconstructed file to: {os.path.abspath(out_path)}")
                    break
            else:
                status_str = f"LOCKED ({conf:.2f})"
        else:
            status_str = "SEARCHING"

        preview = detector.draw_overlay(frame, detected, quad_pts, status_str)
        cv2.imshow("OptiLink Receiver Feed", preview)

        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), 27):
            break

    cam.close()
    cv2.destroyAllWindows()


def cmd_simulate(args):
    print(f"\n[OptiLink Simulation] Simulating optical channel with {args.file_size_kb} KB file...")
    data = os.urandom(args.file_size_kb * 1024)
    channel = OpticalChannelSimulator(
        frame_drop_rate=args.drop_rate,
        tilt_degrees=args.tilt,
        noise_sigma=args.noise,
    )
    results = run_optical_simulation(
        file_bytes=data,
        filename=f"sim_{args.file_size_kb}kb.bin",
        modulation_mode=args.mode,
        grid_rows=args.grid,
        grid_cols=args.grid,
        fec_ratio=args.fec,
        simulator=channel,
    )
    print("\n--- Simulation Results ---")
    for k, v in results.items():
        print(f"  {k:28s}: {v}")


def cmd_benchmark(args):
    print("\n[OptiLink Benchmark] Running empirical parameter sweeps...")
    suite = BenchmarkSuite(args.output_dir)
    graphs = suite.run_all_benchmarks()
    print("\nGenerated Performance Graphs:")
    for name, path in graphs.items():
        print(f"  ✓ {name}: {os.path.abspath(path)}")


def cmd_server(args):
    import uvicorn
    print(f"\n[OptiLink Server] Launching FastAPI backend on http://{args.host}:{args.port}...")
    uvicorn.run("optilink.server.app:app", host=args.host, port=args.port, reload=args.reload)


def main():
    parser = argparse.ArgumentParser(description="OptiLink Optical Communication System")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Sender command
    p_send = subparsers.add_parser("send", help="Transmit file optically on screen")
    p_send.add_argument("file", help="Path to file to transmit")
    p_send.add_argument("--mode", default="4color", choices=["binary", "4color", "8color", "adaptive"])
    p_send.add_argument("--grid", type=int, default=32, help="Grid size (e.g. 32 for 32x32)")
    p_send.add_argument("--fps", type=int, default=30, help="Transmission frame rate")
    p_send.add_argument("--fec", type=float, default=0.20, help="FEC parity ratio")
    p_send.add_argument("--size", type=int, default=768, help="Window display size in px")
    p_send.add_argument("--fullscreen", action="store_true", help="Launch in fullscreen mode")
    p_send.add_argument("--no-encrypt", action="store_true", help="Disable AES-256-GCM encryption")
    p_send.add_argument("--no-compress", action="store_true", help="Disable zlib compression")
    p_send.set_defaults(func=cmd_send)

    # Receiver command
    p_recv = subparsers.add_parser("receive", help="Receive file via camera")
    p_recv.add_argument("--camera", type=int, default=0, help="Webcam device index")
    p_recv.add_argument("--grid", type=int, default=32, help="Expected grid dimension")
    p_recv.add_argument("--output", default=None, help="Destination file path")
    p_recv.set_defaults(func=cmd_receive)

    # Simulation command
    p_sim = subparsers.add_parser("simulate", help="Run degraded optical channel simulation")
    p_sim.add_argument("--file-size-kb", type=int, default=10, help="Simulated file size in KB")
    p_sim.add_argument("--mode", type=int, default=2, help="1=Binary, 2=4-Color, 3=8-Color")
    p_sim.add_argument("--grid", type=int, default=32, help="Grid dimension")
    p_sim.add_argument("--fec", type=float, default=0.20, help="FEC parity ratio")
    p_sim.add_argument("--drop-rate", type=float, default=0.08, help="Frame drop rate (e.g. 0.08 = 8%%)")
    p_sim.add_argument("--tilt", type=float, default=10.0, help="Perspective tilt in degrees")
    p_sim.add_argument("--noise", type=float, default=5.0, help="Gaussian noise sigma")
    p_sim.set_defaults(func=cmd_simulate)

    # Benchmark command
    p_bench = subparsers.add_parser("benchmark", help="Run benchmark suite and generate graphs")
    p_bench.add_argument("--output-dir", default="docs/benchmark_results")
    p_bench.set_defaults(func=cmd_benchmark)

    # Server command
    p_srv = subparsers.add_parser("server", help="Launch FastAPI backend")
    p_srv.add_argument("--host", default="127.0.0.1")
    p_srv.add_argument("--port", type=int, default=8000)
    p_srv.add_argument("--reload", action="store_true")
    p_srv.set_defaults(func=cmd_server)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
