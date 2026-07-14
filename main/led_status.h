#pragma once
#include <stdint.h>
#include <stdbool.h>

typedef enum {
    LED_OFF = 0,
    LED_NORMAL,
    LED_POOR_SIGNAL,
    LED_EMERGENCY,
    LED_WIFI_ACTIVE,
    LED_LOGGING,
    LED_BOOTING,
    LED_ERROR,
    LED_CALIBRATING,
    LED_GESTURE
} led_state_t;

void led_status_init(int gpio_red, int gpio_green, int gpio_blue);
void led_status_set(led_state_t state);
void led_status_blink(led_state_t state, uint16_t interval_ms);
void led_status_off(void);
