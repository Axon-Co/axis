# Axis Feature Roadmap & Tasks

## Phase 1: Core BCI (✅ Completed)

- [x] TGAM EEG packet parser (state machine)
- [x] UART EEG reader with FreeRTOS task
- [x] 5-channel servo controller (LEDC PWM)
- [x] Brain-to-servo command interpreter
- [x] Grip mode (attention → grip strength)
- [x] Calibrate mode (raw data monitor)

## Phase 2: Advanced Control (✅ Completed)

- [x] Finger selection mode (EEG bands → finger select)
- [x] Smooth motion with configurable speed
- [x] Blink detection with debounce
- [x] Adjustable brain mapping thresholds
- [x] Signal quality monitoring

## Phase 3: Persistence & Interface (✅ Completed)

- [x] NVS configuration storage (save/load/reset)
- [x] Interactive serial CLI (UART0 command interface)
- [x] WiFi Access Point + WebSocket server
- [x] Real-time EEG/servo data broadcast
- [x] Remote control via WebSocket JSON protocol

## Phase 4: Data & Training (✅ Completed)

- [x] SD card data logging (CSV format)
- [x] Full EEG power band logging
- [x] Servo position synchronized logging
- [x] Start/stop logging control

## Phase 5: Motion Quality (✅ Completed)

- [x] S-curve motion planner (sigmoid profile)
- [x] Configurable transition timing
- [x] Parallel multi-servo coordination
- [x] Smooth acceleration/deceleration

## Phase 6: Safety & Robustness (✅ Completed)

- [x] Signal loss detection → safe position
- [x] Poor quality timeout protection
- [x] Safety monitor FreeRTOS task
- [x] Enable/disable servo output

## Phase 7: Gestures (✅ Completed)

- [x] Pre-programmed gesture database (6 poses)
- [x] Multi-frame gesture sequences
- [x] Gesture playback with smooth transitions
- [x] CLI and WebSocket gesture trigger

## Phase 8: System Health & Diagnostics (✅ Completed)

- [x] System diagnostics module (uptime, packet stats, error counters)
- [x] Attention/meditation min/max/avg statistics
- [x] Heap monitoring (current + min free)
- [x] RGB LED status indicator (10 states: normal, warning, emergency, etc.)
- [x] Config validation before NVS save (range checks, constraint enforcement)
- [x] Semantic versioning (version.h with MAJOR.MINOR.PATCH)
- [x] `diag` CLI command for live diagnostics
- [x] `version` CLI command
- [x] `clear` CLI command to reset diagnostic counters
- [x] Enhanced `status` output with uptime, heap, signal quality %, EEG stats
- [x] LED auto-state machine (emergency → poor signal → calibrating → logging → normal)

## Phase 9: Control Mode Enhancements (✅ Completed)

- [x] SEQUENCE mode implemented (8 brain-controlled poses)
- [x] Attention threshold advancement (att ≥ 55 → next pose)
- [x] Meditation-based fine control within each pose
- [x] Blink gesture resets sequence to start
- [x] Config hold time (800ms) prevents accidental advancement

## Phase 10: Signal Processing Improvements

- [x] Moving average filter for attention/meditation
- [x] Adaptive threshold calibration
- [x] EEG band power ratios (alpha/beta, theta/gamma)
- [ ] Real-time FFT visualization on dashboard
- [ ] Notch filter (50Hz/60Hz power line noise cancellation)
- [ ] Artifact rejection (eye movement, muscle noise)
- [ ] Multi-sensor fusion (accelerometer data)
- [ ] Configurable filter chain (LPF, HPF, band-pass)

## Phase 11: Sequence Control Mode (🔄 In Progress)

- [x] 8 brain-controlled pose sequence
- [x] Attention-based step advancement (att ≥ 55)
- [x] Meditation-based fine motor control
- [x] Blink gesture resets sequence
- [ ] Multi-axis simultaneous movement
- [ ] Configurable sequence slots
- [ ] Save/load custom sequences from NVS

## Phase 12: Simulation & Development Tools (✅ Completed)

- [x] `tools/simulate_dashboard.py` — all-in-one EEG simulator + real-time web dashboard
- [x] Live Chart.js visualization (attention, meditation, blink, 8 EEG bands, servos)
- [x] WebSocket-free SSE streaming (no pip dependencies needed)
- [x] Mental state switching + auto-cycle from browser
- [x] Band power doughnut chart + time-series + statistics
- [x] `tools/analyze_server.py` — standalone CSV web analysis dashboard
- [x] Automatic CSV file detection, file selector
- [x] Statistical analysis (mean, median, min/max, std, percentiles, correlations)
- [x] Professional README.md with architecture, setup, tooling docs

## Phase 13: Connectivity & Remote Operation

- [ ] BLE (Bluetooth Low Energy) control — `nimble` stack
- [ ] ESP-NOW peer-to-peer (sub-10ms latency, no WiFi needed)
- [ ] Video feed integration (ESP32-CAM / OV2640)
- [ ] Haptic feedback (vibration motor PWM control)
- [ ] Multi-robot control (switch between robot profiles)
- [ ] Secure WebSocket (WSS) with authentication token
- [ ] MQTT broker support for IoT integration
- [ ] REST API for configuration (GET/PUT endpoints)

## Phase 14: On-Device Machine Learning

- [ ] TensorFlow Lite Micro model inference (ESP32-S3)
- [ ] Mental state classification (focused, relaxed, neutral)
- [ ] Personalized gesture recognition from EEG patterns
- [ ] On-device feature extraction (PSD, band ratios)
- [ ] Real-time blink pattern decoding (Morse code input)
- [ ] Model update via OTA / SD card

## Phase 15: Terminal UI & Dashboard (✅ Completed)

- [x] Live TUI dashboard over serial (`dash` command)
- [x] ANSI-rendered real-time display with bar graphs
- [x] EEG values + servo positions + system status all on one screen
- [x] `diag` command with comprehensive diagnostics
- [x] `version` + `clear` commands
- [x] Enhanced `status` with uptime, heap, signal quality

## Phase 16: Web Analysis Dashboard (✅ Completed)

- [x] `tools/analyze_server.py` — standalone web server for CSV log analysis
- [x] Automatic CSV file detection with file selector
- [x] Statistical analysis (mean, median, min, max, std, percentiles)
- [x] Time-series charts (Attention, Meditation, Blink over time)
- [x] Servo position tracking over time
- [x] EEG band power time-series (all 8 bands, log scale)
- [x] Band power distribution (doughnut chart)
- [x] EEG ratio calculation (α/β, θ/γ, Att/Med)
- [x] Correlation matrix between EEG metrics
- [x] Dark theme professional UI
- [x] Downsampled rendering for large CSV files (2000+ points)

## Phase 17: UI/UX & Dashboard

- [ ] Mobile app (ESP32 BLE + Flutter/React Native)
- [ ] Training game (brain-controlled Pong / Maze)
- [ ] Calibration wizard (step-by-step guided setup)
- [ ] Speech synthesis feedback (TTS status announcements)

## Phase 18: Hardware & System

- [ ] OTA firmware updates (esp_https_ota)
- [ ] Factory reset button (GPIO-triggered recovery mode)
- [ ] Battery monitoring (ADC voltage readout, low-battery alert)
- [ ] Power profiling and deep sleep mode
- [ ] Multiple EEG channel support (OpenBCI daisy chain via SPI)
- [ ] Custom PCB design (KiCad schematic + layout)
- [ ] SMA connector for EEG shielding

## Phase 19: Humanoid & Robotics Integration

- [ ] ROS2 micro-ROS integration (`uros` library)
- [ ] Inverse kinematics solver (2-link wrist + hand)
- [ ] Full arm control (shoulder + elbow + wrist servos)
- [ ] Walking gait generation from brain signals
- [ ] Bilateral teleoperation (force feedback via haptics)
- [ ] Joint angle trajectory recording + playback

## Phase 20: Developer Experience & Testing

- [ ] Automated testing harness (Unity test framework)
- [ ] CI pipeline (GitHub Actions: build + lint + test)
- [ ] Hardware-in-the-loop simulation
- [ ] Power profiling and optimization tools
- [ ] CE/FCC certification preparation guide
- [ ] Docker development environment
- [ ] Python CLI tool for offline config editing

## Phase 21: Production Readiness

- [ ] Manufacturing test firmware
- [ ] Serial number + device identity in NVS
- [ ] Secure boot + flash encryption
- [ ] Crash dump collection and analysis
- [ ] Watchdog timer for system-level recovery
- [ ] Syslog-style remote logging over UDP

---

## How to Contribute

1. Pick a task from any phase
2. Create a branch: `git checkout -b feature/<task-name>`
3. Implement the feature
4. Add documentation and update this file
5. Submit PR

## Legend

- `[x]` = implemented
- `[ ]` = planned / in progress
- `🔄` = partially done
- `P#` = phase number
