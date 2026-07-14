#include "servo_controller.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/ledc.h"
#include "esp_log.h"

static const char *TAG = "ServoCtrl";

#define LEDC_TIMER        LEDC_TIMER_0
#define LEDC_SPEED_MODE   LEDC_LOW_SPEED_MODE
#define LEDC_DUTY_RES     LEDC_TIMER_13_BIT

static uint8_t s_current_angles[SERVO_COUNT];
static uint8_t s_speed = 128;
static bool s_enabled = false;

static const servo_config_t *s_configs = NULL;

static uint32_t angle_to_duty(uint8_t angle, const servo_config_t *cfg)
{
    if (angle < cfg->min_angle) angle = cfg->min_angle;
    if (angle > cfg->max_angle) angle = cfg->max_angle;

    if (cfg->invert)
        angle = cfg->max_angle - (angle - cfg->min_angle);

    uint32_t pulse = SERVO_MIN_PULSE +
        (uint32_t)(SERVO_MAX_PULSE - SERVO_MIN_PULSE) * angle / 180;

    return (pulse * (1 << LEDC_DUTY_RES)) / 20000;
}

void servo_controller_init(const servo_config_t *configs)
{
    s_configs = configs;

    ledc_timer_config_t timer = {
        .speed_mode      = LEDC_SPEED_MODE,
        .timer_num       = LEDC_TIMER,
        .duty_resolution = LEDC_DUTY_RES,
        .freq_hz         = SERVO_FREQUENCY,
        .clk_cfg         = LEDC_AUTO_CLK
    };
    ledc_timer_config(&timer);

    for (int i = 0; i < SERVO_COUNT; i++) {
        ledc_channel_config_t ch = {
            .gpio_num   = configs[i].gpio_pin,
            .speed_mode = LEDC_SPEED_MODE,
            .channel    = (ledc_channel_t)i,
            .timer_sel  = LEDC_TIMER,
            .duty       = 0,
            .hpoint     = 0
        };
        ledc_channel_config(&ch);
        s_current_angles[i] = configs[i].home_position;
        uint32_t duty = angle_to_duty(configs[i].home_position, &configs[i]);
        ledc_set_duty(LEDC_SPEED_MODE, (ledc_channel_t)i, duty);
        ledc_update_duty(LEDC_SPEED_MODE, (ledc_channel_t)i);
    }

    s_enabled = true;
    ESP_LOGI(TAG, "Servo controller initialized, %d channels", SERVO_COUNT);
}

void servo_set_angle(servo_id_t servo, uint8_t angle)
{
    if (!s_enabled || servo >= SERVO_COUNT) return;
    s_current_angles[servo] = angle;
    uint32_t duty = angle_to_duty(angle, &s_configs[servo]);
    ledc_set_duty(LEDC_SPEED_MODE, (ledc_channel_t)servo, duty);
    ledc_update_duty(LEDC_SPEED_MODE, (ledc_channel_t)servo);
}

void servo_set_all(const uint8_t *angles)
{
    for (int i = 0; i < SERVO_COUNT; i++)
        servo_set_angle((servo_id_t)i, angles[i]);
}

void servo_smooth_to(servo_id_t servo, uint8_t target, uint16_t duration_ms)
{
    if (!s_enabled || servo >= SERVO_COUNT) return;
    uint8_t start = s_current_angles[servo];
    if (start == target) return;

    int steps = (duration_ms * s_speed) / 256;
    if (steps < 2) steps = 2;
    int delay_ms = duration_ms / steps;

    int diff = (int)target - (int)start;
    for (int i = 1; i <= steps; i++) {
        uint8_t angle = start + (diff * i / steps);
        servo_set_angle(servo, angle);
        vTaskDelay(pdMS_TO_TICKS(delay_ms));
    }
    servo_set_angle(servo, target);
}

void servo_smooth_all(const uint8_t *targets, uint16_t duration_ms)
{
    uint8_t start[SERVO_COUNT];
    for (int i = 0; i < SERVO_COUNT; i++)
        start[i] = s_current_angles[i];

    int steps = (duration_ms * s_speed) / 256;
    if (steps < 2) steps = 2;
    int delay_ms = duration_ms / steps;

    for (int s = 1; s <= steps; s++) {
        for (int i = 0; i < SERVO_COUNT; i++) {
            int diff = (int)targets[i] - (int)start[i];
            uint8_t angle = start[i] + (diff * s / steps);
            servo_set_angle((servo_id_t)i, angle);
        }
        vTaskDelay(pdMS_TO_TICKS(delay_ms));
    }
    servo_set_all(targets);
}

void servo_set_speed(uint8_t speed)
{
    s_speed = speed;
}

uint8_t servo_get_angle(servo_id_t servo)
{
    if (servo >= SERVO_COUNT) return 0;
    return s_current_angles[servo];
}

void servo_enable(bool on)
{
    s_enabled = on;
    for (int i = 0; i < SERVO_COUNT; i++) {
        if (on) {
            uint32_t duty = angle_to_duty(s_current_angles[i], &s_configs[i]);
            ledc_set_duty(LEDC_SPEED_MODE, (ledc_channel_t)i, duty);
        } else {
            ledc_set_duty(LEDC_SPEED_MODE, (ledc_channel_t)i, 0);
        }
        ledc_update_duty(LEDC_SPEED_MODE, (ledc_channel_t)i);
    }
}
