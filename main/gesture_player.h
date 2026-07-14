#pragma once
#include <stdint.h>
#include <stdbool.h>
#include "servo_controller.h"

typedef struct {
    uint8_t angles[SERVO_COUNT];
    uint16_t transition_ms;
} gesture_frame_t;

typedef struct {
    const char *name;
    uint8_t frame_count;
    const gesture_frame_t *frames;
} gesture_t;

void gesture_player_init(void);
bool gesture_player_play(uint8_t gesture_id);
void gesture_player_stop(void);
int  gesture_player_count(void);
const char *gesture_player_name(int id);
bool gesture_player_is_playing(void);
