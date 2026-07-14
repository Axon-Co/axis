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
        .ssid     = "EspBrain",
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

void nvs_config_save(const app_config_t *cfg)
{
    if (cfg) memcpy(&s_current_config, cfg, sizeof(app_config_t));

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
    ESP_LOGI(TAG, "Configuration saved");
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
