# Axis API Reference

## Module: tgam_protocol

### `void tgam_parser_init(tgam_parser_t *parser)`
Initialize the TGAM packet parser state machine. Must be called before parsing.

### `bool tgam_parse_byte(tgam_parser_t *parser, uint8_t byte, tgam_data_t *out)`
Feed one byte to the parser. When a complete valid packet is received, `out` is populated. Returns `true` on packet completion.

### `tgam_data_t`
```c
typedef struct {
    int16_t poor_signal_quality;  // 0=good, >0=noise
    uint8_t attention;            // 0-100 focus level
    uint8_t meditation;           // 0-100 relaxation
    uint8_t blink_strength;       // 0-255 blink intensity
    int16_t raw_wave;             // raw EEG amplitude
    struct {
        uint32_t delta, theta, low_alpha, high_alpha;
        uint32_t low_beta, high_beta, low_gamma, high_gamma;
    } eeg_power;                  // frequency band powers
    bool has_new_data;            // set when packet parsed
} tgam_data_t;
```

## Module: eeg_reader

### `void eeg_reader_init(void)`
Initialize UART2 for TGAM communication, start parser task. Must be called once.

### `tgam_data_t eeg_reader_get_latest(void)`
Get the latest parsed EEG data. Thread-safe. Resets `has_new_data` flag.

### `void eeg_reader_reset(void)`
Reset parser state machine and clear data.

## Module: servo_controller

### `void servo_controller_init(const servo_config_t *configs)`
Initialize LEDC PWM for all servos. Takes array of `SERVO_COUNT` configs.

### `void servo_set_angle(servo_id_t servo, uint8_t angle)`
Immediately set servo to angle (0-180, clamped to min/max).

### `void servo_set_all(const uint8_t *angles)`
Set all servos simultaneously.

### `void servo_smooth_to(servo_id_t servo, uint8_t target, uint16_t duration_ms)`
Smoothly move servo to target over duration. Uses motion planner if available.

### `void servo_smooth_all(const uint8_t *targets, uint16_t duration_ms)`
Smoothly move all servos to targets.

### `void servo_set_speed(uint8_t speed)`
Set global speed factor (0-255). 128 = normal, 255 = instant.

### `uint8_t servo_get_angle(servo_id_t servo)`
Get current servo angle.

### `void servo_enable(bool on)`
Enable/disable all servos (zero PWM when disabled).

### `servo_config_t`
```c
typedef struct {
    int gpio_pin;        // GPIO number
    uint8_t min_angle;   // mechanical minimum
    uint8_t max_angle;   // mechanical maximum
    uint8_t home_position; // startup position
    bool    invert;      // reverse direction
} servo_config_t;
```

## Module: command_interpreter

### `void command_interpreter_init(const brain_map_config_t *config)`
Initialize interpreter with brain mapping config (or NULL for defaults).

### `void command_interpreter_set_mode(control_mode_t mode)`
Switch control mode.

### `control_mode_t command_interpreter_get_mode(void)`
Get current mode.

### `void command_interpreter_process(const tgam_data_t *eeg)`
Main processing: maps EEG data → servo commands based on current mode.

### `void command_interpreter_set_config(const brain_map_config_t *config)`
Update brain mapping parameters at runtime.

### `control_mode_t`
```c
typedef enum {
    MODE_GRIP,           // Attention→grip strength
    MODE_FINGER_SELECT,  // Brain waves→finger selection
    MODE_SEQUENCE,       // Play recorded sequence
    MODE_CALIBRATE       // Raw data output
} control_mode_t;
```

### `brain_map_config_t`
```c
typedef struct {
    uint8_t attention_threshold_low;
    uint8_t attention_threshold_high;
    uint8_t blink_threshold;
    uint8_t smoothing_factor;  // 0-100
    uint8_t min_grip;
    uint8_t max_grip;
} brain_map_config_t;
```

## Module: nvs_config

### `void nvs_config_init(void)`
Initialize NVS partition. Load config or set defaults.

### `void nvs_config_load(app_config_t *cfg)`
Load configuration from NVS flash.

### `void nvs_config_save(const app_config_t *cfg)`
Save configuration to NVS flash.

### `void nvs_config_reset(void)`
Reset to factory defaults.

### `const app_config_t *nvs_config_get(void)`
Get pointer to current config (read-only).

### `app_config_t`
Full configuration structure including brain mapping, servo limits, WiFi credentials, and system settings.

## Module: serial_cli

### `void serial_cli_init(void)`
Start serial CLI task on UART0 (USB).

### Commands

| Command | Arguments | Description |
|---------|-----------|-------------|
| `help` | | List all commands |
| `mode` | `<0-3>` | Switch control mode |
| `status` | | Show system status |
| `config` | | Show current config |
| `config set` | `<key> <value>` | Set config parameter |
| `save` | | Save config to NVS |
| `load` | | Load config from NVS |
| `reset` | | Reset to defaults |
| `servo` | `<id> <angle>` | Direct servo control |
| `gesture` | `<id>` | Play gesture sequence |
| `log` | `start\|stop` | Toggle data logging |
| `wifi` | `start\|stop\|status` | WiFi control |
| `calibrate` | | Enter calibration mode |
| `reboot` | | Restart ESP32 |

## Module: wifi_control

### `void wifi_control_init(void)`
Start WiFi Access Point + WebSocket server.

### `void wifi_control_broadcast(const tgam_data_t *eeg, const uint8_t *servo_angles)`
Broadcast real-time data to all connected WebSocket clients.

### `void wifi_control_stop(void)`
Stop WiFi and clean up.

### WebSocket Protocol

**Server → Client (JSON):**
```json
{
  "type": "eeg",
  "attention": 65,
  "meditation": 42,
  "blink": 0,
  "signal": 0,
  "servos": [30, 45, 50, 40, 35],
  "mode": 0,
  "timestamp": 123456
}
```

**Client → Server (JSON):**
```json
{"cmd": "mode", "value": 1}
{"cmd": "servo", "id": 2, "angle": 90}
{"cmd": "config", "key": "smoothing_factor", "value": 60}
{"cmd": "gesture", "id": 0}
```

## Module: data_logger

### `void data_logger_init(void)`
Initialize SD card and prepare logging.

### `void data_logger_start(void)`
Start logging EEG data to CSV file.

### `void data_logger_stop(void)`
Stop logging and close file.

### `void data_logger_feed(const tgam_data_t *eeg, const uint8_t *servo_angles)`
Write one data row to CSV.

### CSV Format
```
timestamp,attention,meditation,blink_strength,raw_wave,
delta,theta,low_alpha,high_alpha,low_beta,high_beta,low_gamma,high_gamma,
servo0,servo1,servo2,servo3,servo4
```

## Module: gesture_player

### `void gesture_player_init(void)`
Initialize gesture database.

### `void gesture_player_play(uint8_t gesture_id)`
Play gesture sequence with smooth transitions.

### `void gesture_player_stop(void)`
Stop current gesture immediately.

### `int gesture_player_count(void)`
Get number of defined gestures.

### Predefined Gestures

| ID | Name | Description |
|----|------|-------------|
| 0 | Open | Relaxed open hand |
| 1 | Fist | Full grip |
| 2 | Point | Index finger extended |
| 3 | Pinch | Thumb + index pinch |
| 4 | Peace | V-sign (index + middle) |
| 5 | Ok | OK sign (thumb + index circle) |
| 6 | Wave | Wave motion sequence |

## Module: safety_monitor

### `void safety_monitor_init(void)`
Start safety monitor task.

### `void safety_monitor_feed(const tgam_data_t *eeg)`
Feed latest EEG data to monitor. Resets signal loss timer.

### `bool safety_monitor_is_safe(void)`
Returns false if emergency condition detected.

### Safety Triggers
- Signal loss > 5 seconds → safe position
- Poor signal quality > 200 for 10s → safe position
- Manual emergency stop via CLI
- Watchdog timer reset if main loop hangs

## Module: motion_planner

### `void motion_planner_init(void)`
Initialize motion planner.

### `void motion_planner_set_target(servo_id_t servo, uint8_t target, uint16_t time_ms)`
Set target position with transition time. Motion follows S-curve profile.

### `bool motion_planner_update(uint8_t *current_angles)`
Call periodically (every 20ms). Updates angles array with interpolated values. Returns true when all motions complete.

### `void motion_planner_stop_all(void)`
Stop all active motions immediately.
