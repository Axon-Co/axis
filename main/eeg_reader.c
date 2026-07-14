#include "eeg_reader.h"
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/uart.h"
#include "driver/gpio.h"
#include "esp_log.h"

static const char *TAG = "EEG_Reader";

static tgam_data_t s_latest_data;
static tgam_parser_t s_parser;
static SemaphoreHandle_t s_data_mutex;

static void uart_event_task(void *pvParameters)
{
    uart_event_t event;
    QueueHandle_t uart_queue;

    uart_driver_install(TGAM_UART_PORT, 256, 0, 16, &uart_queue, 0);

    uint8_t byte;
    while (1) {
        if (xQueueReceive(uart_queue, &event, portMAX_DELAY)) {
            if (event.type == UART_DATA) {
                int len = uart_read_bytes(TGAM_UART_PORT, &byte, 1, 0);
                while (len > 0) {
                    if (xSemaphoreTake(s_data_mutex, portMAX_DELAY)) {
                        tgam_parse_byte(&s_parser, byte, &s_latest_data);
                        xSemaphoreGive(s_data_mutex);
                    }
                    len = uart_read_bytes(TGAM_UART_PORT, &byte, 1, 0);
                }
            }
        }
    }
}

void eeg_reader_init(void)
{
    s_data_mutex = xSemaphoreCreateMutex();

    uart_config_t uart_config = {
        .baud_rate = TGAM_BAUD_RATE,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };

    uart_param_config(TGAM_UART_PORT, &uart_config);
    uart_set_pin(TGAM_UART_PORT, TGAM_TX_PIN, TGAM_RX_PIN, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);

    tgam_parser_init(&s_parser);

    xTaskCreate(uart_event_task, "eeg_reader", 4096, NULL, 10, NULL);

    ESP_LOGI(TAG, "EEG reader initialized on UART2, baud=%d", TGAM_BAUD_RATE);
}

tgam_data_t eeg_reader_get_latest(void)
{
    tgam_data_t data;
    if (xSemaphoreTake(s_data_mutex, pdMS_TO_TICKS(100))) {
        data = s_latest_data;
        s_latest_data.has_new_data = false;
        xSemaphoreGive(s_data_mutex);
    }
    return data;
}

void eeg_reader_reset(void)
{
    if (xSemaphoreTake(s_data_mutex, portMAX_DELAY)) {
        tgam_parser_init(&s_parser);
        memset(&s_latest_data, 0, sizeof(s_latest_data));
        xSemaphoreGive(s_data_mutex);
    }
}
