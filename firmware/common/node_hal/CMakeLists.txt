idf_component_register(SRCS "node_hal.c" "ssd1306.c"
                       INCLUDE_DIRS "include"
                       PRIV_REQUIRES driver nvs_flash esp_timer esp_system esp_hw_support)
