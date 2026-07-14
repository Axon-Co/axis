#include "wifi_control.h"
#include "command_interpreter.h"
#include "nvs_config.h"
#include "gesture_player.h"
#include "safety_monitor.h"
#include "esp_log.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_http_server.h"
#include "nvs_flash.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include <string.h>
#include <stdio.h>

static const char *TAG = "WiFiCtrl";

#define WS_MAX_CLIENTS 8
#define WIFI_MAX_RETRY 5

static bool s_initialized = false;
static int s_client_count = 0;

static httpd_handle_t s_server = NULL;
static int s_client_fds[WS_MAX_CLIENTS];

static void ws_broadcast(const char *data, size_t len)
{
    for (int i = 0; i < WS_MAX_CLIENTS; i++) {
        if (s_client_fds[i] >= 0) {
            httpd_ws_frame_t ws = {
                .type = HTTPD_WS_TYPE_TEXT,
                .payload = (uint8_t *)data,
                .len = len,
            };
            httpd_ws_send_frame_async(s_server, s_client_fds[i], &ws);
        }
    }
}

static void ws_remove_fd(int fd)
{
    for (int i = 0; i < WS_MAX_CLIENTS; i++) {
        if (s_client_fds[i] == fd) {
            s_client_fds[i] = -1;
            s_client_count--;
            break;
        }
    }
}

static void ws_add_fd(int fd)
{
    for (int i = 0; i < WS_MAX_CLIENTS; i++) {
        if (s_client_fds[i] < 0) {
            s_client_fds[i] = fd;
            s_client_count++;
            return;
        }
    }
    ESP_LOGW(TAG, "Max WS clients reached");
    s_client_count++;
}

static void broadcast_eeg(const tgam_data_t *eeg, const uint8_t *servo_angles)
{
    char buf[512];
    int len = snprintf(buf, sizeof(buf),
        "{\"type\":\"eeg\",\"att\":%u,\"med\":%u,\"blink\":%u,\"signal\":%d,"
        "\"servos\":[%u,%u,%u,%u,%u],\"mode\":%d}\n",
        eeg->attention, eeg->meditation, eeg->blink_strength,
        eeg->poor_signal_quality,
        servo_angles[0], servo_angles[1], servo_angles[2],
        servo_angles[3], servo_angles[4],
        command_interpreter_get_mode());

    ws_broadcast(buf, len);
}

static void handle_ws_cmd(const char *data, size_t len)
{
    char cmd[64];
    int int_val = 0;

    if (sscanf(data, "{\"cmd\":\"mode\",\"value\":%d}", &int_val) == 1) {
        if (int_val >= 0 && int_val <= 3)
            command_interpreter_set_mode((control_mode_t)int_val);
        return;
    }

    int servo_id = 0, angle = 0;
    if (sscanf(data, "{\"cmd\":\"servo\",\"id\":%d,\"angle\":%d}", &servo_id, &angle) == 2) {
        if (servo_id >= 0 && servo_id < SERVO_COUNT && angle >= 0 && angle <= 180)
            servo_set_angle((servo_id_t)servo_id, (uint8_t)angle);
        return;
    }

    if (sscanf(data, "{\"cmd\":\"gesture\",\"id\":%d}", &int_val) == 1) {
        gesture_player_play((uint8_t)int_val);
        return;
    }

    float fval;
    if (sscanf(data, "{\"cmd\":\"config\",\"key\":\"%63[^\"]\",\"value\":%f}",
               cmd, &fval) >= 2) {
        app_config_t cfg;
        nvs_config_load(&cfg);
        if (strcmp(cmd, "smoothing_factor") == 0)
            cfg.brain.smoothing_factor = (uint8_t)fval;
        else if (strcmp(cmd, "attention_threshold_low") == 0)
            cfg.brain.attention_threshold_low = (uint8_t)fval;
        else if (strcmp(cmd, "attention_threshold_high") == 0)
            cfg.brain.attention_threshold_high = (uint8_t)fval;
        else if (strcmp(cmd, "blink_threshold") == 0)
            cfg.brain.blink_threshold = (uint8_t)fval;
        else if (strcmp(cmd, "system_speed") == 0)
            cfg.system_speed = (uint8_t)fval;
        command_interpreter_set_config(&cfg.brain);
        nvs_config_save(&cfg);
        return;
    }

    if (strstr(data, "\"cmd\":\"stop\"")) {
        safety_monitor_emergency_stop();
        return;
    }
    if (strstr(data, "\"cmd\":\"release\"")) {
        safety_monitor_release();
        return;
    }
}

static esp_err_t ws_handler(httpd_req_t *req)
{
    if (req->method == HTTP_GET) {
        ESP_LOGI(TAG, "WS client connected");
        ws_add_fd(httpd_req_to_sockfd(req));

        char buf[128];
        snprintf(buf, sizeof(buf),
            "{\"type\":\"info\",\"servo_count\":%d,\"gestures\":%d}\n",
            SERVO_COUNT, gesture_player_count());
        httpd_ws_frame_t ws = {
            .type = HTTPD_WS_TYPE_TEXT,
            .payload = (uint8_t *)buf,
            .len = strlen(buf),
        };
        httpd_ws_send_frame(req, &ws);
        return ESP_OK;
    }

    httpd_ws_frame_t ws;
    memset(&ws, 0, sizeof(ws));
    ws.type = HTTPD_WS_TYPE_TEXT;
    uint8_t buf[256];

    esp_err_t ret = httpd_ws_recv_frame(req, &ws, sizeof(buf));
    if (ret != ESP_OK) {
        ws_remove_fd(httpd_req_to_sockfd(req));
        return ret;
    }

    if (ws.payload && ws.len > 0) {
        memcpy(buf, ws.payload, ws.len);
        buf[ws.len] = '\0';
        handle_ws_cmd((const char *)buf, ws.len);
    }

    return ESP_OK;
}

static esp_err_t root_handler(httpd_req_t *req)
{
    const char *html = "<!DOCTYPE html><html><head><title>EspBrain</title>"
        "<style>body{font-family:monospace;background:#111;color:#0f0;margin:20px}"
        ".val{font-size:24px;font-weight:bold}.bar{height:20px;background:#333;margin:4px 0}"
        ".bar-fill{height:100%;background:#0f0;transition:width .2s}</style></head>"
        "<body><h1>EspBrain BCI</h1>"
        "<div id='data'></div>"
        "<script>var ws=new WebSocket('ws://'+location.host+'/ws');"
        "ws.onmessage=function(e){var d=JSON.parse(e.data);"
        "if(d.type=='eeg'){var h='<h2>EEG</h2>'"
        "+'<div>Attention: <span class=val>'+d.att+'</span>'"
        "+'<div class=bar><div class=bar-fill style=width:'+d.att+'%></div></div>'"
        "+'<div>Meditation: <span class=val>'+d.med+'</span>'"
        "+'<div class=bar><div class=bar-fill style=width:'+d.med+'%></div></div>'"
        "+'<div>Blink: <span class=val>'+d.blink+'</span></div>'"
        "+'<div>Signal: <span class=val>'+d.signal+'</span></div>'"
        "+'<h2>Servos</h2>'";
        "for(var i=0;i<d.servos.length;i++){"
        "h+='<div>Servo '+i+': <span class=val>'+d.servos[i]+'°</span>'"
        "+'<div class=bar><div class=bar-fill style=width:'+(d.servos[i]/1.8)+'%></div></div></div>';}"
        "document.getElementById('data').innerHTML=h;}};</script></body></html>";

    httpd_resp_set_type(req, "text/html");
    httpd_resp_send(req, html, strlen(html));
    return ESP_OK;
}

static void start_webserver(void)
{
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.lru_purge_enable = true;
    config.max_uri_handlers = 8;
    config.server_port = 80;

    for (int i = 0; i < WS_MAX_CLIENTS; i++)
        s_client_fds[i] = -1;

    if (httpd_start(&s_server, &config) != ESP_OK) {
        ESP_LOGE(TAG, "Failed to start HTTP server");
        return;
    }

    httpd_uri_t root_uri = {
        .uri = "/",
        .method = HTTP_GET,
        .handler = root_handler,
    };
    httpd_register_uri_handler(s_server, &root_uri);

    httpd_uri_t ws_uri = {
        .uri = "/ws",
        .method = HTTP_GET,
        .handler = ws_handler,
        .is_websocket = true,
        .handle_ws_control_frames = true,
    };
    httpd_register_uri_handler(s_server, &ws_uri);

    ESP_LOGI(TAG, "WebSocket server started on port 80");
}

static void wifi_event_handler(void *arg, esp_event_base_t base,
                                int32_t id, void *data)
{
    if (base == WIFI_EVENT && id == WIFI_EVENT_AP_STACONNECTED) {
        wifi_event_ap_staconnected_t *ev = (wifi_event_ap_staconnected_t *)data;
        ESP_LOGI(TAG, "Station connected: " MACSTR, MAC2STR(ev->mac));
    }
    if (base == WIFI_EVENT && id == WIFI_EVENT_AP_STADISCONNECTED) {
        ESP_LOGI(TAG, "Station disconnected");
    }
}

void wifi_control_init(const char *ssid, const char *password, uint8_t channel)
{
    if (s_initialized) return;

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());

    esp_netif_create_default_wifi_ap();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID,
                                                &wifi_event_handler, NULL));

    wifi_config_t wifi_config = {
        .ap = {
            .ssid_len = 0,
            .channel = channel,
            .max_connection = WS_MAX_CLIENTS,
            .authmode = WIFI_AUTH_WPA_WPA2_PSK,
            .pmf_cfg = { .required = false },
        },
    };
    strncpy((char *)wifi_config.ap.ssid, ssid, sizeof(wifi_config.ap.ssid) - 1);
    strncpy((char *)wifi_config.ap.password, password, sizeof(wifi_config.ap.password) - 1);

    if (strlen(password) == 0)
        wifi_config.ap.authmode = WIFI_AUTH_OPEN;

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_AP));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());

    ESP_LOGI(TAG, "WiFi AP started: SSID=%s, CH=%d", ssid, channel);

    start_webserver();
    s_initialized = true;
}

void wifi_control_broadcast(const tgam_data_t *eeg, const uint8_t *servo_angles)
{
    if (!s_initialized || !s_server) return;
    broadcast_eeg(eeg, servo_angles);
}

void wifi_control_stop(void)
{
    if (s_server) {
        httpd_stop(s_server);
        s_server = NULL;
    }
    esp_wifi_stop();
    s_initialized = false;
    ESP_LOGI(TAG, "WiFi control stopped");
}

bool wifi_control_is_connected(void)
{
    return s_initialized;
}

int wifi_control_client_count(void)
{
    return s_client_count;
}
