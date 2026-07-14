#include "motion_planner.h"
#include "esp_log.h"

static const char *TAG = "MotionPlan";

static motion_plan_t s_plans[SERVO_COUNT];

void motion_planner_init(void)
{
    for (int i = 0; i < SERVO_COUNT; i++) {
        s_plans[i].active = false;
        s_plans[i].elapsed_ratio = 1.0f;
    }
}

static float s_curve(float t)
{
    if (t <= 0.0f) return 0.0f;
    if (t >= 1.0f) return 1.0f;
    return t * t * (3.0f - 2.0f * t);
}

void motion_planner_set_target(servo_id_t servo, uint8_t target, uint16_t duration_ms)
{
    if (servo >= SERVO_COUNT) return;
    s_plans[servo].target_angle = target;
    s_plans[servo].duration_ms = duration_ms;
    s_plans[servo].elapsed_ratio = 0.0f;
    s_plans[servo].active = true;
    s_plans[servo].start_angle = servo_get_angle(servo);
}

bool motion_planner_update(uint8_t *out_angles)
{
    bool any_active = false;

    for (int i = 0; i < SERVO_COUNT; i++) {
        motion_plan_t *p = &s_plans[i];

        if (!p->active) {
            out_angles[i] = servo_get_angle((servo_id_t)i);
            continue;
        }

        p->elapsed_ratio += 0.02f / (p->duration_ms / 1000.0f);

        if (p->elapsed_ratio >= 1.0f) {
            p->elapsed_ratio = 1.0f;
            p->active = false;
            out_angles[i] = p->target_angle;
        } else {
            float t = s_curve(p->elapsed_ratio);
            float range = (float)((int)p->target_angle - (int)p->start_angle);
            out_angles[i] = (uint8_t)(p->start_angle + range * t);
            any_active = true;
        }
    }

    return !any_active;
}

void motion_planner_stop_all(void)
{
    for (int i = 0; i < SERVO_COUNT; i++) {
        s_plans[i].active = false;
    }
}

bool motion_planner_is_active(void)
{
    for (int i = 0; i < SERVO_COUNT; i++) {
        if (s_plans[i].active) return true;
    }
    return false;
}
