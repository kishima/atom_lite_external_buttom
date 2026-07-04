// M5 Atom Lite を PC の「外部ボタン」にするファームウェア。
//
// PC とは USB (UART0) で接続する。ATOM Lite 本体のボタン押下を検知して PC へ
// テキスト行で通知し、PC から届いたコマンドで本体 RGB LED を任意の色に光らせる。
//
// ハードウェア（ATOM Lite 固定）:
//   - ボタン: GPIO39（入力専用・基板上プルアップ・押下で LOW）
//   - RGB LED: GPIO27（SK6812 1 個・GRB）
//   - USB シリアル: UART0（GPIO1=TX / GPIO3=RX）ボーレート 115200
//
// ── 通信プロトコル（行単位、CRLF 終端。PC 側は行頭で判別する）──
//   Device -> PC:
//     READY            起動完了
//     BTN DOWN         ボタン押下
//     BTN UP           ボタン解放
//     PONG             PING への応答
//     OK               コマンド成功
//     ERR <理由>       コマンド失敗
//   PC -> Device（\n または \r 終端）:
//     LED RRGGBB       16進で色指定（例: LED FF8800）
//     LED OFF          消灯
//     PING             疎通確認（PONG が返る）
//
// ── リンク監視（PC 通信断で白）──
// PC からの定期通信（ハートビート）が LINK_TIMEOUT_MS 途絶えると、LED を白にして
// 「PC からの通信が失われた」ことを示す。通信が戻れば PC 側ハートビートが色を
// 再送するので通常表示に復帰する。PC 側は現在色を定期的に送ること（app.py 参照）。
#include <ctype.h>
#include <stdio.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"

#include "driver/gpio.h"
#include "driver/uart.h"
#include "esp_log.h"
#include "led_strip.h"

static const char *TAG = "btn";

// --- ピン定義（ATOM Lite） ---
#define BUTTON_GPIO   GPIO_NUM_39   // 押下で LOW（active low）
#define LED_GPIO      GPIO_NUM_27   // SK6812
#define LED_COUNT     1

// --- UART（USB シリアル）---
#define UART_PORT     UART_NUM_0
#define UART_BAUD     115200
#define UART_RX_BUF   1024
#define RX_LINE_MAX   64            // 受信 1 行の最大長（LINE_MAX は syslimits.h と衝突）

// --- ボタン検出 ---
// POLL_MS は最低 1 tick（既定 100Hz = 10ms）以上にすること。これより小さいと
// pdMS_TO_TICKS() が 0 tick に切り捨てられ vTaskDelay(0) になり、タスクが CPU を
// 離さずアイドルを飢餓させてタスクウォッチドッグが発火する。
#define POLL_MS       10            // ポーリング周期
#define DEBOUNCE_MS   30            // チャタリング除去の安定時間（POLL_MS の倍数）

// --- リンク監視（PC 通信断で白） ---
#define LINK_TIMEOUT_MS 3000        // この間 PC から受信が無ければ「通信断」とみなす
#define LINK_CHECK_MS   500         // 監視タスクのチェック周期

static led_strip_handle_t s_led;
static SemaphoreHandle_t s_led_mutex;         // led_set を複数タスクから安全に呼ぶ
static volatile TickType_t s_last_rx_tick;    // PC から最後に受信した時刻
static volatile bool s_link_lost;             // 通信断で白を表示中か

// ---- UART 送信ヘルパ（行末に CRLF を付けて 1 行送る）----
static void send_line(const char *s)
{
    uart_write_bytes(UART_PORT, s, strlen(s));
    uart_write_bytes(UART_PORT, "\r\n", 2);
}

// ---- LED 制御（uart_rx / link / init から呼ばれるので排他する）----
static void led_set(uint8_t r, uint8_t g, uint8_t b)
{
    xSemaphoreTake(s_led_mutex, portMAX_DELAY);
    led_strip_set_pixel(s_led, 0, r, g, b);
    led_strip_refresh(s_led);
    xSemaphoreGive(s_led_mutex);
}

static void led_init(void)
{
    led_strip_config_t strip_config = {
        .strip_gpio_num = LED_GPIO,
        .max_leds = LED_COUNT,
        .led_pixel_format = LED_PIXEL_FORMAT_GRB,
        .led_model = LED_MODEL_SK6812,
        .flags.invert_out = false,
    };
    led_strip_rmt_config_t rmt_config = {
        .clk_src = RMT_CLK_SRC_DEFAULT,
        .resolution_hz = 10 * 1000 * 1000,  // 10MHz
        .flags.with_dma = false,
    };
    ESP_ERROR_CHECK(led_strip_new_rmt_device(&strip_config, &rmt_config, &s_led));
    led_set(0, 0, 0);  // 起動時は消灯
}

// ---- UART 初期化 ----
static void uart_init(void)
{
    uart_config_t cfg = {
        .baud_rate = UART_BAUD,
        .data_bits = UART_DATA_8_BITS,
        .parity    = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    // 既定の UART0 ピン（TX=1 / RX=3）をそのまま使うのでピン設定は省略。
    ESP_ERROR_CHECK(uart_driver_install(UART_PORT, UART_RX_BUF, 0, 0, NULL, 0));
    ESP_ERROR_CHECK(uart_param_config(UART_PORT, &cfg));
}

// "FF8800" 等の16進文字列を RGB に変換。成功で true。
static bool parse_hex_color(const char *hex, uint8_t *r, uint8_t *g, uint8_t *b)
{
    if (strlen(hex) != 6) return false;
    for (int i = 0; i < 6; i++) {
        if (!isxdigit((unsigned char)hex[i])) return false;
    }
    unsigned int v;
    if (sscanf(hex, "%6x", &v) != 1) return false;
    *r = (v >> 16) & 0xFF;
    *g = (v >> 8) & 0xFF;
    *b = v & 0xFF;
    return true;
}

// 1 行分のコマンドを処理する。
static void handle_line(char *line)
{
    // 前後の空白を除去
    while (*line == ' ' || *line == '\t') line++;
    size_t len = strlen(line);
    while (len > 0 && (line[len - 1] == ' ' || line[len - 1] == '\t')) {
        line[--len] = '\0';
    }
    if (len == 0) return;

    // コマンド語を大文字化して判定
    if (strncasecmp(line, "PING", 4) == 0 && (line[4] == '\0' || line[4] == ' ')) {
        send_line("PONG");
        return;
    }

    if (strncasecmp(line, "LED", 3) == 0 && (line[3] == ' ' || line[3] == '\t')) {
        char *arg = line + 3;
        while (*arg == ' ' || *arg == '\t') arg++;

        if (strcasecmp(arg, "OFF") == 0) {
            led_set(0, 0, 0);
            send_line("OK");
            return;
        }
        uint8_t r, g, b;
        if (parse_hex_color(arg, &r, &g, &b)) {
            led_set(r, g, b);
            send_line("OK");
        } else {
            send_line("ERR bad color (use LED RRGGBB or LED OFF)");
        }
        return;
    }

    send_line("ERR unknown command");
}

// UART から 1 バイトずつ読み、改行で 1 行にまとめて handle_line へ渡す。
static void uart_rx_task(void *arg)
{
    char line[RX_LINE_MAX];
    size_t pos = 0;
    uint8_t byte;

    while (1) {
        int n = uart_read_bytes(UART_PORT, &byte, 1, portMAX_DELAY);
        if (n <= 0) continue;

        // PC から何か受信した = リンク生存。時刻を更新し、白表示中なら解除する
        // （復帰後の色は PC のハートビートが再送してくれる）。
        s_last_rx_tick = xTaskGetTickCount();
        s_link_lost = false;

        if (byte == '\n' || byte == '\r') {
            if (pos > 0) {
                line[pos] = '\0';
                handle_line(line);
                pos = 0;
            }
        } else if (pos < RX_LINE_MAX - 1) {
            line[pos++] = (char)byte;
        } else {
            // 行が長すぎる。バッファを捨てて次の行から仕切り直す。
            pos = 0;
            send_line("ERR line too long");
        }
    }
}

// PC からの受信が LINK_TIMEOUT_MS 途絶えたら LED を白にする。
// 復帰（受信再開）時は uart_rx_task が s_link_lost を落とし、色は PC の
// ハートビートが再送するのでここでは白の点灯のみを担当する。
static void link_task(void *arg)
{
    while (1) {
        TickType_t elapsed = xTaskGetTickCount() - s_last_rx_tick;
        bool timed_out = elapsed > pdMS_TO_TICKS(LINK_TIMEOUT_MS);
        if (timed_out && !s_link_lost) {
            s_link_lost = true;
            led_set(255, 255, 255);  // 白 = PC からの通信が失われた
        }
        vTaskDelay(pdMS_TO_TICKS(LINK_CHECK_MS));
    }
}

// ボタンをポーリングし、デバウンス後の変化を BTN DOWN/UP として送る。
static void button_task(void *arg)
{
    int stable = gpio_get_level(BUTTON_GPIO);  // 1=解放, 0=押下
    int last_raw = stable;
    int stable_count = 0;

    while (1) {
        int raw = gpio_get_level(BUTTON_GPIO);
        if (raw != last_raw) {
            last_raw = raw;
            stable_count = 0;  // 変化したので安定カウントをリセット
        } else if (raw != stable) {
            stable_count += POLL_MS;
            if (stable_count >= DEBOUNCE_MS) {
                stable = raw;
                send_line(raw == 0 ? "BTN DOWN" : "BTN UP");
            }
        }
        vTaskDelay(pdMS_TO_TICKS(POLL_MS));
    }
}

void app_main(void)
{
    esp_log_level_set("*", ESP_LOG_WARN);  // プロトコル出力を汚さないよう抑制

    // ボタン入力（GPIO39 は入力専用・基板側プルアップあり）
    gpio_config_t io = {
        .pin_bit_mask = 1ULL << BUTTON_GPIO,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,   // 基板上に外部プルアップがある
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&io));

    s_led_mutex = xSemaphoreCreateMutex();     // led_init が led_set を呼ぶので先に作る
    // 起動直後に即・白へ落ちないよう、受信時刻を「今」で初期化してから監視を始める。
    s_last_rx_tick = xTaskGetTickCount();

    uart_init();
    led_init();

    xTaskCreate(uart_rx_task, "uart_rx", 4096, NULL, 10, NULL);
    xTaskCreate(button_task, "button", 3072, NULL, 10, NULL);
    xTaskCreate(link_task, "link", 3072, NULL, 9, NULL);

    ESP_LOGI(TAG, "atomlite-button started");
    send_line("READY");
}
