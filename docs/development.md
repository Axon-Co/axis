# EspBrain Development Guide

## Prerequisites

### Required Software
```bash
# ESP-IDF v5.x
git clone -b v5.1 --recursive https://github.com/espressif/esp-idf.git
cd esp-idf
./install.sh
source export.sh

# Or using PlatformIO (simpler):
pip install platformio
```

### Hardware
- ESP32 DevKit (ESP32-WROOM-32)
- NeuroSky TGAM Module + EEG headset
- 5x SG90/MG996R servo motors
- SD card module (SPI mode)
- 5V 2A power supply
- Jumper wires

## Build & Flash

### With ESP-IDF
```bash
cd espbrain
idf.py set-target esp32
idf.py menuconfig         # Configure as needed
idf.py build
idf.py -p /dev/ttyUSB0 flash monitor
```

### With PlatformIO
```bash
cd espbrain
pio run -t menuconfig     # Configure
pio run -t upload
pio device monitor
```

## Development Workflow

### 1. Code Structure
```
main/
├── main.c                # Entry point, init sequence, main loop
├── tgam_protocol.c/h     # TGAM ThinkGear packet parser
├── eeg_reader.c/h        # UART2 EEG data acquisition
├── servo_controller.c/h  # LEDC PWM servo control
├── command_interpreter.c/h  # Brain→action mapping
├── nvs_config.c/h        # Persistent configuration storage
├── serial_cli.c/h        # Interactive serial terminal
├── wifi_control.c/h      # WiFi AP + WebSocket server
├── data_logger.c/h       # SD card data logging
├── gesture_player.c/h    # Pre-programmed gestures
├── safety_monitor.c/h    # Watchdog & safety systems
├── motion_planner.c/h    # Smooth S-curve motion
└── CMakeLists.txt
```

### 2. Adding a New Module
1. Create `main/new_module.h` and `main/new_module.c`
2. Implement init, process, and getter/setter functions
3. Add `new_module.c` to `main/CMakeLists.txt`
4. Include and initialize in `main.c`

### 3. Code Conventions
- **Naming**: snake_case for functions/variables, UPPER_CASE for defines
- **Headers**: Use `#pragma once` include guard
- **Error handling**: Return `esp_err_t` where appropriate
- **Logging**: Use `ESP_LOGI`, `ESP_LOGW`, `ESP_LOGE` with module TAG
- **Thread safety**: Use mutexes for shared data
- **Configuration**: Store in `app_config_t`, persist via NVS

### 4. Testing
```bash
# Unit test (requires ESP32)
idf.py test

# Simulate EEG data for testing
python tools/simulate_eeg.py /dev/ttyUSB0
```

### 5. Debugging Tips
- Use `LOG_LOCAL_LEVEL` defines for verbose output
- Serial CLI `status` command shows all system parameters
- WiFi control page shows real-time graphs
- SD card logs can be analyzed with Python/matplotlib

## Performance Considerations

| Metric | Target | Measured |
|--------|--------|----------|
| EEG -> Servo latency | <50ms | ~20ms |
| Control loop rate | 50Hz | 50Hz |
| WiFi broadcast rate | 20Hz | 20Hz |
| SD card write rate | 10Hz | 10Hz |
| Max concurrent clients | 5 | 5 |

## Customization Points

### Adding New Control Modes
1. Add entry to `control_mode_t` enum
2. Implement `process_<mode>_mode()` in command_interpreter.c
3. Add mode switch in serial_cli and wifi_control

### Adding New Gestures
1. Add frame array in gesture_player.c
2. Add entry to `gesture_database` array
3. Gesture is automatically available via CLI and WiFi

### Adding New Config Parameters
1. Add field to `app_config_t` in nvs_config.h
2. Add save/load logic in nvs_config.c
3. Register in `config_keys` table in serial_cli.c

## Troubleshooting

### Build Errors
```
Error: "TGAM_UART_PORT" undeclared
  → Check tgam_protocol.h includes driver/uart.h
  → Verify UART_NUM_2 is available in sdkconfig

Error: undefined reference to `ledc_set_duty'
  → Check ESP-IDF framework is properly initialized
  → Verify CONFIG_LEDC_ENABLE=y in sdkconfig
```

### Runtime Errors
```
No EEG data (poor_signal > 0):
  → Check TGAM TX → ESP32 RX connection
  → Verify baud rate (57600)
  → Check sensor placement on forehead

Servos not moving:
  → Verify 5V power supply (not from ESP32 3.3V)
  → Check GPIO pin numbers in servo_configs
  → Verify PWM frequency: 50Hz
```

## Remote Development

### Using VS Code + PlatformIO
```json
// .vscode/settings.json
{
    "platformio-ide.activateOnlyOnPlatformIOProject": true
}
```

### Docker Development
```bash
docker run -it --rm \
    -v $(pwd):/project \
    -v /dev/ttyUSB0:/dev/ttyUSB0 \
    --privileged \
    espressif/idf:v5.1
```
