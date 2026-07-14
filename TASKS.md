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

---

## Future Tasks

### P7: Advanced Signal Processing
- [ ] Real-time FFT visualization
- [ ] Adaptive threshold calibration (ML-based)
- [ ] Noise cancellation (notch filter at 50Hz/60Hz)
- [ ] Artifact rejection (eye movement, muscle noise)
- [ ] Multi-sensor fusion (accelerometer + EEG)

### P8: Enhanced Remote Operation
- [ ] ESP-NOW peer-to-peer (sub-10ms latency)
- [ ] Video feed integration (ESP32-CAM)
- [ ] Haptic feedback (vibration motor in glove)
- [ ] Multi-robot control (switch between robots)
- [ ] Secure WebSocket (WSS) with authentication

### P9: ML Training Pipeline
- [ ] Python data analysis toolkit (tools/analyze.py)
- [ ] Feature extraction from CSV logs
- [ ] TensorFlow Lite model training
- [ ] On-device inference (ESP32-S3)
- [ ] Real-time mental state classification
- [ ] Personalized gesture recognition

### P10: Humanoid Integration
- [ ] ROS2 integration (robot operating system)
- [ ] Inverse kinematics module
- [ ] Full arm control (shoulder + elbow + wrist)
- [ ] Walking gait generation from brain signals
- [ ] Bilateral teleoperation (force feedback)

### P11: Hardware Improvements
- [ ] Custom PCB design (KiCad)
- [ ] SMA connector for EEG shielding
- [ ] Battery management (LiPo + charging)
- [ ] Multiple EEG channels (OpenBCI daisy chain)
- [ ] Dry electrode array (no gel needed)

### P12: UI/UX
- [ ] Web-based dashboard (Chart.js visualization)
- [ ] Mobile app (ESP32 BLE + Flutter)
- [ ] Real-time EEG waveform display
- [ ] Training game (brain-controlled games)
- [ ] Calibration wizard

### P13: Production Readiness
- [ ] OTA firmware updates
- [ ] Factory reset + recovery mode
- [ ] Automated testing harness
- [ ] Power profiling and optimization
- [ ] CE/FCC certification preparation

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
- `P#` = phase number
