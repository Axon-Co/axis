#pragma once
#include "tgam_protocol.h"
#include <stdint.h>

typedef enum {
    MODE_GRIP,           
    MODE_FINGER_SELECT,  
    MODE_SEQUENCE,       
    MODE_CALIBRATE       
} control_mode_t;

typedef struct {
    uint8_t attention_threshold_low;
    uint8_t attention_threshold_high;
    uint8_t blink_threshold;
    uint8_t smoothing_factor;
    uint8_t min_grip;
    uint8_t max_grip;
} brain_map_config_t;

void command_interpreter_init(const brain_map_config_t *config);
void command_interpreter_set_mode(control_mode_t mode);
control_mode_t command_interpreter_get_mode(void);
void command_interpreter_process(const tgam_data_t *eeg);
void command_interpreter_set_config(const brain_map_config_t *config);
const brain_map_config_t *command_interpreter_get_config(void);
