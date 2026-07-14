#pragma once
#include <stdint.h>
#include <stdbool.h>
#include "tgam_protocol.h"
#include "servo_controller.h"

typedef struct {
    uint64_t uptime_ms;
    uint32_t total_eeg_packets;
    uint32_t dropped_packets;
    uint32_t error_count;
    uint32_t recovery_count;
    uint32_t emergency_stops;

    struct {
        uint8_t min;
        uint8_t max;
        uint8_t avg;
    } attention_stats;

    struct {
        uint8_t min;
        uint8_t max;
        uint8_t avg;
    } meditation_stats;

    int32_t min_heap_free;
    uint32_t wifi_reconnects;
} diagnostics_t;

void diagnostics_init(void);
void diagnostics_update_eeg(const tgam_data_t *eeg);
void diagnostics_increment_error(void);
void diagnostics_increment_recovery(void);
void diagnostics_increment_emergency_stop(void);
void diagnostics_increment_wifi_reconnect(void);
void diagnostics_update_heap(void);
void diagnostics_reset_stats(void);
const diagnostics_t *diagnostics_get(void);
uint64_t diagnostics_get_uptime_ms(void);
