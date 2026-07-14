#pragma once
#include <stdint.h>
#include <stdbool.h>
#include "tgam_protocol.h"
#include "servo_controller.h"

typedef enum {
    LOGGER_IDLE,
    LOGGER_RUNNING,
    LOGGER_ERROR
} logger_state_t;

void data_logger_init(void);
bool data_logger_start(void);
void data_logger_stop(void);
void data_logger_feed(const tgam_data_t *eeg, const uint8_t *servo_angles);
logger_state_t data_logger_get_state(void);
uint32_t data_logger_get_count(void);
void data_logger_set_rate(uint8_t hz);
