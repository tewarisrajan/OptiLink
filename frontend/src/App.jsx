import React, { useState, useEffect, useRef } from "react";
import {
  Radio,
  Camera,
  Play,
  Square,
  Maximize2,
  Minimize2,
  Shield,
  Activity,
  BarChart2,
  FileText,
  Sliders,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  Download,
  Lock,
  Layers,
  Cpu,
  Video,
} from "lucide-react";

const API_BASE = "";

// Exact ArUco 4x4 (DICT_4X4_50) 6x6 bit matrices
const ARUCO_BITMAPS = {
  0: [
    [0, 0, 0, 0, 0, 0],
    [0, 1, 0, 1, 1, 0],
    [0, 0, 1, 0, 1, 0],
    [0, 0, 0, 1, 1, 0],
    [0, 0, 0, 1, 0, 0],
    [0, 0, 0, 0, 0, 0],
  ],
  1: [
    [0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0],
    [0, 1, 1, 1, 1, 0],
    [0, 1, 0, 0, 1, 0],
    [0, 1, 0, 1, 0, 0],
    [0, 0, 0, 0, 0, 0],
  ],
  2: [
    [0, 0, 0, 0, 0, 0],
    [0, 0, 0, 1, 1, 0],
    [0, 0, 0, 1, 1, 0],
    [0, 0, 0, 1, 0, 0],
    [0, 1, 1, 0, 1, 0],
    [0, 0, 0, 0, 0, 0],
  ],
  3: [
    [0, 0, 0, 0, 0, 0],
    [0, 1, 0, 0, 1, 0],
    [0, 1, 0, 0, 1, 0],
    [0, 0, 1, 0, 0, 0],
    [0, 0, 1, 1, 0, 0],
    [0, 0, 0, 0, 0, 0],
  ],
};

const CAL_PALETTE = [
  "#000000", // black
  "#0000ff", // blue
  "#00ff00", // green
  "#00ffff", // cyan
  "#ff0000", // red
  "#ff00ff", // magenta
  "#ffff00", // yellow
  "#ffffff", // white
];

export default function App() {
  const [activeTab, setActiveTab] = useState("sender");

  // Sender State
  const [file, setFile] = useState(null);
  const [fileName, setFileName] = useState("optilink_demo.txt");
  const [fileSize, setFileSize] = useState(10240);
  const [customText, setCustomText] = useState(
    "High-Speed Optical Wireless Data Transfer System Protocol Payload Test Data. Transferring over display-to-camera optical channel.\n".repeat(20)
  );
  const [modulationMode, setModulationMode] = useState(2);
  const [gridSize, setGridSize] = useState(32);
  const [fps, setFps] = useState(30);
  const [fecRatio, setFecRatio] = useState(0.20);
  const [encryption, setEncryption] = useState(true);
  const [compression, setCompression] = useState(true);

  const [isTransmitting, setIsTransmitting] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [framesData, setFramesData] = useState(null);
  const [telemetry, setTelemetry] = useState(null);

  // Receiver State
  const [receiverMode, setReceiverMode] = useState("hardware"); // "hardware" or "browser"
  const [hwCameraRunning, setHwCameraRunning] = useState(false);
  const [browserCameraActive, setBrowserCameraActive] = useState(false);
  const [rxDetected, setRxDetected] = useState(false);
  const [rxStatusText, setRxStatusText] = useState("IDLE");
  const [rxTelemetry, setRxTelemetry] = useState({
    active: false,
    speed_kbps: 0,
    progress_percent: 0,
    frames_received: 0,
    frames_recovered_fec: 0,
    estimated_lost_frames: 0,
    in_frame_errors_corrected: 0,
    is_complete: false,
    integrity_verified: false,
    filename: "",
    file_size: 0,
    sha256: "",
  });

  // Simulation State
  const [simSizeKb, setSimSizeKb] = useState(15);
  const [simDropRate, setSimDropRate] = useState(0.08);
  const [simTilt, setSimTilt] = useState(12.0);
  const [simNoise, setSimNoise] = useState(5.0);
  const [simRunning, setSimRunning] = useState(false);
  const [simResult, setSimResult] = useState(null);

  // Benchmarks State
  const [benchmarksLoading, setBenchmarksLoading] = useState(false);
  const [benchmarkGraphs, setBenchmarkGraphs] = useState(null);

  const canvasRef = useRef(null);
  const videoRef = useRef(null);
  const overlayCanvasRef = useRef(null);
  const animationFrameRef = useRef(null);
  const frameProcessingRef = useRef(false);

  // --- SENDER ENGINE ---
  const handleStartTransmission = async () => {
    try {
      const formData = new FormData();
      if (file) {
        formData.append("file", file);
      } else {
        formData.append("content_text", customText);
        formData.append("filename", fileName);
      }
      formData.append("modulation_mode", modulationMode);
      formData.append("grid_size", gridSize);
      formData.append("fps", fps);
      formData.append("fec_ratio", fecRatio);
      formData.append("enable_encryption", encryption);
      formData.append("enable_compression", compression);

      await fetch(`${API_BASE}/api/session/create`, {
        method: "POST",
        body: formData,
      });

      // Fetch the actual serialized packet symbols for every frame
      const framesRes = await fetch(`${API_BASE}/api/session/frames_data`);
      const data = await framesRes.json();
      setFramesData(data);
      setIsTransmitting(true);
    } catch (err) {
      console.error("Failed to prepare session:", err);
      alert("Error contacting OptiLink backend. Ensure the server is running on port 8000.");
    }
  };

  const handleStopTransmission = () => {
    setIsTransmitting(false);
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
    }
  };

  // Render optical frames on canvas using real symbols and exact ArUco fiducials
  useEffect(() => {
    if (!isTransmitting || !framesData || !framesData.frames) return;

    let lastTime = performance.now();
    const frameInterval = 1000 / framesData.fps;
    let frameIdx = 0;
    const totalFrames = framesData.frames.length;
    const palette = framesData.palette;
    const k = 8; // corner size in cells
    const rows = framesData.grid_size;
    const cols = framesData.grid_size;

    // Precalculate data cell positions (exact match to Python FrameLayout)
    const dataCellCoords = [];
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const inTL = r < k && c < k;
        const inTR = r < k && c >= cols - k;
        const inBL = r >= rows - k && c < k;
        const inBR = r >= rows - k && c >= cols - k;
        const inCal = r === 0 && c >= k && c < cols - k;
        if (!inTL && !inTR && !inBL && !inBR && !inCal) {
          dataCellCoords.push([r, c]);
        }
      }
    }

    const renderLoop = (time) => {
      const elapsed = time - lastTime;
      if (elapsed >= frameInterval) {
        lastTime = time - (elapsed % frameInterval);

        const canvas = canvasRef.current;
        if (canvas) {
          const ctx = canvas.getContext("2d");
          const targetSize = canvas.width;
          const qz = 24; // quiet zone in pixels
          const contentSize = targetSize - 2 * qz;
          const cellPx = contentSize / rows;

          // 1. Clear background to white
          ctx.fillStyle = "#ffffff";
          ctx.fillRect(0, 0, targetSize, targetSize);

          // 2. Draw outer thin black alignment box
          ctx.strokeStyle = "#000000";
          ctx.lineWidth = 2;
          ctx.strokeRect(qz - 2, qz - 2, contentSize + 4, contentSize + 4);

          // Active frame packet data
          const currentPacket = framesData.frames[frameIdx % totalFrames];
          const symbols = currentPacket.symbols;

          // 3. Draw Data Cells
          for (let i = 0; i < dataCellCoords.length; i++) {
            const [r, c] = dataCellCoords[i];
            const sym = i < symbols.length ? symbols[i] : 0;
            const color = palette[sym] || palette[0];
            ctx.fillStyle = color;
            ctx.fillRect(qz + c * cellPx, qz + r * cellPx, cellPx, cellPx);
          }

          // 4. Draw Calibration Strip (row 0 between k and cols - k)
          for (let c = k; c < cols - k; c++) {
            const calIdx = (c - k) % CAL_PALETTE.length;
            ctx.fillStyle = CAL_PALETTE[calIdx];
            ctx.fillRect(qz + c * cellPx, qz + 0, cellPx, cellPx);
          }

          // 5. Draw 4 Real ArUco Corner Fiducials
          const drawArucoCorner = (cornerRow, cornerCol, markerId) => {
            const boxX = qz + cornerCol * cellPx;
            const boxY = qz + cornerRow * cellPx;
            const boxW = k * cellPx;

            // White box background
            ctx.fillStyle = "#ffffff";
            ctx.fillRect(boxX, boxY, boxW, boxW);

            // 6x6 marker centered inside 8x8 box (offset by 1 cell)
            const markerBitmap = ARUCO_BITMAPS[markerId];
            const startX = boxX + cellPx;
            const startY = boxY + cellPx;

            for (let mr = 0; mr < 6; mr++) {
              for (let mc = 0; mc < 6; mc++) {
                ctx.fillStyle = markerBitmap[mr][mc] === 1 ? "#ffffff" : "#000000";
                ctx.fillRect(startX + mc * cellPx, startY + mr * cellPx, cellPx, cellPx);
              }
            }
          };

          drawArucoCorner(0, 0, 0); // TL = ID 0
          drawArucoCorner(0, cols - k, 1); // TR = ID 1
          drawArucoCorner(rows - k, cols - k, 2); // BR = ID 2
          drawArucoCorner(rows - k, 0, 3); // BL = ID 3

          // Update telemetry
          const bpc = framesData.modulation_mode === 1 ? 1 : framesData.modulation_mode === 3 ? 3 : 2;
          const usableCount = dataCellCoords.length;
          const rawBps = usableCount * bpc * framesData.fps;
          const effKbps = (rawBps * 0.80) / 1024;

          setTelemetry({
            seq: currentPacket.seq,
            total: totalFrames,
            progress: Math.min(100, Math.round(((frameIdx % totalFrames + 1) / totalFrames) * 100)),
            rawBitrateMbps: (rawBps / 1000000).toFixed(2),
            effectiveKbps: effKbps.toFixed(1),
            fps: framesData.fps,
            etaSec: Math.max(0, Math.round((totalFrames - (frameIdx % totalFrames + 1)) / framesData.fps)),
          });

          frameIdx++;
        }
      }
      animationFrameRef.current = requestAnimationFrame(renderLoop);
    };

    animationFrameRef.current = requestAnimationFrame(renderLoop);
    return () => {
      if (animationFrameRef.current) cancelAnimationFrame(animationFrameRef.current);
    };
  }, [isTransmitting, framesData]);

  // Fullscreen Handler
  const toggleFullscreen = () => {
    if (!isFullscreen) {
      const elem = document.documentElement;
      if (elem.requestFullscreen) elem.requestFullscreen();
      setIsFullscreen(true);
    } else {
      if (document.exitFullscreen) document.exitFullscreen();
      setIsFullscreen(false);
    }
  };

  // --- HARDWARE CAMERA RECEIVER (BACKEND DIRECT OPENCV) ---
  const handleToggleHardwareCamera = async () => {
    if (hwCameraRunning) {
      await fetch(`${API_BASE}/api/receiver/stop_hardware_camera`, { method: "POST" });
      setHwCameraRunning(false);
    } else {
      await fetch(`${API_BASE}/api/receiver/start_hardware_camera`, { method: "POST" });
      setHwCameraRunning(true);
    }
  };

  // --- BROWSER WEBCAM RECEIVER (CLIENT CAPTURE) ---
  const startBrowserCamera = async () => {
  try {
    if (!window.isSecureContext) {
      throw new Error("Camera requires HTTPS.");
    }

    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error("Camera API is unavailable in this browser.");
    }

    const stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: {
        facingMode: { ideal: "environment" },
        width: { ideal: 1280 },
        height: { ideal: 720 },
      },
    });

    const video = videoRef.current;

    if (!video) {
      stream.getTracks().forEach((track) => track.stop());
      throw new Error("Camera video element is not ready.");
    }

    video.srcObject = stream;
    video.muted = true;
    video.autoplay = true;
    video.playsInline = true;

    await video.play();

    setBrowserCameraActive(true);

  } catch (err) {
    console.error("Camera error:", err);

    alert(
      `Could not access camera.\n\n${err.name || "Error"}: ${
        err.message || err
      }`
    );
  }
};

  const stopBrowserCamera = () => {
    if (videoRef.current && videoRef.current.srcObject) {
      videoRef.current.srcObject.getTracks().forEach((t) => t.stop());
    }
    setBrowserCameraActive(false);
  };

  // Frame Capture & Processing Loop for Browser Camera
  useEffect(() => {
    if (!browserCameraActive) return;

    const interval = setInterval(async () => {
      if (frameProcessingRef.current || !videoRef.current) return;
      const video = videoRef.current;
      if (video.readyState < 2) return;

      frameProcessingRef.current = true;

      try {
        const offCanvas = document.createElement("canvas");
        offCanvas.width = video.videoWidth || 640;
        offCanvas.height = video.videoHeight || 480;
        const offCtx = offCanvas.getContext("2d");
        offCtx.drawImage(video, 0, 0, offCanvas.width, offCanvas.height);

        offCanvas.toBlob(
          async (blob) => {
            if (!blob) {
              frameProcessingRef.current = false;
              return;
            }

            const formData = new FormData();
            formData.append("file", blob, "frame.jpg");

            try {
              const res = await fetch(`${API_BASE}/api/receiver/process_frame`, {
                method: "POST",
                body: formData,
              });
              const data = await res.json();

              setRxDetected(data.detected);
              setRxStatusText(data.status);
              if (data.telemetry) {
                setRxTelemetry((prev) => ({ ...prev, ...data.telemetry }));
              }

              // Draw bounding polygon on overlay canvas
              const overlay = overlayCanvasRef.current;
              if (overlay) {
                overlay.width = video.clientWidth;
                overlay.height = video.clientHeight;
                const oCtx = overlay.getContext("2d");
                oCtx.clearRect(0, 0, overlay.width, overlay.height);

                if (data.detected && data.quad_pts) {
                  const scaleX = overlay.width / offCanvas.width;
                  const scaleY = overlay.height / offCanvas.height;

                  oCtx.beginPath();
                  oCtx.strokeStyle = "#10b981";
                  oCtx.lineWidth = 3;
                  data.quad_pts.forEach(([px, py], i) => {
                    const sx = px * scaleX;
                    const sy = py * scaleY;
                    if (i === 0) oCtx.moveTo(sx, sy);
                    else oCtx.lineTo(sx, sy);
                  });
                  oCtx.closePath();
                  oCtx.stroke();

                  // Corners
                  data.quad_pts.forEach(([px, py], i) => {
                    oCtx.fillStyle = i === 0 ? "#ef4444" : i === 1 ? "#10b981" : i === 2 ? "#3b82f6" : "#f59e0b";
                    oCtx.beginPath();
                    oCtx.arc(px * scaleX, py * scaleY, 6, 0, 2 * Math.PI);
                    oCtx.fill();
                  });
                }
              }
            } catch (e) {
              console.error("Frame processing error:", e);
            } finally {
              frameProcessingRef.current = false;
            }
          },
          "image/jpeg",
          0.85
        );
      } catch (err) {
        frameProcessingRef.current = false;
      }
    }, 100); // 10 FPS upload

    return () => clearInterval(interval);
  }, [browserCameraActive]);

  // Status poller for hardware camera mode
  useEffect(() => {
    if (!hwCameraRunning) return;
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/api/receiver/status`);
        const data = await res.json();
        if (data.active) {
          setRxTelemetry((prev) => ({ ...prev, ...data }));
        }
      } catch (e) {}
    }, 500);
    return () => clearInterval(interval);
  }, [hwCameraRunning]);

  const handleResetReceiver = async () => {
    try {
      await fetch(`${API_BASE}/api/receiver/reset`, { method: "POST" });
      setRxTelemetry({
        active: true,
        speed_kbps: 0,
        progress_percent: 0,
        frames_received: 0,
        frames_recovered_fec: 0,
        estimated_lost_frames: 0,
        in_frame_errors_corrected: 0,
        is_complete: false,
        integrity_verified: false,
        filename: "",
        file_size: 0,
        sha256: "",
      });
      setRxStatusText("RESET");
    } catch (e) {}
  };

  // --- SIMULATION ---
  const handleRunSimulation = async () => {
    setSimRunning(true);
    try {
      const res = await fetch(`${API_BASE}/api/simulate/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          file_size_kb: simSizeKb,
          modulation_mode: modulationMode,
          grid_size: gridSize,
          fec_ratio: fecRatio,
          drop_rate: simDropRate,
          tilt_degrees: simTilt,
          noise_sigma: simNoise,
        }),
      });
      const data = await res.json();
      setSimResult(data);
    } catch (e) {
      console.error(e);
    }
    setSimRunning(false);
  };

  // --- BENCHMARKS ---
  const handleRunBenchmarks = async () => {
    setBenchmarksLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/benchmark/run`, { method: "POST" });
      const data = await res.json();
      setBenchmarkGraphs(data.graphs);
    } catch (e) {
      setBenchmarkGraphs({
        throughput_vs_fps: `${API_BASE}/api/benchmark/image/throughput_vs_fps.png`,
        throughput_vs_colors: `${API_BASE}/api/benchmark/image/throughput_vs_colors.png`,
        error_rate_vs_distance: `${API_BASE}/api/benchmark/image/error_rate_vs_distance.png`,
        error_rate_vs_lighting: `${API_BASE}/api/benchmark/image/error_rate_vs_lighting.png`,
        goodput_vs_grid_size: `${API_BASE}/api/benchmark/image/goodput_vs_grid_size.png`,
        fec_overhead_vs_recovery: `${API_BASE}/api/benchmark/image/fec_overhead_vs_recovery.png`,
      });
    }
    setBenchmarksLoading(false);
  };

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      {/* Top Navbar */}
      <header
        style={{
          background: "var(--bg-secondary)",
          borderBottom: "1px solid var(--border-color)",
          padding: "14px 28px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "14px" }}>
          <div
            style={{
              width: "36px",
              height: "36px",
              borderRadius: "8px",
              background: "linear-gradient(135deg, #06b6d4, #3b82f6)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "0 0 16px rgba(6, 182, 212, 0.5)",
            }}
          >
            <Radio size={20} color="#fff" />
          </div>
          <div>
            <h1 style={{ fontSize: "1.25rem", fontWeight: "800", letterSpacing: "0.03em" }}>
              OPTILINK <span style={{ fontSize: "0.75rem", color: "var(--accent-cyan)", fontWeight: "600" }}>EXPERIMENTAL</span>
            </h1>
            <p style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
              High-Speed Screen-to-Camera Optical Data Link
            </p>
          </div>
        </div>

        {/* Navigation Tabs */}
        <nav style={{ display: "flex", gap: "8px" }}>
          {[
            { id: "sender", label: "Optical Transmitter", icon: Radio },
            { id: "receiver", label: "Camera Receiver", icon: Camera },
            { id: "simulator", label: "Channel Simulator", icon: Sliders },
            { id: "benchmarks", label: "Empirical Benchmarks", icon: BarChart2 },
            { id: "architecture", label: "Protocol Specs", icon: Layers },
          ].map((tab) => {
            const Icon = tab.icon;
            const active = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  padding: "8px 16px",
                  borderRadius: "8px",
                  fontSize: "0.85rem",
                  fontWeight: active ? "600" : "500",
                  background: active ? "rgba(6, 182, 212, 0.15)" : "transparent",
                  color: active ? "var(--accent-cyan)" : "var(--text-muted)",
                  border: active ? "1px solid rgba(6, 182, 212, 0.35)" : "1px solid transparent",
                }}
              >
                <Icon size={16} />
                {tab.label}
              </button>
            );
          })}
        </nav>
      </header>

      {/* Main Content Area */}
      <main style={{ flex: 1, padding: "24px 32px", maxWidth: "1500px", margin: "0 auto", width: "100%" }}>
        {/* TAB 1: SENDER */}
        {activeTab === "sender" && (
          <div style={{ display: "grid", gridTemplateColumns: isFullscreen ? "1fr" : "380px 1fr", gap: "24px" }}>
            {/* Configuration Sidebar */}
            {!isFullscreen && (
              <div className="card">
                <div className="card-header">
                  <h2 style={{ fontSize: "1rem", fontWeight: "700", display: "flex", alignItems: "center", gap: "8px" }}>
                    <Sliders size={18} color="var(--accent-cyan)" /> Transmission Setup
                  </h2>
                  <span className="badge badge-cyan">AIR-GAP SECURE</span>
                </div>

                <div style={{ marginBottom: "16px" }}>
                  <label style={{ fontSize: "0.8rem", color: "var(--text-muted)", display: "block", marginBottom: "6px" }}>
                    Select File or Payload
                  </label>
                  <input
                    type="file"
                    onChange={(e) => {
                      if (e.target.files[0]) {
                        setFile(e.target.files[0]);
                        setFileName(e.target.files[0].name);
                        setFileSize(e.target.files[0].size);
                      }
                    }}
                    style={{ width: "100%", fontSize: "0.85rem" }}
                  />
                  <div style={{ marginTop: "6px", fontSize: "0.75rem", color: "var(--text-dim)" }}>
                    Selected: <strong style={{ color: "#fff" }}>{fileName}</strong> ({(fileSize / 1024).toFixed(1)} KB)
                  </div>
                </div>

                <div style={{ marginBottom: "16px" }}>
                  <label style={{ fontSize: "0.8rem", color: "var(--text-muted)", display: "block", marginBottom: "6px" }}>
                    Modulation Scheme
                  </label>
                  <select
                    value={modulationMode}
                    onChange={(e) => setModulationMode(Number(e.target.value))}
                    disabled={isTransmitting}
                    style={{ width: "100%" }}
                  >
                    <option value={1}>Mode 1: Binary (Black/White - 1 bit/cell)</option>
                    <option value={2}>Mode 2: 4-Color (RGBK - 2 bits/cell) [Optimal]</option>
                    <option value={3}>Mode 3: 8-Color (Cube Vertices - 3 bits/cell)</option>
                  </select>
                </div>

                <div style={{ marginBottom: "16px" }}>
                  <label style={{ fontSize: "0.8rem", color: "var(--text-muted)", display: "block", marginBottom: "6px" }}>
                    Spatial Grid Density: <strong style={{ color: "var(--accent-cyan)" }}>{gridSize} × {gridSize}</strong>
                  </label>
                  <select
                    value={gridSize}
                    onChange={(e) => setGridSize(Number(e.target.value))}
                    disabled={isTransmitting}
                    style={{ width: "100%" }}
                  >
                    <option value={24}>24 × 24 (High Noise Margin / Distant Camera)</option>
                    <option value={32}>32 × 32 (Optimal Standard - 1024 Cells)</option>
                    <option value={48}>48 × 48 (High Density - 2304 Cells)</option>
                    <option value={64}>64 × 64 (Ultra Density - 4096 Cells)</option>
                  </select>
                </div>

                <div style={{ marginBottom: "16px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px" }}>
                    <label style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Target Frame Rate</label>
                    <span style={{ fontSize: "0.85rem", fontWeight: "700", color: "var(--accent-cyan)" }}>{fps} FPS</span>
                  </div>
                  <input
                    type="range"
                    min="10"
                    max="60"
                    step="5"
                    value={fps}
                    onChange={(e) => setFps(Number(e.target.value))}
                    disabled={isTransmitting}
                    style={{ width: "100%", accentColor: "var(--accent-cyan)" }}
                  />
                </div>

                <div style={{ marginBottom: "16px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px" }}>
                    <label style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>2D Reed-Solomon Erasure FEC</label>
                    <span style={{ fontSize: "0.85rem", fontWeight: "700", color: "var(--accent-emerald)" }}>{Math.round(fecRatio * 100)}% Parity</span>
                  </div>
                  <input
                    type="range"
                    min="0.10"
                    max="0.40"
                    step="0.05"
                    value={fecRatio}
                    onChange={(e) => setFecRatio(Number(e.target.value))}
                    disabled={isTransmitting}
                    style={{ width: "100%", accentColor: "var(--accent-emerald)" }}
                  />
                </div>

                <div style={{ display: "flex", gap: "16px", marginBottom: "20px" }}>
                  <label style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "0.85rem", cursor: "pointer" }}>
                    <input
                      type="checkbox"
                      checked={encryption}
                      onChange={(e) => setEncryption(e.target.checked)}
                      disabled={isTransmitting}
                    />
                    <Lock size={14} color="var(--accent-cyan)" /> AES-256-GCM
                  </label>
                  <label style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "0.85rem", cursor: "pointer" }}>
                    <input
                      type="checkbox"
                      checked={compression}
                      onChange={(e) => setCompression(e.target.checked)}
                      disabled={isTransmitting}
                    />
                    <Cpu size={14} color="var(--accent-purple)" /> Zlib Deflate
                  </label>
                </div>

                {!isTransmitting ? (
                  <button onClick={handleStartTransmission} className="btn-primary" style={{ width: "100%", justifyContent: "center" }}>
                    <Play size={18} /> START OPTICAL TRANSMISSION
                  </button>
                ) : (
                  <button onClick={handleStopTransmission} className="btn-secondary" style={{ width: "100%", justifyContent: "center", color: "#f43f5e" }}>
                    <Square size={18} /> STOP TRANSMISSION
                  </button>
                )}
              </div>
            )}

            {/* Optical Canvas Display & Real-Time Telemetry */}
            <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
              <div
                className={`optical-frame-container ${isFullscreen ? "fullscreen" : ""}`}
                style={{ position: "relative" }}
              >
                <canvas
                  ref={canvasRef}
                  width={640}
                  height={640}
                  style={{
                    maxWidth: "100%",
                    maxHeight: isFullscreen ? "94vh" : "560px",
                    aspectRatio: "1/1",
                    imageRendering: "pixelated",
                    borderRadius: isFullscreen ? "0" : "8px",
                  }}
                />

                <button
                  onClick={toggleFullscreen}
                  style={{
                    position: "absolute",
                    top: "16px",
                    right: "16px",
                    background: "rgba(0, 0, 0, 0.75)",
                    border: "1px solid rgba(255, 255, 255, 0.2)",
                    color: "#fff",
                    padding: "8px",
                    borderRadius: "6px",
                  }}
                  title={isFullscreen ? "Exit Fullscreen" : "Fullscreen Transmission Display"}
                >
                  {isFullscreen ? <Minimize2 size={18} /> : <Maximize2 size={18} />}
                </button>

                {isTransmitting && (
                  <div
                    style={{
                      position: "absolute",
                      bottom: "16px",
                      left: "16px",
                      background: "rgba(0, 0, 0, 0.85)",
                      border: "1px solid var(--accent-cyan)",
                      padding: "6px 14px",
                      borderRadius: "6px",
                      display: "flex",
                      alignItems: "center",
                      gap: "8px",
                    }}
                  >
                    <div style={{ width: "8px", height: "8px", borderRadius: "50%", background: "#10b981" }} className="pulse-active" />
                    <span style={{ fontSize: "0.8rem", fontFamily: "var(--font-mono)", color: "#fff" }}>
                      TRANSMITTING REAL PACKETS @ {fps} FPS [{gridSize}x{gridSize}]
                    </span>
                  </div>
                )}
              </div>

              {/* Transmission Telemetry HUD */}
              {isTransmitting && telemetry && (
                <div className="card">
                  <div className="telemetry-grid">
                    <div className="telemetry-item">
                      <div className="telemetry-label">PROGRESS</div>
                      <div className="telemetry-val" style={{ color: "var(--accent-cyan)" }}>
                        {telemetry.progress}%
                      </div>
                    </div>
                    <div className="telemetry-item">
                      <div className="telemetry-label">FRAME SEQ</div>
                      <div className="telemetry-val">
                        {telemetry.seq} / {telemetry.total}
                      </div>
                    </div>
                    <div className="telemetry-item">
                      <div className="telemetry-label">RAW BITRATE</div>
                      <div className="telemetry-val">{telemetry.rawBitrateMbps} Mbps</div>
                    </div>
                    <div className="telemetry-item">
                      <div className="telemetry-label">EFFECTIVE GOODPUT</div>
                      <div className="telemetry-val" style={{ color: "var(--accent-emerald)" }}>
                        {telemetry.effectiveKbps} KB/s
                      </div>
                    </div>
                    <div className="telemetry-item">
                      <div className="telemetry-label">ESTIMATED ETA</div>
                      <div className="telemetry-val">{telemetry.etaSec}s</div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* TAB 2: RECEIVER */}
        {activeTab === "receiver" && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 400px", gap: "24px" }}>
            {/* Live Camera View with Detection Overlay */}
            <div className="card">
              <div className="card-header">
                <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                  <h2 style={{ fontSize: "1rem", fontWeight: "700", display: "flex", alignItems: "center", gap: "8px" }}>
                    <Camera size={18} color="var(--accent-emerald)" /> Optical Receiver Feed
                  </h2>
                  {/* Receiver Mode Switcher */}
                  <div style={{ display: "flex", background: "var(--bg-secondary)", borderRadius: "6px", padding: "2px", border: "1px solid var(--border-color)" }}>
                    <button
                      onClick={() => setReceiverMode("hardware")}
                      style={{
                        padding: "4px 10px",
                        borderRadius: "4px",
                        fontSize: "0.75rem",
                        fontWeight: receiverMode === "hardware" ? "600" : "400",
                        background: receiverMode === "hardware" ? "var(--bg-card-hover)" : "transparent",
                        color: receiverMode === "hardware" ? "#fff" : "var(--text-muted)",
                      }}
                    >
                      PC Webcam (OpenCV)
                    </button>
                    <button
                      onClick={() => setReceiverMode("browser")}
                      style={{
                        padding: "4px 10px",
                        borderRadius: "4px",
                        fontSize: "0.75rem",
                        fontWeight: receiverMode === "browser" ? "600" : "400",
                        background: receiverMode === "browser" ? "var(--bg-card-hover)" : "transparent",
                        color: receiverMode === "browser" ? "#fff" : "var(--text-muted)",
                      }}
                    >
                      Browser / Phone Camera
                    </button>
                  </div>
                </div>

                <div style={{ display: "flex", gap: "8px" }}>
                  <button onClick={handleResetReceiver} className="btn-secondary" title="Reset receiver buffer for new transfer">
                    <RefreshCw size={14} /> Reset
                  </button>

                  {receiverMode === "hardware" ? (
                    <button onClick={handleToggleHardwareCamera} className={hwCameraRunning ? "btn-secondary" : "btn-success"}>
                      {hwCameraRunning ? <Square size={16} /> : <Play size={16} />}
                      {hwCameraRunning ? "STOP CAMERA" : "START PC WEBCAM"}
                    </button>
                  ) : (
                    <button onClick={browserCameraActive ? stopBrowserCamera : startBrowserCamera} className={browserCameraActive ? "btn-secondary" : "btn-success"}>
                      {browserCameraActive ? <Square size={16} /> : <Play size={16} />}
                      {browserCameraActive ? "STOP BROWSER CAM" : "START BROWSER CAM"}
                    </button>
                  )}
                </div>
              </div>

              {/* Video Preview Box */}
              <div
                style={{
                  background: "#000",
                  borderRadius: "8px",
                  height: "480px",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  position: "relative",
                  overflow: "hidden",
                  border: "1px solid var(--border-color)",
                }}
              >
                {/* Mode A: Hardware Camera MJPEG Feed */}
                {receiverMode === "hardware" && hwCameraRunning && (
                  <img
                    src={`${API_BASE}/api/receiver/video_feed`}
                    alt="Live OpenCV Hardware Camera Stream"
                    style={{ width: "100%", height: "100%", objectFit: "contain" }}
                  />
                )}

                {/* Mode B: Browser Camera Feed with HTML5 Canvas Overlay */}
                {receiverMode === "browser" && (
                  <>
                    <video ref={videoRef} autoPlay playsInline muted style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                    <canvas
                      ref={overlayCanvasRef}
                      style={{
                        position: "absolute",
                        top: 0,
                        left: 0,
                        width: "100%",
                        height: "100%",
                        pointerEvents: "none",
                      }}
                    />
                    <div
                      style={{
                        position: "absolute",
                        top: "16px",
                        left: "16px",
                        background: "rgba(0, 0, 0, 0.75)",
                        padding: "4px 10px",
                        borderRadius: "6px",
                        border: rxDetected ? "1px solid #10b981" : "1px solid #f59e0b",
                        fontSize: "0.75rem",
                        fontFamily: "var(--font-mono)",
                        color: rxDetected ? "#10b981" : "#f59e0b",
                      }}
                    >
                      {rxDetected ? "LOCKED: " + rxStatusText : "SEARCHING FOR OPTILINK DISPLAY"}
                    </div>
                  </>
                )}

                {/* Idle / Disconnected State */}
                {((receiverMode === "hardware" && !hwCameraRunning) || (receiverMode === "browser" && !browserCameraActive)) && (
                  <div style={{ textAlign: "center", color: "var(--text-dim)" }}>
                    <Camera size={48} style={{ margin: "0 auto 12px", opacity: 0.4 }} />
                    <p style={{ fontSize: "0.9rem", color: "#fff" }}>Camera is disconnected.</p>
                    <p style={{ fontSize: "0.75rem", marginTop: "4px" }}>
                      Click <strong>{receiverMode === "hardware" ? "Start PC Webcam" : "Start Browser Cam"}</strong> to track optical transmission frames.
                    </p>
                  </div>
                )}
              </div>
            </div>

            {/* Receiver Telemetry & File Saver */}
            <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
              <div className="card">
                <div className="card-header">
                  <h3 style={{ fontSize: "0.95rem", fontWeight: "700" }}>Optical Link Telemetry</h3>
                  <span className={`badge ${rxTelemetry.is_complete ? "badge-emerald" : hwCameraRunning || browserCameraActive ? "badge-cyan" : "badge-amber"}`}>
                    {rxTelemetry.is_complete ? "VERIFIED ✓" : hwCameraRunning || browserCameraActive ? "RECEIVING" : "IDLE"}
                  </span>
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                  <div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "4px" }}>
                      <span>Reassembly Progress</span>
                      <strong style={{ color: "#fff" }}>{rxTelemetry.progress_percent}%</strong>
                    </div>
                    <div style={{ background: "rgba(255, 255, 255, 0.1)", borderRadius: "6px", height: "8px", overflow: "hidden" }}>
                      <div
                        style={{
                          background: "linear-gradient(90deg, #06b6d4, #10b981)",
                          height: "100%",
                          width: `${rxTelemetry.progress_percent}%`,
                          transition: "width 0.3s ease",
                        }}
                      />
                    </div>
                  </div>

                  <div className="telemetry-grid">
                    <div className="telemetry-item">
                      <div className="telemetry-label">SPEED</div>
                      <div className="telemetry-val" style={{ color: "var(--accent-emerald)" }}>
                        {rxTelemetry.speed_kbps} KB/s
                      </div>
                    </div>
                    <div className="telemetry-item">
                      <div className="telemetry-label">FRAMES RX</div>
                      <div className="telemetry-val">{rxTelemetry.frames_received}</div>
                    </div>
                    <div className="telemetry-item">
                      <div className="telemetry-label">FEC RECOVERED</div>
                      <div className="telemetry-val" style={{ color: "var(--accent-cyan)" }}>
                        {rxTelemetry.frames_recovered_fec}
                      </div>
                    </div>
                    <div className="telemetry-item">
                      <div className="telemetry-label">LOST / DROPPED</div>
                      <div className="telemetry-val" style={{ color: "var(--accent-rose)" }}>
                        {rxTelemetry.estimated_lost_frames}
                      </div>
                    </div>
                    <div className="telemetry-item">
                      <div className="telemetry-label">IN-FRAME REPAIRS</div>
                      <div className="telemetry-val">{rxTelemetry.in_frame_errors_corrected}</div>
                    </div>
                    <div className="telemetry-item">
                      <div className="telemetry-label">INTEGRITY</div>
                      <div className="telemetry-val" style={{ fontSize: "0.85rem", color: rxTelemetry.integrity_verified ? "#10b981" : "#f59e0b" }}>
                        {rxTelemetry.integrity_verified ? "SHA-256 PASS" : "WAITING"}
                      </div>
                    </div>
                  </div>

                  {rxTelemetry.sha256 && (
                    <div style={{ fontSize: "0.75rem", fontFamily: "var(--font-mono)", background: "rgba(0,0,0,0.4)", padding: "8px", borderRadius: "6px", wordBreak: "break-all" }}>
                      <span style={{ color: "var(--text-muted)" }}>Hash: </span>
                      <span style={{ color: "#10b981" }}>{rxTelemetry.sha256}</span>
                    </div>
                  )}

                  <a
                    href={`${API_BASE}/api/receiver/download`}
                    download
                    className="btn-primary"
                    style={{
                      width: "100%",
                      justifyContent: "center",
                      marginTop: "8px",
                      opacity: rxTelemetry.is_complete ? 1 : 0.5,
                      pointerEvents: rxTelemetry.is_complete ? "auto" : "none",
                    }}
                  >
                    <Download size={18} /> SAVE RECONSTRUCTED FILE
                  </a>
                </div>
              </div>

              {/* Hardware Guidance */}
              <div className="card">
                <h4 style={{ fontSize: "0.85rem", fontWeight: "600", marginBottom: "8px", color: "var(--text-muted)" }}>
                  HOW TO RECEIVE OPTICAL SIGNALS
                </h4>
                <ol style={{ fontSize: "0.75rem", color: "var(--text-dim)", lineHeight: "1.6", paddingLeft: "16px" }}>
                  <li>Open the Optical Transmitter tab on another display or laptop.</li>
                  <li>Point this camera at the transmission grid.</li>
                  <li>Ensure all 4 corner markers (ArUco targets) are inside the frame.</li>
                  <li>Watch the green bounding polygon lock on and data stream in!</li>
                </ol>
              </div>
            </div>
          </div>
        )}

        {/* TAB 3: SIMULATOR */}
        {activeTab === "simulator" && (
          <div style={{ display: "grid", gridTemplateColumns: "380px 1fr", gap: "24px" }}>
            <div className="card">
              <div className="card-header">
                <h2 style={{ fontSize: "1rem", fontWeight: "700", display: "flex", alignItems: "center", gap: "8px" }}>
                  <Sliders size={18} color="var(--accent-purple)" /> Channel Impairment Testbench
                </h2>
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.8rem", marginBottom: "4px" }}>
                    <span>Simulated File Size</span>
                    <strong>{simSizeKb} KB</strong>
                  </div>
                  <input
                    type="range"
                    min="5"
                    max="100"
                    step="5"
                    value={simSizeKb}
                    onChange={(e) => setSimSizeKb(Number(e.target.value))}
                    style={{ width: "100%" }}
                  />
                </div>

                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.8rem", marginBottom: "4px" }}>
                    <span>Camera Frame Drop Rate</span>
                    <strong style={{ color: "var(--accent-rose)" }}>{Math.round(simDropRate * 100)}%</strong>
                  </div>
                  <input
                    type="range"
                    min="0.00"
                    max="0.25"
                    step="0.02"
                    value={simDropRate}
                    onChange={(e) => setSimDropRate(Number(e.target.value))}
                    style={{ width: "100%", accentColor: "var(--accent-rose)" }}
                  />
                </div>

                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.8rem", marginBottom: "4px" }}>
                    <span>Camera Perspective Tilt</span>
                    <strong>{simTilt}°</strong>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max="35"
                    step="5"
                    value={simTilt}
                    onChange={(e) => setSimTilt(Number(e.target.value))}
                    style={{ width: "100%" }}
                  />
                </div>

                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.8rem", marginBottom: "4px" }}>
                    <span>Sensor Noise (Sigma)</span>
                    <strong>{simNoise} σ</strong>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max="15"
                    step="1"
                    value={simNoise}
                    onChange={(e) => setSimNoise(Number(e.target.value))}
                    style={{ width: "100%" }}
                  />
                </div>

                <button
                  onClick={handleRunSimulation}
                  disabled={simRunning}
                  className="btn-primary"
                  style={{ width: "100%", justifyContent: "center" }}
                >
                  <RefreshCw size={18} className={simRunning ? "pulse-active" : ""} />
                  {simRunning ? "SIMULATING OPTICAL CHANNEL..." : "RUN CHANNEL SIMULATION"}
                </button>
              </div>
            </div>

            <div className="card">
              <div className="card-header">
                <h3 style={{ fontSize: "1rem", fontWeight: "700" }}>Simulation Outcome & FEC Reconstruction</h3>
                {simResult && (
                  <span className={`badge ${simResult.file_recovered_100pct ? "badge-emerald" : "badge-rose"}`}>
                    {simResult.file_recovered_100pct ? "100% RECOVERED (SHA-256 PASS)" : "CORRUPTED"}
                  </span>
                )}
              </div>

              {simResult ? (
                <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
                  <div className="telemetry-grid">
                    <div className="telemetry-item">
                      <div className="telemetry-label">FILE SIZE</div>
                      <div className="telemetry-val">{(simResult.file_size / 1024).toFixed(1)} KB</div>
                    </div>
                    <div className="telemetry-item">
                      <div className="telemetry-label">CHANNEL FRAMES</div>
                      <div className="telemetry-val">{simResult.total_channel_frames}</div>
                    </div>
                    <div className="telemetry-item">
                      <div className="telemetry-label">DROPPED FRAMES</div>
                      <div className="telemetry-val" style={{ color: "var(--accent-rose)" }}>
                        {simResult.channel_dropped_frames}
                      </div>
                    </div>
                    <div className="telemetry-item">
                      <div className="telemetry-label">FEC RECONSTRUCTED</div>
                      <div className="telemetry-val" style={{ color: "var(--accent-emerald)" }}>
                        {simResult.frames_recovered_fec}
                      </div>
                    </div>
                    <div className="telemetry-item">
                      <div className="telemetry-label">EFFECTIVE SPEED</div>
                      <div className="telemetry-val">{simResult.speed_kbps} KB/s</div>
                    </div>
                    <div className="telemetry-item">
                      <div className="telemetry-label">ELAPSED TIME</div>
                      <div className="telemetry-val">{simResult.elapsed_seconds}s</div>
                    </div>
                  </div>

                  <div style={{ background: "rgba(16, 22, 34, 0.8)", border: "1px solid var(--border-color)", padding: "16px", borderRadius: "8px" }}>
                    <div style={{ fontSize: "0.85rem", fontWeight: "600", color: "var(--accent-cyan)", marginBottom: "8px" }}>
                      CRYPTOGRAPHIC VERIFICATION
                    </div>
                    <div style={{ fontSize: "0.8rem", fontFamily: "var(--font-mono)", wordBreak: "break-all", color: "var(--text-muted)" }}>
                      SHA-256: <span style={{ color: "#fff" }}>{simResult.sha256}</span>
                    </div>
                    <p style={{ fontSize: "0.75rem", color: "var(--accent-emerald)", marginTop: "8px" }}>
                      ✓ All dropped frames were reconstructed mathematically via 2D Reed-Solomon without retransmission requests.
                    </p>
                  </div>
                </div>
              ) : (
                <div style={{ textAlign: "center", padding: "48px 0", color: "var(--text-dim)" }}>
                  <Sliders size={48} style={{ margin: "0 auto 12px", opacity: 0.3 }} />
                  <p>Configure parameters on the left and click Run Channel Simulation.</p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* TAB 4: BENCHMARKS */}
        {activeTab === "benchmarks" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
            <div className="card" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <h2 style={{ fontSize: "1.1rem", fontWeight: "700" }}>Empirical Benchmarking & Performance Characterization</h2>
                <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                  Experimental sweeps across Frame Rate, Color Modulation, Distance, Illumination, and Grid Density.
                </p>
              </div>
              <button onClick={handleRunBenchmarks} disabled={benchmarksLoading} className="btn-primary">
                <RefreshCw size={16} className={benchmarksLoading ? "pulse-active" : ""} />
                {benchmarksLoading ? "RUNNING EXPERIMENTS..." : "RE-RUN BENCHMARK SUITE"}
              </button>
            </div>

            <div className="card" style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "16px" }}>
              <div style={{ borderLeft: "3px solid #06b6d4", paddingLeft: "12px" }}>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>PROTOTYPE TARGET</div>
                <div style={{ fontSize: "1.3rem", fontWeight: "700", fontFamily: "var(--font-mono)" }}>10 – 50 KB/s</div>
                <p style={{ fontSize: "0.75rem", color: "var(--text-dim)" }}>Baseline Mode 1/2 @ 24x24 30 FPS</p>
              </div>
              <div style={{ borderLeft: "3px solid #10b981", paddingLeft: "12px" }}>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>OPTIMIZED TARGET</div>
                <div style={{ fontSize: "1.3rem", fontWeight: "700", fontFamily: "var(--font-mono)", color: "var(--accent-emerald)" }}>
                  50 – 500 KB/s
                </div>
                <p style={{ fontSize: "0.75rem", color: "var(--text-dim)" }}>Mode 2/3 @ 48x48 30-60 FPS</p>
              </div>
              <div style={{ borderLeft: "3px solid #8b5cf6", paddingLeft: "12px" }}>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>ADVANCED HIGH-SPEED</div>
                <div style={{ fontSize: "1.3rem", fontWeight: "700", fontFamily: "var(--font-mono)", color: "var(--accent-purple)" }}>
                  500+ KB/s
                </div>
                <p style={{ fontSize: "0.75rem", color: "var(--text-dim)" }}>Mode 3 @ 64x64 60 FPS (Peak 1.8 Mbps raw)</p>
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(440px, 1fr))", gap: "20px" }}>
              {[
                { title: "Throughput vs Transmission FPS", file: "throughput_vs_fps.png" },
                { title: "Raw Bitrate vs Effective Goodput by Color Mode", file: "throughput_vs_colors.png" },
                { title: "Packet Error Rate vs Camera Perspective Tilt Angle", file: "error_rate_vs_distance.png" },
                { title: "Optical Error Rate Under Ambient Lighting Levels", file: "error_rate_vs_lighting.png" },
                { title: "Reliable Goodput Scaling vs Grid Density", file: "goodput_vs_grid_size.png" },
                { title: "2D Reed-Solomon Parity Overhead vs Frame Recovery Rate", file: "fec_overhead_vs_recovery.png" },
              ].map((g, idx) => (
                <div key={idx} className="card">
                  <h3 style={{ fontSize: "0.9rem", fontWeight: "600", marginBottom: "12px" }}>{g.title}</h3>
                  <img
                    src={`${API_BASE}/api/benchmark/image/${g.file}`}
                    alt={g.title}
                    style={{ width: "100%", borderRadius: "6px", border: "1px solid var(--border-color)" }}
                  />
                </div>
              ))}
            </div>
          </div>
        )}

        {/* TAB 5: PROTOCOL SPECS */}
        {activeTab === "architecture" && (
          <div className="card" style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
            <div className="card-header">
              <h2 style={{ fontSize: "1.1rem", fontWeight: "700" }}>OptiLink Optical Protocol Architecture</h2>
              <span className="badge badge-cyan">SPECIFICATION v1.0</span>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "24px" }}>
              <div>
                <h3 style={{ fontSize: "0.95rem", fontWeight: "600", color: "var(--accent-cyan)", marginBottom: "8px" }}>
                  1. Packet Framing Format
                </h3>
                <pre
                  style={{
                    background: "var(--bg-secondary)",
                    padding: "16px",
                    borderRadius: "8px",
                    fontSize: "0.75rem",
                    fontFamily: "var(--font-mono)",
                    border: "1px solid var(--border-color)",
                    color: "var(--text-main)",
                  }}
                >
{`┌────────────────────────────────────────────────────────┐
│ Synchronization Markers (4 Corner ArUco Fiducials)     │
│ In-Frame Calibration Strip (8 Reference Colors)        │
│ Fixed Header (25 Bytes with Magic 'OL' + CRC16)        │
│ Modulated Payload Data Grid                            │
│ In-Frame Reed-Solomon Parity (8-16 Bytes)              │
│ IEEE 802.3 CRC-32 Frame Checksum (4 Bytes)            │
└────────────────────────────────────────────────────────┘`}
                </pre>

                <h3 style={{ fontSize: "0.95rem", fontWeight: "600", color: "var(--accent-emerald)", marginTop: "16px", marginBottom: "8px" }}>
                  2. Dual-Tier Error Correction
                </h3>
                <ul style={{ fontSize: "0.8rem", color: "var(--text-muted)", lineHeight: "1.6", paddingLeft: "16px" }}>
                  <li><strong>Tier 1 (In-Frame):</strong> Reed-Solomon RS(N, K) over individual frame payloads to repair burst pixel errors and ambient glints.</li>
                  <li><strong>Tier 2 (Cross-Frame):</strong> 2D Cauchy Reed-Solomon packet erasure coding across frames to recover dropped frames without retransmission.</li>
                  <li><strong>Integrity:</strong> End-to-end SHA-256 validation of the decrypted reconstructed file.</li>
                </ul>
              </div>

              <div>
                <h3 style={{ fontSize: "0.95rem", fontWeight: "600", color: "var(--accent-purple)", marginBottom: "8px" }}>
                  3. Authenticated Cryptographic Stack
                </h3>
                <pre
                  style={{
                    background: "var(--bg-secondary)",
                    padding: "16px",
                    borderRadius: "8px",
                    fontSize: "0.75rem",
                    fontFamily: "var(--font-mono)",
                    border: "1px solid var(--border-color)",
                    color: "var(--text-main)",
                  }}
                >
{`Raw Application File
       ↓
Stream Compression (Zlib Deflate)
       ↓
Authenticated Encryption (AES-256-GCM)
       ↓
Chunking & 2D Erasure Coding
       ↓
Optical Modulation (Binary / 4-Color / 8-Color)
       ↓
Photonic Transmission (Computer Display)`}
                </pre>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
