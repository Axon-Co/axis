#include "diagnostics.h"
#include "servo_controller.h"
#include "esp_timer.h"
#include "esp_heap_caps.h"
#include "freertos/FreeRTOS.h"
#include <string.h>
#include <limits.h>

static diagnostics_t s_diag;
static uint64_t s_start_time_us;
static uint32_t s_att_sum;
static uint32_t s_att_count;
static uint32_t s_med_sum;
static uint32_t s_med_count;

void diagnostics_init(void)
{
    memset(&s_diag, 0, sizeof(s_diag));
    s_start_time_us = esp_timer_get_time();
    s_att_sum = 0;
    s_att_count = 0;
    s_med_sum = 0;
    s_med_count = 0;
    s_diag.attention_stats.min = 255;
    s_diag.meditation_stats.min = 255;
    s_diag.min_heap_free = INT32_MAX;
}

void diagnostics_update_eeg(const tgam_data_t *eeg)
{
    if (!eeg) return;

    s_diag.total_eeg_packets++;

    uint8_t att = eeg->attention;
    uint8_t med = eeg->meditation;

    if (att > 0 && att < 100) {
        if (att < s_diag.attention_stats.min) s_diag.attention_stats.min = att;
        if (att > s_diag.attention_stats.max) s_diag.attention_stats.max = att;
        s_att_sum += att;
        s_att_count++;
        s_diag.attention_stats.avg = s_att_sum / s_att_count;
    }

    if (med > 0 && med < 100) {
        if (med < s_diag.meditation_stats.min) s_diag.meditation_stats.min = med;
        if (med > s_diag.meditation_stats.max) s_diag.meditation_stats.max = med;
        s_med_sum += med;
        s_med_count++;
        s_diag.meditation_stats.avg = s_med_sum / s_med_count;
    }

    if (eeg->poor_signal_quality > 0) {
        s_diag.dropped_packets++;
    }

    diagnostics_update_heap();
}

void diagnostics_increment_error(void)
{
    s_diag.error_count++;
}

void diagnostics_increment_recovery(void)
{
    s_diag.recovery_count++;
}

void diagnostics_increment_emergency_stop(void)
{
    s_diag.emergency_stops++;
}

void diagnostics_increment_wifi_reconnect(void)
{
    s_diag.wifi_reconnects++;
}

void diagnostics_update_heap(void)
{
    int32_t free = (int32_t)esp_get_free_heap_size();
    if (free < s_diag.min_heap_free) {
        s_diag.min_heap_free = free;
    }
}

void diagnostics_reset_stats(void)
{
    s_diag.total_eeg_packets = 0;
    s_diag.dropped_packets = 0;
    s_diag.error_count = 0;
    s_diag.recovery_count = 0;
    s_diag.emergency_stops = 0;
    s_diag.wifi_reconnects = 0;
    s_att_sum = 0;
    s_att_count = 0;
    s_med_sum = 0;
    s_med_count = 0;
    s_diag.attention_stats.min = 255;
    s_diag.attention_stats.max = 0;
    s_diag.attention_stats.avg = 0;
    s_diag.meditation_stats.min = 255;
    s_diag.meditation_stats.max = 0;
    s_diag.meditation_stats.avg = 0;
    s_diag.min_heap_free = INT32_MAX;
    s_start_time_us = esp_timer_get_time();
}

const diagnostics_t *diagnostics_get(void)
{
    s_diag.uptime_ms = (esp_timer_get_time() - s_start_time_us) / 1000;
    return &s_diag;
}

uint64_t diagnostics_get_uptime_ms(void)
{
    return (esp_timer_get_time() - s_start_time_us) / 1000;
}
