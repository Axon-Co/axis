# Axis System Architecture

## Overview

Axis is a non-invasive brain-computer interface (BCI) system that reads human EEG signals via a NeuroSky TGAM module and translates them into servo motor commands for a robotic hand. The system runs on an ESP32 microcontroller.

## System Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         ESP32 (ESP-IDF)                            │
│                                                                     │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────┐             │
│  │  TGAM    │───▶│  eeg_reader  │───▶│  command     │───▶ Servos │
│  │  Module  │UART│  (parser)    │    │  interpreter │             │
│  └──────────┘    └──────────────┘    └──────┬───────┘             │
│                                              │                     │
│  ┌──────────┐    ┌──────────────┐           │                     │
│  │  Serial  │◀──▶│  serial_cli  │◀──────────┘                     │
│  │  Console │    │  (commands)  │                                  │
│  └──────────┘    └──────────────┘                                  │
│                                              │                     │
│  ┌──────────┐    ┌──────────────┐           │                     │
│  │  WiFi    │◀──▶│ wifi_control │◀──────────┘                     │
│  │  Client  │    │ (WebSocket)  │                                  │
│  └──────────┘    └──────────────┘                                  │
│                                              │                     │
│  ┌──────────┐    ┌──────────────┐           │                     │
│  │  SD Card │◀──▶│ data_logger  │◀──────────┘                     │
│  │  (FAT32) │    │   (CSV)      │                                  │
│  └──────────┘    └──────────────┘                                  │
│                                              │                     │
│  ┌──────────┐    ┌──────────────┐           │                     │
│  │   NVS    │◀──▶│  nvs_config  │◀──────────┘                     │
│  │ (Flash)  │    │ (persist)    │                                  │
│  └──────────┘    └──────────────┘                                  │
│                                                                     │
│  ┌────────────────┐   ┌────────────────┐   ┌───────────┐          │
│  │ gesture_player │──▶│ motion_planner │──▶│  safety   │          │
│  │ (presets)      │   │ (S-curve)      │   │ monitor   │          │
│  └────────────────┘   └────────────────┘   └───────────┘          │
└─────────────────────────────────────────────────────────────────────┘
```

## Module Dependencies

```
main.c
  ├── nvs_config       (no deps)
  ├── eeg_reader       (tgam_protocol)
  ├── servo_controller (motion_planner)
  ├── command_interpreter (servo_controller, nvs_config)
  ├── serial_cli       (all modules)
  ├── wifi_control     (all modules)
  ├── data_logger      (sdmmc)
  ├── gesture_player   (servo_controller, motion_planner)
  └── safety_monitor   (servo_controller)
```

## Data Flow

### Primary Path (Brain → Hand)
```
TGAM EEG → UART bytes → tgam_parse_byte() → tgam_data_t
    → command_interpreter_process()
        → map attention/meditation/blink → servo angles
        → servo_smooth_to() / servo_set_all()
            → motion_planner (S-curve interpolation)
                → LEDC PWM → servo motors
```

### Configuration Path
```
serial_cli / wifi_control → commands
    → nvs_config_set/save()
        → NVS flash storage
            → nvs_config_load()
                → command_interpreter / servo_controller
```

### Data Logging Path (Training)
```
eeg_reader → tgam_data_t
    → data_logger_feed()
        → CSV format → SD card (FAT32)
```

### Remote Control Path
```
WiFi client → WebSocket → wifi_control
    → command_interpreter_set_mode()
    → servo_set_angle() (direct override)
    → data feed back to client
```

## Task Structure (FreeRTOS)

| Task | Stack | Priority | Function |
|------|-------|----------|----------|
| `eeg_reader` | 4096 | 10 | UART event handler |
| `main_loop` | 4096 | 5 | Primary control loop |
| `serial_cli` | 4096 | 3 | Serial command interface |
| `wifi_ctrl` | 8192 | 5 | WiFi + WebSocket server |
| `safety_wd` | 2048 | 15 | Watchdog timer |

## Memory Layout

```
┌─────────────────────┐
│   IRAM (inst)       │  ~100KB
├─────────────────────┤
│   DRAM (data)       │  ~200KB
├─────────────────────┤
│   BSS/Heap          │  ~100KB
├─────────────────────┤
│   NVS (config)      │  16KB
├─────────────────────┤
│   SD Card (data)    │  GB range
└─────────────────────┘
```

## Key Design Decisions

1. **UART for TGAM**: TGAM outputs at 57600 baud, UART2 with event-driven reading
2. **LEDC for servos**: ESP32 hardware PWM, 13-bit resolution, 50Hz
3. **FreeRTOS tasks**: Separate tasks for I/O, processing, and safety
4. **NVS for config**: Built-in ESP32 non-volatile storage
5. **CSV for logging**: Universal format, easy ML pipeline integration
6. **WebSocket for remote**: Full-duplex, low-latency remote control
7. **S-curve motion**: Smooth, natural-looking robot movement
