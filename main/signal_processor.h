#pragma once
#include <stdint.h>
#include <stdbool.h>
#include "tgam_protocol.h"

#define MOVING_AVG_WINDOW 8
#define BLINK_HISTORY_SIZE 16

typedef struct {
    uint8_t attention;
    uint8_t meditation;
    uint8_t blink_strength;
    int16_t raw_wave;
    float alpha_beta_ratio;
    float theta_gamma_ratio;
    float attention_relax_index;
    float signal_quality;
    bool is_blink;
    bool is_double_blink;
    uint8_t adaptive_att_threshold_low;
    uint8_t adaptive_att_threshold_high;
    uint8_t adaptive_blink_threshold;
} processed_signal_t;

void signal_processor_init(void);
void signal_processor_feed(const tgam_data_t *raw, processed_signal_t *out);
void signal_processor_reset(void);
