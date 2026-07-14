#include "tgam_protocol.h"
#include <string.h>

void tgam_parser_init(tgam_parser_t *parser)
{
    parser->state = TGAM_SYNC1;
    parser->payload_length = 0;
    parser->payload_index = 0;
    parser->checksum = 0;
}

static void parse_data_row(tgam_data_t *out, uint8_t code, uint8_t *value, uint8_t len)
{
    switch (code) {
    case TGAM_CODE_POOR_SIGNAL:
        out->poor_signal_quality = (int16_t)value[0];
        break;
    case TGAM_CODE_ATTENTION:
        out->attention = value[0];
        out->has_new_data = true;
        break;
    case TGAM_CODE_MEDITATION:
        out->meditation = value[0];
        break;
    case TGAM_CODE_BLINK:
        out->blink_strength = value[0];
        break;
    case TGAM_CODE_RAW_WAVE:
        out->raw_wave = (int16_t)((value[0] << 8) | value[1]);
        break;
    case TGAM_CODE_EEG_POWER:
        if (len >= 24) {
            out->eeg_power.delta      = ((uint32_t)value[0] << 16) | ((uint32_t)value[1] << 8) | value[2];
            out->eeg_power.theta      = ((uint32_t)value[3] << 16) | ((uint32_t)value[4] << 8) | value[5];
            out->eeg_power.low_alpha  = ((uint32_t)value[6] << 16) | ((uint32_t)value[7] << 8) | value[8];
            out->eeg_power.high_alpha = ((uint32_t)value[9] << 16) | ((uint32_t)value[10] << 8) | value[11];
            out->eeg_power.low_beta   = ((uint32_t)value[12] << 16) | ((uint32_t)value[13] << 8) | value[14];
            out->eeg_power.high_beta  = ((uint32_t)value[15] << 16) | ((uint32_t)value[16] << 8) | value[17];
            out->eeg_power.low_gamma  = ((uint32_t)value[18] << 16) | ((uint32_t)value[19] << 8) | value[20];
            out->eeg_power.high_gamma = ((uint32_t)value[21] << 16) | ((uint32_t)value[22] << 8) | value[23];
        }
        break;
    }
}

bool tgam_parse_byte(tgam_parser_t *parser, uint8_t byte, tgam_data_t *out)
{
    switch (parser->state) {
    case TGAM_SYNC1:
        if (byte == TGAM_SYNC_BYTE1)
            parser->state = TGAM_SYNC2;
        break;
    case TGAM_SYNC2:
        if (byte == TGAM_SYNC_BYTE2) {
            parser->state = TGAM_LENGTH;
        } else if (byte != TGAM_SYNC_BYTE1) {
            parser->state = TGAM_SYNC1;
        }
        break;
    case TGAM_LENGTH:
        parser->payload_length = byte;
        if (parser->payload_length == 0 || parser->payload_length > 255) {
            parser->state = TGAM_SYNC1;
        } else {
            parser->payload_index = 0;
            parser->checksum = 0;
            parser->state = TGAM_PAYLOAD;
        }
        break;
    case TGAM_PAYLOAD:
        parser->payload[parser->payload_index++] = byte;
        parser->checksum += byte;
        if (parser->payload_index >= parser->payload_length)
            parser->state = TGAM_CHECKSUM;
        break;
    case TGAM_CHECKSUM:
    {
        uint8_t expected_checksum = (uint8_t)(~parser->checksum);
        if (byte == expected_checksum) {
            uint8_t i = 0;
            while (i < parser->payload_length) {
                uint8_t code = parser->payload[i++];
                uint8_t len;
                uint8_t value[24];
                if (code & 0x80) {
                    if (i >= parser->payload_length) break;
                    len = parser->payload[i++];
                } else {
                    len = 1;
                }
                if (i + len > parser->payload_length) break;
                memcpy(value, &parser->payload[i], len);
                i += len;
                parse_data_row(out, code, value, len);
            }
        }
        parser->state = TGAM_SYNC1;
        break;
    }
    }
    return false;
}
