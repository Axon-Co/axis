#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "nvs_flash.h"
#include "eeg_reader.h"
#include "servo_controller.h"
#include "command_interpreter.h"
#include "nvs_config.h"
#include "motion_planner.h"
#include "gesture_player.h"
#include "safety_monitor.h"
#include "data_logger.h"
#include "serial_cli.h"
#include "wifi_control.h"
#include "signal_processor.h"
#include "diagnostics.h"
#include "led_status.h"
#include "version.h"

static const char *TAG = "Axis";

#define GPIO_SERVO_THUMB GPIO_NUM_18
#define GPIO_SERVO_INDEX GPIO_NUM_19
#define GPIO_SERVO_MID   GPIO_NUM_21
#define GPIO_SERVO_RING  GPIO_NUM_22
#define GPIO_SERVO_PINKY GPIO_NUM_23

#define GPIO_LED_R       GPIO_NUM_25
#define GPIO_LED_G       GPIO_NUM_26
#define GPIO_LED_B       GPIO_NUM_27

static const int DEFAULT_PINS[SERVO_COUNT] = {
    GPIO_SERVO_THUMB,
    GPIO_SERVO_INDEX,
    GPIO_SERVO_MID,
    GPIO_SERVO_RING,
    GPIO_SERVO_PINKY,
};

static void build_servo_configs(servo_config_t *configs, const app_config_t *cfg)
{
    for (int i = 0; i < SERVO_COUNT; i++) {
        configs[i].gpio_pin      = DEFAULT_PINS[i];
        configs[i].min_angle     = cfg->servo.min_angle[i];
        configs[i].max_angle     = cfg->servo.max_angle[i];
        configs[i].home_position = cfg->servo.home_position[i];
        configs[i].invert        = cfg->servo.invert[i];
    }
}

void app_main(void)
{
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    nvs_config_init();
    const app_config_t *cfg = nvs_config_get();

    diagnostics_init();
    led_status_init(GPIO_LED_R, GPIO_LED_G, GPIO_LED_B);
    led_status_blink(LED_BOOTING, 150);

    motion_planner_init();

    servo_config_t servo_cfgs[SERVO_COUNT];
    build_servo_configs(servo_cfgs, cfg);
    servo_controller_init(servo_cfgs);
    servo_set_speed(cfg->system_speed);

    eeg_reader_init();
    safety_monitor_init(cfg->safety.signal_loss_timeout_ms,
                        cfg->safety.poor_quality_timeout_ms);
    signal_processor_init();
    command_interpreter_init(&cfg->brain);
    gesture_player_init();
    data_logger_init();
    serial_cli_init();

    if (cfg->wifi.enabled) {
        wifi_control_init(cfg->wifi.ssid, cfg->wifi.password, cfg->wifi.channel);
        led_status_set(LED_WIFI_ACTIVE);
    } else {
        led_status_set(LED_NORMAL);
    }

    ESP_LOGI(TAG, "Axis v%s ready", AXIS_VERSION_STR);
    ESP_LOGI(TAG, "WiFi SSID: %s | Servos: %d | Mode: GRIP",
             cfg->wifi.enabled ? cfg->wifi.ssid : "disabled", SERVO_COUNT);

    uint32_t last_status = 0;
    uint32_t last_ws = 0;
    tgam_data_t eeg = {0};
    processed_signal_t proc = {0};

    uint32_t last_led_update = 0;

    while (1) {
        tgam_data_t fresh = eeg_reader_get_latest();
        if (fresh.has_new_data) {
            eeg = fresh;
            diagnostics_update_eeg(&eeg);
            safety_monitor_feed(&eeg);

            signal_processor_feed(&eeg, &proc);

            if (safety_monitor_is_safe()) {
                command_interpreter_process(&eeg);
            }
        }

        uint32_t now = xTaskGetTickCount() * portTICK_PERIOD_MS;

        if (cfg->wifi.enabled && (now - last_ws > 100)) {
            uint8_t angles[SERVO_COUNT];
            for (int i = 0; i < SERVO_COUNT; i++)
                angles[i] = servo_get_angle((servo_id_t)i);
            wifi_control_broadcast(&eeg, angles);
            last_ws = now;
        }

        if (data_logger_get_state() == LOGGER_RUNNING) {
            uint8_t angles[SERVO_COUNT];
            for (int i = 0; i < SERVO_COUNT; i++)
                angles[i] = servo_get_angle((servo_id_t)i);
            data_logger_feed(&eeg, angles);
        }

        if (now - last_led_update > 500) {
            if (!safety_monitor_is_safe()) {
                led_status_blink(LED_EMERGENCY, 300);
            } else if (eeg.poor_signal_quality > 200) {
                led_status_set(LED_POOR_SIGNAL);
            } else if (command_interpreter_get_mode() == MODE_CALIBRATE) {
                led_status_blink(LED_CALIBRATING, 400);
            } else if (data_logger_get_state() == LOGGER_RUNNING) {
                led_status_blink(LED_LOGGING, 600);
            } else if (wifi_control_client_count() > 0) {
                led_status_set(LED_WIFI_ACTIVE);
            } else {
                led_status_set(LED_NORMAL);
            }
            last_led_update = now;
        }

        if (now - last_status > 10000) {
            ESP_LOGI(TAG, "v%s Att=%d Med=%d Blink=%d Signal=%d "
                          "Alpha/Beta=%.2f Theta/Gamma=%.2f "
                          "AdaptThr=%d/%d Mode=%d Clients=%d Heap=%lu",
                     AXIS_VERSION_STR,
                     eeg.attention, eeg.meditation,
                     eeg.blink_strength, eeg.poor_signal_quality,
                     proc.alpha_beta_ratio, proc.theta_gamma_ratio,
                     proc.adaptive_att_threshold_low,
                     proc.adaptive_att_threshold_high,
                     command_interpreter_get_mode(),
                     wifi_control_client_count(),
                     esp_get_free_heap_size());
            last_status = now;
        }

        vTaskDelay(pdMS_TO_TICKS(20));
    }
}
