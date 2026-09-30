# OptiLink — High-Speed Optical Data Transfer System

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![React + Vite](https://img.shields.io/badge/Frontend-React%20%2B%20Vite-purple.svg)](https://vitejs.dev/)
[![AES-256-GCM](https://img.shields.io/badge/Security-AES--256--GCM-red.svg)]()
[![Tests](https://img.shields.io/badge/Tests-Passing-brightgreen.svg)]()

> **OptiLink** is an experimental, contactless optical wireless communication (OWC) system that transfers arbitrary binary files from a computer display to an optical sensor (webcam or smartphone camera) using rapidly changing modulated colored visual patterns.

OptiLink does **NOT** use Wi-Fi, Bluetooth, NFC, USB, QR codes, or the Internet for the actual data transfer. The screen and camera are the physical communication channel.

---

## 🚀 Key Features

* **Custom Optical Framing Protocol:** No generic QR codes. Features sub-pixel ArUco corner fiducials, 25-byte fixed headers with CRC-16, and CRC-32 integrity checking.
* **Multi-Tier Error Correction:**
  * **In-Frame Reed-Solomon:** Corrects localized pixel noise, glints, and color misclassifications within individual frames.
  * **2D Cross-Frame Erasure Coding:** Reconstructs lost or blurred frames without requiring retransmission.
* **Multi-Color Modulation Schemes:**
  * **Mode 1 (Binary):** 1 bit/cell (maximum noise margin).
  * **Mode 2 (4-Color):** 2 bits/cell (optimal balance of density and resilience).
  * **Mode 3 (8-Color):** 3 bits/cell (vertices of 3D RGB color cube).
  * **Mode 4 (Adaptive):** Dynamic scaling based on real-time channel SNR proxy and decoding confidence.
* **Dynamic In-Frame Color Calibration:** Built-in optical reference strip equalizes ambient lighting drift, display gamma, and camera auto-white-balance.
* **End-to-End Cryptography:** Authenticated AES-256-GCM cipher with random session key and 96-bit nonce. Transmits ciphertext over the optical link.
* **Complete UI & CLI:**
  * **React + Vite Dashboard:** Fullscreen optical transmission canvas, live camera reception view, channel impairment simulator, and benchmark graph visualizer.
  * **Unified Python CLI:** Run sender, receiver, simulator, benchmarks, and backend server with single commands.

---

## 📦 System Architecture

```text
┌────────────────────────────────────────────────────────┐
│ Sender:                                                │
│ File → Zlib Deflate → AES-256-GCM → Chunker            │
│       → 2D Reed-Solomon FEC → Optical Packetizer       │
│       → Visual Color Modulation → Display Canvas       │
└───────────────────────────┬────────────────────────────┘
                            │
                   [ Photons in Air ]
                            │
┌───────────────────────────▼────────────────────────────┐
│ Receiver:                                              │
│ Camera Capture → ArUco Corner Detection                │
│       → Perspective Rectification (Homography)         │
│       → In-Frame Color Calibration → Cell Demodulation │
│       → CRC-32 Check & In-Frame RS Repair              │
│       → 2D Cross-Frame Erasure Decoding                │
│       → AES-256-GCM Decryption → SHA-256 Verification   │
└────────────────────────────────────────────────────────┘
```

---

## 🛠️ Installation

### 1. Prerequisites
* Python 3.11+ (Python 3.14 compatible)
* Node.js v18+ & npm

### 2. Install Python Dependencies
```bash
python -m pip install -r requirements.txt
```
*(Or manually: `python -m pip install opencv-python cryptography matplotlib reedsolo fastapi uvicorn python-multipart pytest`)*

### 3. Build React Frontend
```bash
cd frontend
npm install
npm run build
cd ..
```

---

## 🎮 Quickstart Guide

### Option A: Launch Full Web Dashboard (Sender + Receiver + Simulator)
```bash
python -m optilink.cli server --port 8000
```
Open **`http://localhost:8000`** in your browser to access:
* **Optical Transmitter:** Select any file, configure modulation, and project fullscreen optical patterns.
* **Camera Receiver:** Connect webcam, track optical bounding quad in real time, and download verified files.
* **Channel Simulator:** Simulate packet loss, perspective tilt, lens blur, and sensor noise.
* **Empirical Benchmarks:** Inspect performance graphs and metrics.

---

### Option B: Terminal Command-Line Interface (CLI)

#### 1. Transmit a File (Sender)
```bash
python -m optilink.cli send ./sample.txt --mode 4color --grid 32 --fps 30
```
*Press `q` or `ESC` to stop transmission.*

#### 2. Capture and Reconstruct (Receiver)
```bash
python -m optilink.cli receive --camera 0 --grid 32 --output ./received_sample.txt
```

#### 3. Run Optical Channel Simulation
Test the protocol against synthetic physical impairments (frame drops, tilt, blur, noise):
```bash
python -m optilink.cli simulate --file-size-kb 10 --drop-rate 0.08 --tilt 12.0 --noise 5.0
```

#### 4. Run Benchmark Suite & Generate Graphs
```bash
python -m optilink.cli benchmark --output-dir docs/benchmark_results
```
Generates all 6 empirical research graphs in `docs/benchmark_results/`:
1. `throughput_vs_fps.png`
2. `throughput_vs_colors.png`
3. `error_rate_vs_distance.png`
4. `error_rate_vs_lighting.png`
5. `goodput_vs_grid_size.png`
6. `fec_overhead_vs_recovery.png`

#### 5. Run Unit & Integration Test Suite
```bash
python -m pytest tests/test_optilink.py
```

---

## 🧪 Experimental Demonstrations

| Demo | Scenario | Procedure | Outcome |
|---|---|---|---|
| **Demo 1** | Small Text Transfer | `python -m optilink.cli send sample.txt` | Instant transmission and SHA-256 verification |
| **Demo 2** | Binary / Media Transfer | Transfer JPG, PNG, MP4, or ZIP file | Streaming chunker handles binary without RAM bloat |
| **Demo 3** | Off-Axis Camera Movement | Move webcam up to $\pm 35^\circ$ tilt | ArUco fiducials & homography maintain link lock |
| **Demo 4** | Dim Lighting / Glare | Dim ambient room lighting | Calibration strip equalizes RGB color drift |
| **Demo 5** | Artificial Frame Loss | Simulate $15\%$ dropped camera frames | Cross-Frame FEC reconstructs $100\%$ of data |
| **Demo 6** | Palette Comparison | Compare Binary vs. 4-Color vs. 8-Color | Evaluates noise margin vs. raw bitrate trade-off |
| **Demo 7** | Adaptive Rate Scaling | Observe mode adaptation under noise | Dynamically shifts parameters to maximize goodput |

---

## 📁 Repository Structure

```text
optilink/
├── optilink/
│   ├── sender/             # File reading, compression, AES-GCM encryption, chunker, transmitter
│   ├── protocol/           # Fixed headers, CRC-16/32, Reed-Solomon in-frame & 2D erasure coding
│   ├── optical/            # Color palettes, modulation, calibration strip, ArUco frame generator
│   ├── receiver/           # Camera capture, sub-pixel detector, homography rectifier, reassembler
│   ├── adaptive/           # Channel state estimation & rate adaptation engine
│   ├── benchmark/          # Optical channel simulator, empirical metric sweeps, plotting
│   ├── server/             # FastAPI REST & WebSocket server with static frontend serving
│   └── cli.py              # Unified Command-Line Interface
├── frontend/               # React + Vite cyberpunk dashboard
├── tests/                  # Pytest unit and integration test suite
├── docs/
│   ├── ARCHITECTURE.md     # Detailed architecture & Mermaid flowcharts
│   ├── PROTOCOL_SPEC.md    # Formal Optical Protocol Specification v1.0
│   ├── TECHNICAL_REPORT.md # Research report answering core questions
│   └── benchmark_results/  # Generated empirical performance charts (PNG)
├── requirements.txt        # Python dependency manifest
└── README.md
```

---

## 🛡️ License

MIT License. Developed for advanced experimental research into display-to-camera optical data transmission.
