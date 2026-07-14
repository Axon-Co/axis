#pragma once
#include <stdint.h>
#include <stdbool.h>
#include "tgam_protocol.h"

void safety_monitor_init(uint16_t signal_loss_ms, uint16_t poor_quality_ms);
void safety_monitor_feed(const tgam_data_t *eeg);
bool safety_monitor_is_safe(void);
void safety_monitor_emergency_stop(void);
void safety_monitor_release(void);
uint32_t safety_monitor_last_signal_ms(void);
