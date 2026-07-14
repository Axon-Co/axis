#pragma once
#include <stdint.h>
#include <stdbool.h>

#define TGAM_BAUD_RATE 57600
#define TGAM_UART_PORT UART_NUM_2
#define TGAM_RX_PIN    GPIO_NUM_16
#define TGAM_TX_PIN    UART_PIN_NO_CHANGE

#define TGAM_SYNC_BYTE1 0xAA
#define TGAM_SYNC_BYTE2 0xAA

#define TGAM_CODE_POOR_SIGNAL  0x02
#define TGAM_CODE_ATTENTION    0x04
#define TGAM_CODE_MEDITATION   0x05
#define TGAM_CODE_BLINK        0x16
#define TGAM_CODE_RAW_WAVE     0x80
#define TGAM_CODE_EEG_POWER    0x83

typedef struct {
    int16_t poor_signal_quality;
    uint8_t attention;
    uint8_t meditation;
    uint8_t blink_strength;
    int16_t raw_wave;
    struct {
        uint32_t delta;
        uint32_t theta;
        uint32_t low_alpha;
        uint32_t high_alpha;
        uint32_t low_beta;
        uint32_t high_beta;
        uint32_t low_gamma;
        uint32_t high_gamma;
    } eeg_power;
    bool has_new_data;
} tgam_data_t;

typedef enum {
    TGAM_SYNC1,
    TGAM_SYNC2,
    TGAM_LENGTH,
    TGAM_PAYLOAD,
    TGAM_CHECKSUM
} tgam_parse_state_t;

typedef struct {
    tgam_parse_state_t state;
    uint8_t payload[256];
    uint8_t payload_length;
    uint8_t payload_index;
    uint8_t checksum;
} tgam_parser_t;

void tgam_parser_init(tgam_parser_t *parser);
bool tgam_parse_byte(tgam_parser_t *parser, uint8_t byte, tgam_data_t *out);
