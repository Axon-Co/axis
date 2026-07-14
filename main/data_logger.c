#include "data_logger.h"
#include "esp_log.h"
#include "esp_vfs_fat.h"
#include "sdmmc_cmd.h"
#include "driver/sdspi_host.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <string.h>
#include <stdio.h>
#include <time.h>

static const char *TAG = "DataLogger";

#define SPI_DMA_CHAN    1
#define PIN_NUM_MISO    2
#define PIN_NUM_MOSI    15
#define PIN_NUM_CLK     14
#define PIN_NUM_CS      13

static logger_state_t s_state = LOGGER_IDLE;
static uint32_t s_record_count = 0;
static uint8_t s_rate_hz = 10;
static uint32_t s_last_log_tick = 0;
static FILE *s_file = NULL;
static sdmmc_card_t *s_card = NULL;
static bool s_sd_mounted = false;

static const char *CSV_HEADER =
    "timestamp_ms,attention,meditation,blink_strength,raw_wave,"
    "delta,theta,low_alpha,high_alpha,low_beta,high_beta,low_gamma,high_gamma,"
    "servo0,servo1,servo2,servo3,servo4\n";

void data_logger_init(void)
{
    esp_vfs_fat_sdmmc_mount_config_t mount_config = {
        .format_if_mount_failed = false,
        .max_files = 5,
        .allocation_unit_size = 16 * 1024,
    };

    sdmmc_host_t host = SDSPI_HOST_DEFAULT();
    host.slot = SPI3_HOST;

    spi_bus_config_t bus_cfg = {
        .mosi_io_num = PIN_NUM_MOSI,
        .miso_io_num = PIN_NUM_MISO,
        .sclk_io_num = PIN_NUM_CLK,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .max_transfer_sz = 4000,
    };

    esp_err_t ret = spi_bus_initialize(host.slot, &bus_cfg, SPI_DMA_CHAN);
    if (ret != ESP_OK) {
        ESP_LOGW(TAG, "SPI bus init failed: %s", esp_err_to_name(ret));
        return;
    }

    sdspi_device_config_t slot_config = SDSPI_DEVICE_CONFIG_DEFAULT();
    slot_config.gpio_cs = PIN_NUM_CS;
    slot_config.host_id = host.slot;

    ret = esp_vfs_fat_sdspi_mount("/sdcard", &host, &slot_config, &mount_config, &s_card);
    if (ret != ESP_OK) {
        ESP_LOGW(TAG, "SD card mount failed: %s", esp_err_to_name(ret));
        spi_bus_free(host.slot);
        return;
    }

    s_sd_mounted = true;
    ESP_LOGI(TAG, "SD card mounted at /sdcard");
}

bool data_logger_start(void)
{
    if (!s_sd_mounted) {
        ESP_LOGW(TAG, "Cannot log: no SD card");
        return false;
    }

    if (s_state == LOGGER_RUNNING) return true;

    time_t now = time(NULL);
    struct tm *tm = localtime(&now);

    char path[64];
    if (tm) {
        snprintf(path, sizeof(path), "/sdcard/eeg_%04d%02d%02d_%02d%02d%02d.csv",
                 tm->tm_year + 1900, tm->tm_mon + 1, tm->tm_mday,
                 tm->tm_hour, tm->tm_min, tm->tm_sec);
    } else {
        snprintf(path, sizeof(path), "/sdcard/eeg_log.csv");
    }

    s_file = fopen(path, "w");
    if (!s_file) {
        ESP_LOGE(TAG, "Failed to create log file: %s", path);
        s_state = LOGGER_ERROR;
        return false;
    }

    fputs(CSV_HEADER, s_file);
    s_record_count = 0;
    s_last_log_tick = 0;
    s_state = LOGGER_RUNNING;

    ESP_LOGI(TAG, "Logging started: %s", path);
    return true;
}

void data_logger_stop(void)
{
    if (s_state != LOGGER_RUNNING) return;

    if (s_file) {
        fclose(s_file);
        s_file = NULL;
    }

    s_state = LOGGER_IDLE;
    ESP_LOGI(TAG, "Logging stopped. Records: %lu", s_record_count);
}

void data_logger_feed(const tgam_data_t *eeg, const uint8_t *servo_angles)
{
    if (s_state != LOGGER_RUNNING || !s_file || !eeg) return;

    uint32_t now = xTaskGetTickCount() * portTICK_PERIOD_MS;
    uint32_t interval_ms = 1000 / s_rate_hz;

    if (s_last_log_tick > 0 && (now - s_last_log_tick) < interval_ms) return;
    s_last_log_tick = now;

    fprintf(s_file,
        "%lu,%u,%u,%u,%d,"
        "%lu,%lu,%lu,%lu,%lu,%lu,%lu,%lu,"
        "%u,%u,%u,%u,%u\n",
        now,
        eeg->attention, eeg->meditation, eeg->blink_strength, eeg->raw_wave,
        eeg->eeg_power.delta, eeg->eeg_power.theta,
        eeg->eeg_power.low_alpha, eeg->eeg_power.high_alpha,
        eeg->eeg_power.low_beta, eeg->eeg_power.high_beta,
        eeg->eeg_power.low_gamma, eeg->eeg_power.high_gamma,
        servo_angles[0], servo_angles[1], servo_angles[2],
        servo_angles[3], servo_angles[4]);

    s_record_count++;

    if (s_record_count % 100 == 0) {
        fflush(s_file);
    }
}

logger_state_t data_logger_get_state(void)
{
    return s_state;
}

uint32_t data_logger_get_count(void)
{
    return s_record_count;
}

void data_logger_set_rate(uint8_t hz)
{
    if (hz >= 1 && hz <= 100) s_rate_hz = hz;
}
