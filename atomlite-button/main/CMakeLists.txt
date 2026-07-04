idf_component_register(
    SRCS "main.c"
    INCLUDE_DIRS "."
    REQUIRES
        driver            # gpio / uart
        esp_driver_gpio
        esp_driver_uart
)
