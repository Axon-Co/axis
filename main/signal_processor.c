#include "signal_processor.h"
#include "esp_log.h"
#include <string.h>

static const char *TAG = "SigProc";

static uint8_t s_att_buffer[MOVING_AVG_WINDOW];
static uint8_t s_med_buffer[MOVING_AVG_WINDOW];
static int s_buffer_index = 0;
static int s_buffer_count = 0;

static uint32_t s_att_sum = 0;
static uint32_t s_med_sum = 0;

static uint8_t s_blink_history[BLINK_HISTORY_SIZE];
static int s_blink_index = 0;
static int s_blink_count_1s = 0;
static uint32_t s_last_blink_tick = 0;
static uint32_t s_last_double_tick = 0;

static uint8_t s_att_running_min = 255;
static uint8_t s_att_running_max = 0;
static uint32_t s_att_sample_count = 0;

static uint8_t s_blink_running_sum = 0;
static uint8_t s_blink_running_count = 0;

static uint8_t moving_average(uint8_t *buf, int count)
{
    if (count == 0) return 0;
    uint32_t sum = 0;
    for (int i = 0; i < count; i++) sum += buf[i];
    return sum / count;
}

void signal_processor_init(void)
{
    memset(s_att_buffer, 0, sizeof(s_att_buffer));
    memset(s_med_buffer, 0, sizeof(s_med_buffer));
    memset(s_blink_history, 0, sizeof(s_blink_history));
    s_buffer_index = 0;
    s_buffer_count = 0;
    s_blink_index = 0;
    s_att_running_min = 255;
    s_att_running_max = 0;
    s_att_sample_count = 0;
    s_blink_running_sum = 0;
    s_blink_running_count = 0;
    s_last_blink_tick = 0;
    s_last_double_tick = 0;
    s_blink_count_1s = 0;
    ESP_LOGI(TAG, "Signal processor initialized");
}

void signal_processor_feed(const tgam_data_t *raw, processed_signal_t *out)
{
    memset(out, 0, sizeof(*out));

    uint32_t now = xTaskGetTickCount() * portTICK_PERIOD_MS;

    s_att_sum += raw->attention;
    s_med_sum += raw->meditation;

    s_att_buffer[s_buffer_index] = raw->attention;
    s_med_buffer[s_buffer_index] = raw->meditation;
    s_buffer_index = (s_buffer_index + 1) % MOVING_AVG_WINDOW;
    if (s_buffer_count < MOVING_AVG_WINDOW) s_buffer_count++;

    if (s_buffer_count >= MOVING_AVG_WINDOW) {
        s_att_sum -= s_att_buffer[s_buffer_index];
        s_med_sum -= s_med_buffer[s_buffer_index];
    }

    out->attention = s_att_sum / s_buffer_count;
    out->meditation = s_med_sum / s_buffer_count;
    out->raw_wave = raw->raw_wave;

    float low_beta = (float)raw->eeg_power.low_beta;
    float high_beta = (float)raw->eeg_power.high_beta;
    float low_alpha = (float)raw->eeg_power.low_alpha;
    float high_alpha = (float)raw->eeg_power.high_alpha;
    float theta = (float)raw->eeg_power.theta;
    float low_gamma = (float)raw->eeg_power.low_gamma;
    float high_gamma = (float)raw->eeg_power.high_gamma;

    float beta = low_beta + high_beta;
    float alpha = low_alpha + high_alpha;
    float gamma = low_gamma + high_gamma;

    out->alpha_beta_ratio = (beta > 0) ? (alpha / beta) : 0;
    out->theta_gamma_ratio = (gamma > 0) ? (theta / gamma) : 0;
    out->attention_relax_index = (out->meditation > 0) ?
        (float)out->attention / out->meditation : 1.0f;

    if (raw->poor_signal_quality > 0) {
        out->signal_quality = 1.0f - (raw->poor_signal_quality / 255.0f);
    } else {
        out->signal_quality = 1.0f;
    }

    if (raw->blink_strength > 0) {
        s_blink_running_sum += raw->blink_strength;
        s_blink_running_count++;
    }

    out->blink_strength = raw->blink_strength;

    if (raw->blink_strength > 10) {
        uint8_t avg_blink = (s_blink_running_count > 0) ?
            (s_blink_running_sum / s_blink_running_count) : 50;
        uint8_t dynamic_threshold = (avg_blink * 3) / 2;
        if (dynamic_threshold < 30) dynamic_threshold = 30;

        if (raw->blink_strength > dynamic_threshold) {
            out->is_blink = true;

            if (s_last_blink_tick > 0 &&
                (now - s_last_blink_tick) < 500) {
                out->is_double_blink = true;
                s_last_double_tick = now;
            }
            s_last_blink_tick = now;
        }
    }

    s_blink_history[s_blink_index] = out->is_blink ? 1 : 0;
    s_blink_index = (s_blink_index + 1) % BLINK_HISTORY_SIZE;

    s_blink_count_1s = 0;
    for (int i = 0; i < BLINK_HISTORY_SIZE; i++)
        s_blink_count_1s += s_blink_history[i];

    if (s_att_sample_count < 100) {
        s_att_sample_count++;
        if (raw->attention < s_att_running_min && raw->attention > 5)
            s_att_running_min = raw->attention;
        if (raw->attention > s_att_running_max && raw->attention < 95)
            s_att_running_max = raw->attention;
    }

    out->adaptive_att_threshold_low = s_att_running_min + 10;
    out->adaptive_att_threshold_high = s_att_running_max - 10;
    out->adaptive_blink_threshold =
        (s_blink_running_count > 0) ?
        (s_blink_running_sum / s_blink_running_count * 3 / 2) : 80;

    if (out->adaptive_att_threshold_low > out->adaptive_att_threshold_high) {
        out->adaptive_att_threshold_low = 30;
        out->adaptive_att_threshold_high = 70;
    }
}

void signal_processor_reset(void)
{
    signal_processor_init();
}
