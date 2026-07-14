#pragma once
#include <stdint.h>
#include <stdbool.h>
#include "servo_controller.h"

typedef struct {
    uint8_t target_angle;
    uint16_t duration_ms;
    float elapsed_ratio;
    bool active;
    uint8_t start_angle;
} motion_plan_t;

void motion_planner_init(void);
void motion_planner_set_target(servo_id_t servo, uint8_t target, uint16_t duration_ms);
bool motion_planner_update(uint8_t *out_angles);
void motion_planner_stop_all(void);
bool motion_planner_is_active(void);
