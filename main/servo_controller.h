#pragma once
#include <stdint.h>
#include <stdbool.h>

#define SERVO_COUNT      5
#define SERVO_MIN_PULSE  500
#define SERVO_MAX_PULSE  2500
#define SERVO_FREQUENCY  50

typedef enum {
    SERVO_THUMB  = 0,
    SERVO_INDEX  = 1,
    SERVO_MIDDLE = 2,
    SERVO_RING   = 3,
    SERVO_PINKY  = 4
} servo_id_t;

typedef struct {
    int gpio_pin;
    uint8_t min_angle;
    uint8_t max_angle;
    uint8_t home_position;
    bool    invert;
} servo_config_t;

void servo_controller_init(const servo_config_t *configs);
void servo_set_angle(servo_id_t servo, uint8_t angle);
void servo_set_all(const uint8_t *angles);
void servo_smooth_to(servo_id_t servo, uint8_t target, uint16_t duration_ms);
void servo_smooth_all(const uint8_t *targets, uint16_t duration_ms);
void servo_set_speed(uint8_t speed);
uint8_t servo_get_angle(servo_id_t servo);
void servo_enable(bool on);
