#include "gesture_player.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "Gesture";

static const gesture_frame_t open_hand[] = {
    {{30, 10, 10, 10, 10}, 500},
};

static const gesture_frame_t fist[] = {
    {{150, 170, 170, 170, 160}, 500},
};

static const gesture_frame_t point[] = {
    {{30, 170, 10, 10, 10}, 400},
};

static const gesture_frame_t pinch[] = {
    {{150, 170, 10, 10, 10}, 400},
};

static const gesture_frame_t peace[] = {
    {{30, 170, 170, 10, 10}, 400},
};

static const gesture_frame_t ok_sign[] = {
    {{150, 170, 10, 10, 30}, 400},
};

static const gesture_frame_t wave_motion[] = {
    {{30,  10, 10, 10, 10}, 300},
    {{150, 170, 170, 170, 160}, 300},
    {{30,  10, 10, 10, 10}, 300},
    {{150, 170, 170, 170, 160}, 300},
};

static const gesture_t gesture_database[] = {
    {"Open",  1, open_hand},
    {"Fist",  1, fist},
    {"Point", 1, point},
    {"Pinch", 1, pinch},
    {"Peace", 1, peace},
    {"OK",    1, ok_sign},
    {"Wave",  4, wave_motion},
};

#define GESTURE_COUNT (sizeof(gesture_database) / sizeof(gesture_database[0]))

static bool s_is_playing = false;
static int s_current_gesture = -1;

void gesture_player_init(void)
{
    ESP_LOGI(TAG, "Gesture player initialized with %d gestures", GESTURE_COUNT);
}

bool gesture_player_play(uint8_t gesture_id)
{
    if (gesture_id >= GESTURE_COUNT) {
        ESP_LOGW(TAG, "Invalid gesture ID: %d", gesture_id);
        return false;
    }

    s_is_playing = true;
    s_current_gesture = gesture_id;

    const gesture_t *g = &gesture_database[gesture_id];
    ESP_LOGI(TAG, "Playing gesture: %s (%d frames)", g->name, g->frame_count);

    for (int f = 0; f < g->frame_count; f++) {
        if (!s_is_playing) break;
        servo_smooth_all(g->frames[f].angles, g->frames[f].transition_ms);
        vTaskDelay(pdMS_TO_TICKS(g->frames[f].transition_ms + 50));
    }

    s_is_playing = false;
    s_current_gesture = -1;
    return true;
}

void gesture_player_stop(void)
{
    s_is_playing = false;
}

int gesture_player_count(void)
{
    return GESTURE_COUNT;
}

const char *gesture_player_name(int id)
{
    if (id >= 0 && id < GESTURE_COUNT)
        return gesture_database[id].name;
    return NULL;
}

bool gesture_player_is_playing(void)
{
    return s_is_playing;
}
