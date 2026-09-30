# OptiLink Optical Framing Protocol Specification v1.0

## 1. Frame Structure

Every optical frame displayed by OptiLink consists of 5 logical segments:

```text
┌──────────────────────────────────────────────────────────────┐
│ [1] Optical Synchronization Markers (ArUco Fiducials 0,1,2,3) │
│ [2] Dynamic Color Calibration Strip (8 Reference Colors)     │
│ [3] Protocol Header (25 Bytes Fixed Length)                  │
│ [4] Modulated Payload Data (L Bytes)                         │
│ [5] In-Frame Reed-Solomon Parity + CRC-32 (4 Bytes)          │
└──────────────────────────────────────────────────────────────┘
```

---

## 2. Fixed Header Definition (25 Bytes)

All fields are transmitted in Network Byte Order (Big-Endian):

| Offset | Field Name | Type | Size (Bytes) | Description |
|---|---|---|---|---|
| `0x00` | Magic | `char[2]` | 2 | Protocol identifier: ASCII `"OL"` (`0x4F, 0x4C`) |
| `0x02` | Protocol Version | `uint8` | 1 | Currently `0x01` |
| `0x03` | Frame Type | `uint8` | 1 | `0` = Announce, `1` = Data, `2` = FEC Parity, `3` = EOT |
| `0x04` | Session ID | `uint32` | 4 | Unique 32-bit transfer session identifier |
| `0x08` | Sequence Number | `uint32` | 4 | Sequential packet index ($0 \le \text{seq} < \text{total}$) |
| `0x0C` | Total Source Frames | `uint32` | 4 | Total source chunks ($K$) |
| `0x10` | Payload Length | `uint16` | 2 | Byte length of payload within this frame ($0 \dots 2048$) |
| `0x12` | Modulation Mode | `uint8` | 1 | `1` = Binary, `2` = 4-Color, `3` = 8-Color, `4` = Adaptive |
| `0x13` | Grid Rows | `uint8` | 1 | Grid vertical resolution (e.g. 24, 32, 48, 64) |
| `0x14` | Grid Columns | `uint8` | 1 | Grid horizontal resolution (e.g. 24, 32, 48, 64) |
| `0x15` | FEC Scheme | `uint8` | 1 | `0` = None, `1` = In-Frame RS, `2` = Erasure, `3` = Hybrid |
| `0x16` | FEC Parity Length | `uint8` | 1 | In-frame Reed-Solomon parity byte count (default: 8) |
| `0x17` | Header CRC16 | `uint16` | 2 | CRC-16-CCITT covering bytes `0x00` through `0x16` |

Total header size: **25 Bytes**.

---

## 3. Frame Types

### 3.1 Type 0x00: Session Announce
Carries UTF-8 encoded JSON session metadata:
- `session_id`: 32-bit integer
- `filename`: Original file name
- `file_size`: Total byte size
- `file_sha256`: Hexadecimal SHA-256 digest
- `chunk_size`: Byte capacity per frame
- `total_source_chunks`: Number of source data frames ($K$)
- `total_parity_chunks`: Number of cross-frame parity frames ($M$)
- `encryption_algo`: `"AES-GCM-256"`
- `encryption_nonce`: 12-byte hex nonce
- `encryption_tag`: 16-byte hex tag
- `encryption_key`: 32-byte hex symmetric session key

The Announce frame is transmitted multiple times at session start and interleaved periodically.

### 3.2 Type 0x01: Source Data Frame
Carries sequential encrypted file chunks with sequence numbers $0 \le \text{seq} < K$.

### 3.3 Type 0x02: Cross-Frame Parity Frame
Carries 2D Reed-Solomon erasure parity packets with sequence numbers $K \le \text{seq} < K + M$. Any $K$ packets out of $K + M$ received is sufficient for complete file reconstruction.

### 3.4 Type 0x03: End of Transmission (EOT)
Signals the conclusion of transmission.

---

## 4. Visual Modulation Specification

### Mode 1 — Binary (1 bit/cell)
- `0` = Black `(0, 0, 0)`
- `1` = White `(255, 255, 255)`
- Maximum noise margin; highly resilient to severe glare, low-end sensors, and long distance.

### Mode 2 — 4-Color (2 bits/cell)
- `00` = Black `(0, 0, 0)`
- `01` = Red `(255, 0, 0)`
- `10` = Green `(0, 255, 0)`
- `11` = Blue `(0, 0, 255)`
- Balances high noise margin with double the data density of binary mode.

### Mode 3 — 8-Color (3 bits/cell)
- Corners of the 3D RGB color cube:
  - `000` = Black `(0, 0, 0)`
  - `001` = Blue `(0, 0, 255)`
  - `010` = Green `(0, 255, 0)`
  - `011` = Cyan `(0, 255, 255)`
  - `100` = Red `(255, 0, 0)`
  - `101` = Magenta `(255, 0, 255)`
  - `110` = Yellow `(255, 255, 0)`
  - `111` = White `(255, 255, 255)`
- Yields highest data density (3 bits per cell) under calibrated conditions.

---

## 5. Optical Calibration Strip

A 1-cell tall strip situated at Row 0 between columns $k$ and $\text{cols} - k$ sequentially displays the 8 reference colors. The receiver continuously computes:

$$\Delta E = \sqrt{0.30(R - R_{\text{ref}})^2 + 0.59(G - G_{\text{ref}})^2 + 0.11(B - B_{\text{ref}})^2}$$

This neutralizes camera auto-exposure, ambient color temperature shifts, and display gamma differences.
