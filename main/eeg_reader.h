#pragma once
#include "tgam_protocol.h"

void eeg_reader_init(void);
tgam_data_t eeg_reader_get_latest(void);
void eeg_reader_reset(void);
