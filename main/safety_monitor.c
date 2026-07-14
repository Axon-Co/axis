#include "safety_monitor.h"
#include "servo_controller.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "Safety";

static uint16_t s_signal_loss_timeout = 5000;
static uint16_t s_poor_quality_timeout = 10000;
static uint32_t s_last_valid_signal = 0;
static uint32_t s_poor_quality_start = 0;
static bool s_emergency = false;
static bool s_initialized = false;

static const uint8_t SAFE_ANGLES[SERVO_COUNT] = {30, 10, 10, 10, 10};

static void safety_task(void *pv)
{
    (void)pv;
    while (1) {
        vTaskDelay(pdMS_TO_TICKS(500));

        if (!s_initialized) continue;

        uint32_t now = xTaskGetTickCount() * portTICK_PERIOD_MS;

        if (s_emergency) continue;

        if (s_last_valid_signal > 0 &&
            (now - s_last_valid_signal) > s_signal_loss_timeout) {
            ESP_LOGW(TAG, "Signal loss! Moving to safe position");
            servo_smooth_all(SAFE_ANGLES, 1000);
            servo_enable(false);
            s_emergency = true;
        }
    }
}

void safety_monitor_init(uint16_t signal_loss_ms, uint16_t poor_quality_ms)
{
    s_signal_loss_timeout = signal_loss_ms;
    s_poor_quality_timeout = poor_quality_ms;
    s_last_valid_signal = 0;
    s_poor_quality_start = 0;
    s_emergency = false;
    s_initialized = true;

    xTaskCreate(safety_task, "safety", 2048, NULL, 15, NULL);
    ESP_LOGI(TAG, "Safety monitor initialized");
}

void safety_monitor_feed(const tgam_data_t *eeg)
{
    if (!eeg || !s_initialized) return;

    uint32_t now = xTaskGetTickCount() * portTICK_PERIOD_MS;

    if (eeg->poor_signal_quality == 0) {
        s_last_valid_signal = now;
        s_poor_quality_start = 0;

        if (s_emergency) {
            ESP_LOGI(TAG, "Signal recovered, releasing emergency stop");
            s_emergency = false;
            servo_enable(true);
        }
    } else if (eeg->poor_signal_quality > 200) {
        if (s_poor_quality_start == 0) {
            s_poor_quality_start = now;
        } else if ((now - s_poor_quality_start) > s_poor_quality_timeout) {
            if (!s_emergency) {
                ESP_LOGW(TAG, "Poor quality timeout! Moving to safe position");
                servo_smooth_all(SAFE_ANGLES, 1000);
                s_emergency = true;
            }
        }
    } else {
        s_poor_quality_start = 0;
        s_last_valid_signal = now;
    }
}

bool safety_monitor_is_safe(void)
{
    return !s_emergency;
}

void safety_monitor_emergency_stop(void)
{
    ESP_LOGW(TAG, "EMERGENCY STOP");
    s_emergency = true;
    servo_smooth_all(SAFE_ANGLES, 500);
    servo_enable(false);
}

void safety_monitor_release(void)
{
    ESP_LOGI(TAG, "Safety release");
    s_emergency = false;
    s_last_valid_signal = xTaskGetTickCount() * portTICK_PERIOD_MS;
    servo_enable(true);
}

uint32_t safety_monitor_last_signal_ms(void)
{
    return s_last_valid_signal;
}
