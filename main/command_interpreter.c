#include "command_interpreter.h"
#include "servo_controller.h"
#include "esp_log.h"
#include <string.h>

static const char *TAG = "CmdInterp";

static control_mode_t s_mode = MODE_GRIP;
static brain_map_config_t s_config;
static uint8_t s_selected_finger = 0;
static uint8_t s_last_grip = 0;
static bool s_blink_triggered = false;
static uint8_t s_blink_cooldown = 0;

static const uint8_t DEFAULT_OPEN[SERVO_COUNT]  = {30, 10, 10, 10, 10};
static const uint8_t DEFAULT_CLOSED[SERVO_COUNT] = {150, 170, 170, 170, 160};

void command_interpreter_init(const brain_map_config_t *config)
{
    if (config) {
        s_config = *config;
    } else {
        s_config.attention_threshold_low  = 30;
        s_config.attention_threshold_high = 70;
        s_config.blink_threshold          = 80;
        s_config.smoothing_factor         = 40;
        s_config.min_grip                 = 0;
        s_config.max_grip                 = 100;
    }
    s_mode = MODE_GRIP;
    s_selected_finger = 0;
    s_last_grip = 0;
    s_blink_cooldown = 0;
    ESP_LOGI(TAG, "Command interpreter initialized in GRIP mode");
}

void command_interpreter_set_mode(control_mode_t mode)
{
    s_mode = mode;
    ESP_LOGI(TAG, "Mode switched to %d", mode);
}

control_mode_t command_interpreter_get_mode(void)
{
    return s_mode;
}

void command_interpreter_set_config(const brain_map_config_t *config)
{
    if (config) s_config = *config;
}

const brain_map_config_t *command_interpreter_get_config(void)
{
    return &s_config;
}

static uint8_t apply_smoothing(uint8_t current, uint8_t target, uint8_t factor)
{
    if (factor >= 100) return target;
    return current + ((int16_t)(target - current) * factor / 100);
}

static bool detect_blink(const tgam_data_t *eeg)
{
    if (s_blink_cooldown > 0) {
        s_blink_cooldown--;
        return false;
    }
    if (eeg->blink_strength > s_config.blink_threshold) {
        s_blink_cooldown = 20;
        return true;
    }
    return false;
}

static void process_grip_mode(const tgam_data_t *eeg)
{
    uint8_t grip = eeg->attention;
    if (grip < s_config.attention_threshold_low)
        grip = 0;
    else if (grip > s_config.attention_threshold_high)
        grip = 100;
    else
        grip = (grip - s_config.attention_threshold_low) * 100 /
               (s_config.attention_threshold_high - s_config.attention_threshold_low);

    grip = apply_smoothing(s_last_grip, grip, s_config.smoothing_factor);
    s_last_grip = grip;

    uint8_t angles[SERVO_COUNT];
    for (int i = 0; i < SERVO_COUNT; i++) {
        angles[i] = DEFAULT_OPEN[i] +
            (uint32_t)(DEFAULT_CLOSED[i] - DEFAULT_OPEN[i]) * grip / 100;
    }

    if (detect_blink(eeg))
        grip > 50 ? servo_smooth_all(DEFAULT_OPEN, 300) :
                    servo_smooth_all(DEFAULT_CLOSED, 300);
    else
        servo_set_all(angles);
}

static void process_finger_select_mode(const tgam_data_t *eeg)
{
    uint8_t attention = eeg->attention;
    uint8_t meditation = eeg->meditation;

    if (attention > 60 && meditation < 40) {
        s_selected_finger = 0;
    } else if (attention > 60 && meditation >= 40) {
        s_selected_finger = 1;
    } else if (attention < 40 && meditation > 60) {
        s_selected_finger = 2;
    } else if (attention >= 40 && attention <= 60) {
        s_selected_finger = 3;
    }

    if (detect_blink(eeg)) {
        s_selected_finger = (s_selected_finger + 1) % SERVO_COUNT;
        ESP_LOGI(TAG, "Selected finger: %d", s_selected_finger);
    }

    uint8_t angle;
    if (meditation > 50) {
        angle = DEFAULT_OPEN[s_selected_finger];
    } else {
        uint8_t range = DEFAULT_CLOSED[s_selected_finger] - DEFAULT_OPEN[s_selected_finger];
        angle = DEFAULT_OPEN[s_selected_finger] +
            (uint32_t)range * (50 - meditation) / 50;
    }

    servo_smooth_to((servo_id_t)s_selected_finger, angle, 200);
}

static uint8_t s_seq_step = 0;
static uint32_t s_seq_last_advance = 0;
static uint8_t s_seq_att_hold = 0;

static const uint8_t SEQUENCE_POSES[][SERVO_COUNT] = {
    {30,  10,  10,  10,  10},
    {150, 170, 170, 170, 160},
    {30,  170, 10,  10,  10},
    {150, 170, 10,  10,  10},
    {30,  170, 170, 10,  10},
    {150, 170, 10,  10,  30},
    {30,  10,  170, 170, 10},
    {150, 170, 170, 170, 160},
};

#define SEQUENCE_STEPS (sizeof(SEQUENCE_POSES) / sizeof(SEQUENCE_POSES[0]))
#define SEQ_HOLD_MS    800
#define SEQ_ADVANCE_ATT_THR 55

static void process_sequence_mode(const tgam_data_t *eeg)
{
    uint32_t now = xTaskGetTickCount() * portTICK_PERIOD_MS;

    if (eeg->attention >= SEQ_ADVANCE_ATT_THR) {
        s_seq_att_hold++;
        if (s_seq_att_hold > 3 && (now - s_seq_last_advance) > SEQ_HOLD_MS) {
            s_seq_step = (s_seq_step + 1) % SEQUENCE_STEPS;
            s_seq_last_advance = now;
            s_seq_att_hold = 0;
            ESP_LOGI(TAG, "Sequence advanced to step %d/%d", s_seq_step + 1, SEQUENCE_STEPS);
        }
    } else {
        s_seq_att_hold = 0;
    }

    uint8_t angle;
    if (eeg->meditation > 50) {
        angle = servo_get_angle(SERVO_THUMB);
    } else {
        uint8_t grip = (50 - eeg->meditation) * 100 / 50;
        if (grip > 100) grip = 100;
        uint8_t open = SEQUENCE_POSES[s_seq_step][0];
        uint8_t closed = SEQUENCE_POSES[s_seq_step][0] > 90 ? 30 : 170;
        angle = open + (uint32_t)(closed - open) * grip / 100;
    }

    servo_set_angle(SERVO_THUMB, angle);

    if (eeg->blink_strength > 80) {
        s_seq_step = 0;
        s_seq_last_advance = now;
        ESP_LOGI(TAG, "Sequence reset to step 1 via blink");
    }
}

static void process_calibrate_mode(const tgam_data_t *eeg)
{
    ESP_LOGI(TAG, "Signal=%d Att=%d Med=%d Blink=%d",
             eeg->poor_signal_quality,
             eeg->attention,
             eeg->meditation,
             eeg->blink_strength);
}

void command_interpreter_process(const tgam_data_t *eeg)
{
    if (!eeg || eeg->poor_signal_quality > 0) return;

    switch (s_mode) {
    case MODE_GRIP:
        process_grip_mode(eeg);
        break;
    case MODE_FINGER_SELECT:
        process_finger_select_mode(eeg);
        break;
    case MODE_SEQUENCE:
        process_sequence_mode(eeg);
        break;
    case MODE_CALIBRATE:
        process_calibrate_mode(eeg);
        break;
    }
}
