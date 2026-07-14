/* csi_tx — ESP-NOW broadcast beacon for CSI sensing array.
 * Broadcasts a small packet with an incrementing sequence number at a
 * fixed rate on a fixed channel. RX nodes capture CSI from these frames.
 */
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_wifi.h"
#include "esp_now.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "nvs_flash.h"

#define CSI_WIFI_CHANNEL   6      /* must match csi_rx */
#define SEND_INTERVAL_MS   10     /* 10 ms = 100 Hz */

static const char *TAG = "csi_tx";
static const uint8_t BROADCAST_MAC[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};

typedef struct __attribute__((packed)) {
    uint32_t magic;   /* 0xC51C51C5 — lets RX ignore stray ESP-NOW traffic */
    uint32_t seq;
} csi_beacon_t;

static void wifi_init(void)
{
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));
    ESP_ERROR_CHECK(esp_wifi_set_channel(CSI_WIFI_CHANNEL, WIFI_SECOND_CHAN_NONE));
    /* Lock to a basic HT20 MCS0 rate: consistent packet format → consistent CSI */
    ESP_ERROR_CHECK(esp_wifi_config_espnow_rate(WIFI_IF_STA, WIFI_PHY_RATE_MCS0_LGI));
}

void app_main(void)
{
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ESP_ERROR_CHECK(nvs_flash_init());
    }

    wifi_init();
    ESP_ERROR_CHECK(esp_now_init());

    esp_now_peer_info_t peer = {0};
    memcpy(peer.peer_addr, BROADCAST_MAC, 6);
    peer.channel = CSI_WIFI_CHANNEL;
    peer.ifidx = WIFI_IF_STA;
    peer.encrypt = false;
    ESP_ERROR_CHECK(esp_now_add_peer(&peer));

    uint8_t mac[6];
    ESP_ERROR_CHECK(esp_wifi_get_mac(WIFI_IF_STA, mac));
    ESP_LOGI(TAG, "TX node MAC " MACSTR " — ch %d, %d Hz",
             MAC2STR(mac), CSI_WIFI_CHANNEL, 1000 / SEND_INTERVAL_MS);

    csi_beacon_t beacon = { .magic = 0xC51C51C5, .seq = 0 };
    TickType_t last_wake = xTaskGetTickCount();

    while (1) {
        esp_err_t err = esp_now_send(BROADCAST_MAC, (uint8_t *)&beacon, sizeof(beacon));
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "send failed: %s", esp_err_to_name(err));
        }
        beacon.seq++;
        if (beacon.seq % 1000 == 0) {
            ESP_LOGI(TAG, "sent %lu", (unsigned long)beacon.seq);
        }
        vTaskDelayUntil(&last_wake, pdMS_TO_TICKS(SEND_INTERVAL_MS));
    }
}
