#include "led_status.h"
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

typedef struct { uint8_t r, g, b; } rgb_t;

static const rgb_t STATE_COLORS[] = {
    [LED_OFF]         = {0, 0, 0},
    [LED_NORMAL]      = {0, 1, 0},
    [LED_POOR_SIGNAL] = {1, 1, 0},
    [LED_EMERGENCY]   = {1, 0, 0},
    [LED_WIFI_ACTIVE] = {0, 0, 1},
    [LED_LOGGING]     = {0, 1, 1},
    [LED_BOOTING]     = {0, 0, 1},
    [LED_ERROR]       = {1, 0, 0},
    [LED_CALIBRATING] = {1, 0, 1},
    [LED_GESTURE]     = {0, 1, 0},
};

static struct {
    int pin_r, pin_g, pin_b;
    led_state_t current_state;
    bool blinking;
    uint16_t blink_interval;
} s_led;

static void set_rgb(int r, int g, int b)
{
    gpio_set_level(s_led.pin_r, r);
    gpio_set_level(s_led.pin_g, g);
    gpio_set_level(s_led.pin_b, b);
}

static void led_task(void *pv)
{
    (void)pv;
    while (1) {
        if (s_led.blinking) {
            int half = s_led.blink_interval / 2;
            if (half < 50) half = 50;
            rgb_t c = STATE_COLORS[s_led.current_state];
            set_rgb(c.r, c.g, c.b);
            vTaskDelay(pdMS_TO_TICKS(half));
            set_rgb(0, 0, 0);
            vTaskDelay(pdMS_TO_TICKS(half));
        } else {
            rgb_t c = STATE_COLORS[s_led.current_state];
            set_rgb(c.r, c.g, c.b);
            vTaskDelay(pdMS_TO_TICKS(250));
        }
    }
}

void led_status_init(int gpio_r, int gpio_g, int gpio_b)
{
    s_led.pin_r = gpio_r;
    s_led.pin_g = gpio_g;
    s_led.pin_b = gpio_b;
    s_led.current_state = LED_BOOTING;
    s_led.blinking = true;
    s_led.blink_interval = 150;

    gpio_reset_pin(gpio_r);
    gpio_reset_pin(gpio_g);
    gpio_reset_pin(gpio_b);
    gpio_set_direction(gpio_r, GPIO_MODE_OUTPUT);
    gpio_set_direction(gpio_g, GPIO_MODE_OUTPUT);
    gpio_set_direction(gpio_b, GPIO_MODE_OUTPUT);
    set_rgb(0, 0, 0);

    xTaskCreate(led_task, "led_status", 2048, NULL, 5, NULL);
}

void led_status_set(led_state_t state)
{
    s_led.current_state = state;
    s_led.blinking = false;
}

void led_status_blink(led_state_t state, uint16_t interval_ms)
{
    s_led.current_state = state;
    s_led.blinking = true;
    s_led.blink_interval = interval_ms;
}

void led_status_off(void)
{
    s_led.current_state = LED_OFF;
    s_led.blinking = false;
    set_rgb(0, 0, 0);
}
