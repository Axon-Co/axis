#include "nvs_config.h"
#include "esp_log.h"
#include "nvs_flash.h"
#include <string.h>

static const char *TAG = "NVS_Config";

static app_config_t s_current_config;

static const app_config_t DEFAULT_CONFIG = {
    .brain = {
        .attention_threshold_low  = 30,
        .attention_threshold_high = 70,
        .blink_threshold          = 80,
        .smoothing_factor         = 40,
        .min_grip                 = 0,
        .max_grip                 = 100,
    },
    .servo = {
        .min_angle      = {20, 0, 0, 0, 10},
        .max_angle      = {160, 180, 180, 180, 170},
        .home_position  = {30, 10, 10, 10, 10},
        .invert         = {false, false, false, false, false},
    },
    .wifi = {
        .ssid     = "Axis",
        .password = "12345678",
        .channel  = 1,
        .enabled  = true,
    },
    .logging = {
        .enabled = false,
        .rate_hz = 10,
    },
    .safety = {
        .signal_loss_timeout_ms   = 5000,
        .poor_quality_timeout_ms  = 10000,
    },
    .default_mode  = MODE_GRIP,
    .system_speed  = 128,
};

void nvs_config_init(void)
{
    memcpy(&s_current_config, &DEFAULT_CONFIG, sizeof(app_config_t));

    nvs_handle_t handle;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READONLY, &handle);
    if (err == ESP_OK) {
        size_t size = sizeof(app_config_t);
        err = nvs_get_blob(handle, "config", &s_current_config, &size);
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "No saved config, using defaults");
        }
        nvs_close(handle);
    } else {
        ESP_LOGI(TAG, "NVS not initialized, using defaults");
    }
}

void nvs_config_load(app_config_t *cfg)
{
    if (cfg) *cfg = s_current_config;
}

static bool validate_config(const app_config_t *cfg)
{
    if (!cfg) return false;

    if (cfg->brain.attention_threshold_low >= cfg->brain.attention_threshold_high) {
        ESP_LOGW(TAG, "Invalid thresholds: low=%d >= high=%d",
                 cfg->brain.attention_threshold_low, cfg->brain.attention_threshold_high);
        return false;
    }
    if (cfg->brain.smoothing_factor > 100) {
        ESP_LOGW(TAG, "Invalid smoothing_factor: %d", cfg->brain.smoothing_factor);
        return false;
    }
    if (cfg->brain.min_grip > cfg->brain.max_grip) {
        ESP_LOGW(TAG, "Invalid grip range: min=%d > max=%d",
                 cfg->brain.min_grip, cfg->brain.max_grip);
        return false;
    }
    if (cfg->system_speed < 1 || cfg->system_speed > 255) {
        ESP_LOGW(TAG, "Invalid system_speed: %d", cfg->system_speed);
        return false;
    }
    if (cfg->safety.signal_loss_timeout_ms < 100) {
        ESP_LOGW(TAG, "signal_loss_timeout too low: %d", cfg->safety.signal_loss_timeout_ms);
        return false;
    }
    if (cfg->logging.rate_hz < 1 || cfg->logging.rate_hz > 100) {
        ESP_LOGW(TAG, "Invalid logging rate: %d", cfg->logging.rate_hz);
        return false;
    }
    for (int i = 0; i < SERVO_COUNT; i++) {
        if (cfg->servo.min_angle[i] > cfg->servo.max_angle[i]) {
            ESP_LOGW(TAG, "Servo[%d]: min=%d > max=%d",
                     i, cfg->servo.min_angle[i], cfg->servo.max_angle[i]);
            return false;
        }
    }
    return true;
}

void nvs_config_save(const app_config_t *cfg)
{
    if (cfg) {
        if (!validate_config(cfg)) {
            ESP_LOGE(TAG, "Config validation failed — save rejected");
            return;
        }
        memcpy(&s_current_config, cfg, sizeof(app_config_t));
    }

    nvs_handle_t handle;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "NVS open failed: %s", esp_err_to_name(err));
        return;
    }

    err = nvs_set_blob(handle, "config", &s_current_config, sizeof(app_config_t));
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "NVS write failed: %s", esp_err_to_name(err));
    }

    err = nvs_commit(handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "NVS commit failed: %s", esp_err_to_name(err));
    }

    nvs_close(handle);
    ESP_LOGI(TAG, "Configuration saved (validated)");
}

void nvs_config_reset(void)
{
    memcpy(&s_current_config, &DEFAULT_CONFIG, sizeof(app_config_t));
    nvs_config_save(NULL);
    ESP_LOGI(TAG, "Reset to factory defaults");
}

const app_config_t *nvs_config_get(void)
{
    return &s_current_config;
}
