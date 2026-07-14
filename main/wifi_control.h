#pragma once
#include <stdint.h>
#include <stdbool.h>
#include "tgam_protocol.h"
#include "servo_controller.h"

void wifi_control_init(const char *ssid, const char *password, uint8_t channel);
void wifi_control_broadcast(const tgam_data_t *eeg, const uint8_t *servo_angles);
void wifi_control_stop(void);
bool wifi_control_is_connected(void);
int  wifi_control_client_count(void);
