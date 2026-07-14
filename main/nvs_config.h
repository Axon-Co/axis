#pragma once
#include <stdint.h>
#include <stdbool.h>
#include "servo_controller.h"
#include "command_interpreter.h"

#define NVS_NAMESPACE "espbrain"
#define WIFI_SSID_MAX  32
#define WIFI_PASS_MAX  64

typedef struct {
    brain_map_config_t brain;
    struct {
        uint8_t min_angle[SERVO_COUNT];
        uint8_t max_angle[SERVO_COUNT];
        uint8_t home_position[SERVO_COUNT];
        bool    invert[SERVO_COUNT];
    } servo;
    struct {
        char ssid[WIFI_SSID_MAX];
        char password[WIFI_PASS_MAX];
        uint8_t channel;
        bool enabled;
    } wifi;
    struct {
        bool enabled;
        uint8_t rate_hz;
    } logging;
    struct {
        uint16_t signal_loss_timeout_ms;
        uint16_t poor_quality_timeout_ms;
    } safety;
    control_mode_t default_mode;
    uint8_t system_speed;
} app_config_t;

void nvs_config_init(void);
void nvs_config_load(app_config_t *cfg);
void nvs_config_save(const app_config_t *cfg);
void nvs_config_reset(void);
const app_config_t *nvs_config_get(void);
