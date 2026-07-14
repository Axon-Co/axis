#include "serial_cli.h"
#include "command_interpreter.h"
#include "servo_controller.h"
#include "nvs_config.h"
#include "safety_monitor.h"
#include "gesture_player.h"
#include "data_logger.h"
#include "eeg_reader.h"
#include "esp_log.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/uart.h"
#include <string.h>
#include <stdio.h>
#include <ctype.h>

static const char *TAG = "CLI";

#define CLI_UART      UART_NUM_0
#define CLI_BUF_SIZE  256
#define CLI_MAX_ARGS  16
#define CLI_PROMPT    "espbrain> "

typedef struct {
    char name[24];
    char help[64];
    void (*handler)(int argc, char **argv);
} cmd_entry_t;

#define MAX_CMDS 32
static cmd_entry_t s_cmds[MAX_CMDS];
static int s_cmd_count = 0;
static char s_line[CLI_BUF_SIZE];
static int s_line_pos = 0;

static void cmd_help(int argc, char **argv);
static void cmd_mode(int argc, char **argv);
static void cmd_status(int argc, char **argv);
static void cmd_config(int argc, char **argv);
static void cmd_save(int argc, char **argv);
static void cmd_load(int argc, char **argv);
static void cmd_reset(int argc, char **argv);
static void cmd_servo(int argc, char **argv);
static void cmd_gesture(int argc, char **argv);
static void cmd_log(int argc, char **argv);
static void cmd_safety(int argc, char **argv);
static void cmd_reboot(int argc, char **argv);
static void cmd_info(int argc, char **argv);

void serial_cli_register_cmd(const char *name, const char *help,
                              void (*handler)(int, char **))
{
    if (s_cmd_count >= MAX_CMDS) return;
    strncpy(s_cmds[s_cmd_count].name, name, sizeof(s_cmds[s_cmd_count].name) - 1);
    strncpy(s_cmds[s_cmd_count].help, help, sizeof(s_cmds[s_cmd_count].help) - 1);
    s_cmds[s_cmd_count].handler = handler;
    s_cmd_count++;
}

static void register_builtins(void)
{
    serial_cli_register_cmd("help",     "List available commands",      cmd_help);
    serial_cli_register_cmd("mode",     "Set mode: 0=Grip,1=Finger,2=Seq,3=Cal", cmd_mode);
    serial_cli_register_cmd("status",  "Show system status",           cmd_status);
    serial_cli_register_cmd("config",  "Show/set config: config set <key> <val>", cmd_config);
    serial_cli_register_cmd("save",    "Save config to NVS",           cmd_save);
    serial_cli_register_cmd("load",    "Load config from NVS",         cmd_load);
    serial_cli_register_cmd("reset",   "Reset to factory defaults",    cmd_reset);
    serial_cli_register_cmd("servo",   "Direct servo: servo <id> <angle>", cmd_servo);
    serial_cli_register_cmd("gesture", "Play gesture: gesture <id>",   cmd_gesture);
    serial_cli_register_cmd("log",     "Logging: log start|stop",      cmd_log);
    serial_cli_register_cmd("safety",  "Safety: safety stop|release",  cmd_safety);
    serial_cli_register_cmd("reboot",  "Restart ESP32",                cmd_reboot);
    serial_cli_register_cmd("info",    "System information",           cmd_info);
}

static void cmd_help(int argc, char **argv)
{
    (void)argc; (void)argv;
    printf("\nAvailable commands:\n");
    for (int i = 0; i < s_cmd_count; i++) {
        printf("  %-12s %s\n", s_cmds[i].name, s_cmds[i].help);
    }
    printf("\n");
}

static void cmd_mode(int argc, char **argv)
{
    if (argc < 2) {
        const char *mode_names[] = {"GRIP", "FINGER_SELECT", "SEQUENCE", "CALIBRATE"};
        int m = command_interpreter_get_mode();
        printf("Current mode: %d (%s)\n", m,
               m >= 0 && m < 4 ? mode_names[m] : "UNKNOWN");
        return;
    }
    int mode = atoi(argv[1]);
    if (mode >= 0 && mode <= 3) {
        command_interpreter_set_mode((control_mode_t)mode);
        printf("Mode set to %d\n", mode);
    } else {
        printf("Invalid mode. Use 0-3.\n");
    }
}

static void cmd_status(int argc, char **argv)
{
    (void)argc; (void)argv;
    const app_config_t *cfg = nvs_config_get();
    const char *mode_names[] = {"GRIP", "FINGER_SELECT", "SEQUENCE", "CALIBRATE"};

    int m = command_interpreter_get_mode();
    printf("\n=== EspBrain Status ===\n");
    printf("Mode:       %d (%s)\n", m, m >= 0 && m < 4 ? mode_names[m] : "?");
    printf("Speed:      %d\n", cfg->system_speed);
    printf("Logging:    %s (%lu records)\n",
           data_logger_get_state() == LOGGER_RUNNING ? "ON" : "OFF",
           data_logger_get_count());
    printf("Safe:       %s\n", safety_monitor_is_safe() ? "YES" : "NO");
    printf("Servos:     %d\n", SERVO_COUNT);

    for (int i = 0; i < SERVO_COUNT; i++) {
        printf("  Servo[%d]: angle=%d\n", i, servo_get_angle((servo_id_t)i));
    }
    printf("WiFi:       %s\n", cfg->wifi.enabled ? cfg->wifi.ssid : "disabled");
    printf("======================\n\n");
}

static void cmd_config(int argc, char **argv)
{
    if (argc < 2) {
        const app_config_t *cfg = nvs_config_get();
        printf("\n=== Configuration ===\n");
        printf("brain.attention_threshold_low  = %d\n", cfg->brain.attention_threshold_low);
        printf("brain.attention_threshold_high = %d\n", cfg->brain.attention_threshold_high);
        printf("brain.blink_threshold          = %d\n", cfg->brain.blink_threshold);
        printf("brain.smoothing_factor         = %d\n", cfg->brain.smoothing_factor);
        printf("brain.min_grip                 = %d\n", cfg->brain.min_grip);
        printf("brain.max_grip                 = %d\n", cfg->brain.max_grip);
        printf("wifi.ssid                      = %s\n", cfg->wifi.ssid);
        printf("wifi.enabled                   = %s\n", cfg->wifi.enabled ? "yes" : "no");
        printf("logging.rate_hz                = %d\n", cfg->logging.rate_hz);
        printf("safety.signal_loss_timeout_ms  = %d\n", cfg->safety.signal_loss_timeout_ms);
        printf("safety.poor_quality_timeout_ms = %d\n", cfg->safety.poor_quality_timeout_ms);
        printf("system_speed                   = %d\n", cfg->system_speed);
        printf("========================\n");
        return;
    }

    if (argc == 4 && strcmp(argv[1], "set") == 0) {
        app_config_t cfg;
        nvs_config_load(&cfg);

        const char *key = argv[2];
        int val = atoi(argv[3]);

        if      (strcmp(key, "attention_threshold_low") == 0)  cfg.brain.attention_threshold_low = val;
        else if (strcmp(key, "attention_threshold_high") == 0) cfg.brain.attention_threshold_high = val;
        else if (strcmp(key, "blink_threshold") == 0)          cfg.brain.blink_threshold = val;
        else if (strcmp(key, "smoothing_factor") == 0)         cfg.brain.smoothing_factor = val;
        else if (strcmp(key, "system_speed") == 0)             cfg.system_speed = val;
        else if (strcmp(key, "signal_loss_timeout") == 0)      cfg.safety.signal_loss_timeout_ms = val;
        else if (strcmp(key, "poor_quality_timeout") == 0)     cfg.safety.poor_quality_timeout_ms = val;
        else if (strcmp(key, "logging_rate") == 0)             cfg.logging.rate_hz = val;
        else if (strcmp(key, "wifi_enabled") == 0)             cfg.wifi.enabled = val;
        else {
            printf("Unknown key: %s\n", key);
            return;
        }

        command_interpreter_set_config(&cfg.brain);
        servo_set_speed(cfg.system_speed);
        nvs_config_save(&cfg);
        printf("Set %s = %d\n", key, val);
    }
}

static void cmd_save(int argc, char **argv)
{
    (void)argc; (void)argv;
    nvs_config_save(NULL);
    printf("Configuration saved to NVS.\n");
}

static void cmd_load(int argc, char **argv)
{
    (void)argc; (void)argv;
    app_config_t cfg;
    nvs_config_load(&cfg);
    command_interpreter_set_config(&cfg.brain);
    servo_set_speed(cfg.system_speed);
    printf("Configuration loaded from NVS.\n");
}

static void cmd_reset(int argc, char **argv)
{
    (void)argc; (void)argv;
    nvs_config_reset();
    printf("Reset to factory defaults. Reboot to apply.\n");
}

static void cmd_servo(int argc, char **argv)
{
    if (argc < 3) {
        printf("Usage: servo <id> <angle>\n");
        return;
    }
    int id = atoi(argv[1]);
    int angle = atoi(argv[2]);
    if (id >= 0 && id < SERVO_COUNT && angle >= 0 && angle <= 180) {
        servo_set_angle((servo_id_t)id, (uint8_t)angle);
        printf("Servo[%d] -> %d\n", id, angle);
    } else {
        printf("Invalid servo ID (0-%d) or angle (0-180).\n", SERVO_COUNT - 1);
    }
}

static void cmd_gesture(int argc, char **argv)
{
    if (argc < 2) {
        printf("Available gestures:\n");
        for (int i = 0; i < gesture_player_count(); i++) {
            printf("  %d: %s\n", i, gesture_player_name(i));
        }
        return;
    }
    int id = atoi(argv[1]);
    if (gesture_player_play((uint8_t)id)) {
        printf("Playing gesture %d\n", id);
    } else {
        printf("Invalid gesture ID (0-%d).\n", gesture_player_count() - 1);
    }
}

static void cmd_log(int argc, char **argv)
{
    if (argc < 2) {
        printf("Logging is %s\n",
               data_logger_get_state() == LOGGER_RUNNING ? "ON" : "OFF");
        return;
    }
    if (strcmp(argv[1], "start") == 0) {
        if (data_logger_start())
            printf("Logging started\n");
        else
            printf("Failed to start logging\n");
    } else if (strcmp(argv[1], "stop") == 0) {
        data_logger_stop();
        printf("Logging stopped\n");
    }
}

static void cmd_safety(int argc, char **argv)
{
    if (argc < 2) {
        printf("Safety: %s\n", safety_monitor_is_safe() ? "SAFE" : "EMERGENCY");
        return;
    }
    if (strcmp(argv[1], "stop") == 0) {
        safety_monitor_emergency_stop();
        printf("Emergency stop activated\n");
    } else if (strcmp(argv[1], "release") == 0) {
        safety_monitor_release();
        printf("Emergency stop released\n");
    }
}

static void cmd_reboot(int argc, char **argv)
{
    (void)argc; (void)argv;
    printf("Rebooting...\n");
    vTaskDelay(pdMS_TO_TICKS(100));
    esp_restart();
}

static void cmd_info(int argc, char **argv)
{
    (void)argc; (void)argv;
    printf("\nEspBrain v1.0\n");
    printf("Framework: ESP-IDF\n");
    printf("Target:    ESP32\n");
    printf("Modules:\n");
    printf("  EEG:     TGAM ThinkGear\n");
    printf("  Servos:  %d channels LEDC PWM\n", SERVO_COUNT);
    printf("  Motion:  S-curve planner\n");
    printf("  Gestures:%d presets\n", gesture_player_count());
    printf("  Storage: NVS + SD card\n");
    printf("  Remote:  WiFi WebSocket\n");
    printf("Heap free: %lu bytes\n", esp_get_free_heap_size());
    printf("\n");
}

static void process_line(const char *line)
{
    char work[CLI_BUF_SIZE];
    strncpy(work, line, sizeof(work) - 1);
    work[sizeof(work) - 1] = '\0';

    char *argv[CLI_MAX_ARGS];
    int argc = 0;
    char *token = strtok(work, " \t\r\n");
    while (token && argc < CLI_MAX_ARGS) {
        argv[argc++] = token;
        token = strtok(NULL, " \t\r\n");
    }

    if (argc == 0) return;

    for (int i = 0; i < s_cmd_count; i++) {
        if (strcmp(argv[0], s_cmds[i].name) == 0) {
            s_cmds[i].handler(argc, argv);
            return;
        }
    }

    printf("Unknown command: %s\nType 'help' for available commands.\n", argv[0]);
}

static void cli_task(void *pv)
{
    (void)pv;
    uint8_t byte;
    int len;

    printf("\nEspBrain BCI System\n");
    printf("Type 'help' for commands\n\n");

    while (1) {
        len = uart_read_bytes(CLI_UART, &byte, 1, pdMS_TO_TICKS(50));
        if (len <= 0) continue;

        if (byte == '\r' || byte == '\n') {
            if (s_line_pos > 0) {
                s_line[s_line_pos] = '\0';
                printf("\n");
                process_line(s_line);
                s_line_pos = 0;
            }
            printf(CLI_PROMPT);
            fflush(stdout);
        } else if (byte == '\b' || byte == 127) {
            if (s_line_pos > 0) {
                s_line_pos--;
                printf("\b \b");
                fflush(stdout);
            }
        } else if (s_line_pos < CLI_BUF_SIZE - 1) {
            s_line[s_line_pos++] = (char)byte;
            printf("%c", (char)byte);
            fflush(stdout);
        }
    }
}

void serial_cli_init(void)
{
    register_builtins();
    s_line_pos = 0;

    xTaskCreate(cli_task, "serial_cli", 4096, NULL, 3, NULL);
    ESP_LOGI(TAG, "Serial CLI initialized");
}
