/* i2c_scan - where is the OLED on this Heltec WiFi LoRa 32 V3, really?
 *
 * Why this exists
 * ---------------
 * docs/S3_PORT_SCOPE.md:132-137 records that csi_rx's OLED_SDA 21 /
 * OLED_SCL 22 are DevKit-convention pins and that "the Heltec's own I2C
 * OLED wiring is not recorded anywhere in this repo". This app is the
 * missing measurement.
 *
 * The published sources disagree: Heltec's Arduino core says SDA 8 /
 * SCL 9, community threads say other things, and Heltec's own repo carries
 * an open issue titled "LoRa 32 V3: OLED_SDA / OLED_SCL Pin Locations".
 * None of those is evidence about THIS board. So this app asks the board
 * instead of asking a diagram: it powers the rail, sweeps pin pairs, and
 * prints every address that ACKs.
 *
 * Note what is NOT known going in. csi_rx would log "OLED not found on
 * SDA=%d SCL=%d - running headless" (main.c:305-306), but that line goes
 * to stdout, into the binary telemetry stream, where pc/rff/protocol.py's
 * resync discards it as non-frame bytes - it reaches no file in data/raw/
 * and nobody has read it (docs/OLED_AND_MARGINAL_CELL.md 2.4). The same
 * section lists what is still open: whether oled_init failed on the bus,
 * on the device add, or on the first command byte, and whether a panel is
 * wired to 21/22 at all. This app settles the pin question directly and
 * does not need that log line to exist.
 *
 * It answers one question and refuses to answer any other. It does not
 * draw anything, does not init an SSD1306, does not touch WiFi, LoRa, NVS
 * or ../common. A bare ACK is the whole result.
 *
 * The three unknowns it separates
 * -------------------------------
 * 1. POWER. GPIO36 is reported as the Vext control on the V3 and Vext is a
 *    switched 3.3 V rail. With it off the panel is unpowered and EVERY
 *    probe fails no matter how right the pins are - a pin result read
 *    under the wrong rail state is worthless. The polarity is NOT settled
 *    (a P-channel high-side switch would be active-low, an N-channel
 *    enable active-high), so all three states are tested: driven low,
 *    driven high, and left floating as an input. Whichever produced ACKs
 *    is reported; if none did, that is stated too.
 * 2. PINS. Every ordered pair from SWEEP_PINS, so a pinout documented
 *    backwards still gets found. The eight specifically documented pairs
 *    are ALSO probed verbosely first, so each published claim gets an
 *    individually attributable yes/no.
 * 3. RESET. SSD1306 modules commonly need a reset line released before
 *    they answer. Scanned with no reset at all, then with GPIO16 pulsed,
 *    then with GPIO21 pulsed. Whether reset changed anything is reported
 *    rather than assumed.
 *
 * 3 rail states x 3 reset options = 9 independent sweeps. Both SSD1306
 * addresses (0x3C and 0x3D) are probed at every pair, and EVERY address
 * that answers is printed - if a third-party part is sitting on that bus,
 * that is worth knowing and is not filtered out.
 *
 * Pins deliberately NOT swept, and why
 * ------------------------------------
 *   0, 3, 45, 46   ESP32-S3 strapping pins (boot mode, JTAG source,
 *                  VDD_SPI voltage, ROM log enable). Driving them is how
 *                  you get a board that will not boot.
 *   19, 20         USB D-/D+. This is the console the report is printed
 *                  on; driving them would destroy the output.
 *   22..25         Do not exist on the ESP32-S3. Note that this is why
 *                  csi_rx's OLED_SCL=22 cannot ever work here - it is an
 *                  ESP32-classic pinout. The named-pair pass probes it
 *                  anyway so the failure is on the record, not inferred.
 *   26..32         SPI flash (CS0/CLK/Q/D/HD/WP/CS1). Driving = crash.
 *   33..35, 37     Octal-PSRAM lines on -R8 parts. esptool reported
 *                  "Embedded PSRAM 2MB" for this board (quad, sharing the
 *                  flash bus, so these are idle here) and CONFIG_SPIRAM is
 *                  off - but they are left alone anyway, because the cost
 *                  of being wrong about the package is a dead board.
 *   36             Held as Vext for the whole run, so it is never also a
 *                  bus pin. It is the one pin whose role we take on trust,
 *                  and it sits inside that same 33..37 range - see README.
 *   43, 44         UART0 TX/RX, where the ROM and second-stage bootloader
 *                  log. Left clean.
 *
 * The swept pins are driven open-drain by the I2C peripheral, so the worst
 * this does to a neighbouring part (the SX1262 sits on several of these on
 * a V3) is pull one of its lines low briefly, or reset it. Nothing here is
 * held, and nothing is driven high.
 *
 * Output is plain text on USB-Serial-JTAG - `idf.py monitor` works on this
 * app, unlike csi_rx whose stdout is a binary telemetry stream.
 */
#include <stdio.h>
#include <string.h>
#include <stdbool.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"
#include "driver/i2c_master.h"
#include "esp_rom_sys.h"
#include "esp_err.h"
#include "esp_mac.h"

/* Reported Vext control on the Heltec V3. Polarity unknown - all three
 * states are tested rather than picked. */
#define VEXT_GPIO           36
#define VEXT_SETTLE_MS      300     /* rail rise + SSD1306 power-on wait */

#define RESET_LOW_MS        10      /* SSD1306 needs >3 us; 10 ms is free */
#define RESET_SETTLE_MS     150

#define PROBE_TIMEOUT_MS    20      /* only reached if a line is held low */

#define RESET_NONE          (-1)

/* Both SSD1306 7-bit addresses. Anything that answers is printed. */
static const uint8_t ADDRS[] = {0x3C, 0x3D};
#define N_ADDRS (sizeof(ADDRS) / sizeof(ADDRS[0]))

/* Sweep set: see the exclusion list in the header comment above. */
static const int SWEEP_PINS[] = {
    1,  2,  4,  5,  6,  7,  8,  9,  10, 11, 12, 13,
    14, 15, 16, 17, 18, 21, 38, 39, 40, 41, 42, 47, 48,
};
#define N_SWEEP (sizeof(SWEEP_PINS) / sizeof(SWEEP_PINS[0]))

/* Every pair anyone has published for this board, both orderings. */
typedef struct {
    int sda;
    int scl;
    const char *source;
} named_pair_t;

static const named_pair_t NAMED[] = {
    {17, 18, "Heltec V3 board files / community threads"},
    {18, 17, "  ...same, reversed"},
    {21, 22, "csi_rx OLED_SDA/OLED_SCL (ESP32-classic pinout)"},
    {22, 21, "  ...same, reversed"},
    { 8,  9, "Heltec Arduino core (OLED_SDA/OLED_SCL)"},
    { 9,  8, "  ...same, reversed"},
    { 4, 15, "Heltec V2 / TTGO-era pinout"},
    {15,  4, "  ...same, reversed"},
};
#define N_NAMED (sizeof(NAMED) / sizeof(NAMED[0]))

typedef enum { VEXT_LOW = 0, VEXT_HIGH, VEXT_FLOAT, N_VEXT } vext_state_t;

static const char *VEXT_NAME[N_VEXT] = {
    "driven LOW",
    "driven HIGH",
    "FLOATING (input, no pull)",
};

static const int RESET_OPTS[] = {RESET_NONE, 16, 21};
#define N_RESET (sizeof(RESET_OPTS) / sizeof(RESET_OPTS[0]))

typedef struct {
    vext_state_t vext;
    int rst;
    int sda;
    int scl;
    uint8_t addr;
} hit_t;

#define MAX_HITS 64
static hit_t s_hits[MAX_HITS];
static int   s_nhits;
static int   s_hits_by_vext[N_VEXT];
static int   s_hits_no_reset;
static int   s_hits_with_reset;
static int   s_pairs_probed;
static int   s_pairs_skipped;

static void vext_apply(vext_state_t v)
{
    gpio_config_t io = {
        .pin_bit_mask = 1ULL << VEXT_GPIO,
        .mode         = (v == VEXT_FLOAT) ? GPIO_MODE_INPUT : GPIO_MODE_OUTPUT,
        .pull_up_en   = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type    = GPIO_INTR_DISABLE,
    };
    gpio_reset_pin((gpio_num_t)VEXT_GPIO);
    gpio_config(&io);
    if (v != VEXT_FLOAT) {
        gpio_set_level((gpio_num_t)VEXT_GPIO, (v == VEXT_HIGH) ? 1 : 0);
    }
    vTaskDelay(pdMS_TO_TICKS(VEXT_SETTLE_MS));
}

/* Pulse a candidate reset line low then high, and leave it high (released)
 * for the sweep that follows. */
static void reset_pulse(int pin)
{
    if (pin == RESET_NONE) {
        return;
    }
    gpio_config_t io = {
        .pin_bit_mask = 1ULL << pin,
        .mode         = GPIO_MODE_OUTPUT,
        .pull_up_en   = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type    = GPIO_INTR_DISABLE,
    };
    gpio_reset_pin((gpio_num_t)pin);
    gpio_config(&io);
    gpio_set_level((gpio_num_t)pin, 0);
    vTaskDelay(pdMS_TO_TICKS(RESET_LOW_MS));
    gpio_set_level((gpio_num_t)pin, 1);
    vTaskDelay(pdMS_TO_TICKS(RESET_SETTLE_MS));
}

/* An idle I2C bus rests high on both lines. If one is held low by
 * something else, no probe on that pair can succeed - skip it and say
 * which pin was low, because that is itself a useful finding. */
static bool lines_idle(int sda, int scl, int *stuck_pin)
{
    gpio_config_t io = {
        .pin_bit_mask = (1ULL << sda) | (1ULL << scl),
        .mode         = GPIO_MODE_INPUT,
        .pull_up_en   = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type    = GPIO_INTR_DISABLE,
    };
    if (gpio_config(&io) != ESP_OK) {
        *stuck_pin = -1;
        return false;
    }
    esp_rom_delay_us(200);          /* let the weak pullup charge the line */
    if (!gpio_get_level((gpio_num_t)sda)) {
        *stuck_pin = sda;
        return false;
    }
    if (!gpio_get_level((gpio_num_t)scl)) {
        *stuck_pin = scl;
        return false;
    }
    return true;
}

static void record_hit(vext_state_t v, int rst, int sda, int scl, uint8_t addr)
{
    s_hits_by_vext[v]++;
    if (rst == RESET_NONE) {
        s_hits_no_reset++;
    } else {
        s_hits_with_reset++;
    }
    if (s_nhits < MAX_HITS) {
        s_hits[s_nhits++] = (hit_t){v, rst, sda, scl, addr};
    }
}

/* Probe one ordered pair at both addresses. Returns the number of
 * addresses that ACKed. Internal pullups only - same as ssd1306.c. */
static int probe_pair(int sda, int scl, vext_state_t v, int rst, bool verbose)
{
    i2c_master_bus_config_t bus_cfg = {
        .i2c_port                     = -1,
        .sda_io_num                   = sda,
        .scl_io_num                   = scl,
        .clk_source                   = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt            = 7,
        .flags.enable_internal_pullup = true,
    };
    i2c_master_bus_handle_t bus;
    esp_err_t err = i2c_new_master_bus(&bus_cfg, &bus);
    if (err != ESP_OK) {
        if (verbose) {
            printf("      bus not created: %s%s\n", esp_err_to_name(err),
                   (err == ESP_ERR_INVALID_ARG)
                       ? "  (pin not usable on ESP32-S3)" : "");
        }
        return 0;
    }

    s_pairs_probed++;
    int found = 0;
    for (size_t i = 0; i < N_ADDRS; i++) {
        esp_err_t p = i2c_master_probe(bus, ADDRS[i], PROBE_TIMEOUT_MS);
        if (p == ESP_OK) {
            found++;
            record_hit(v, rst, sda, scl, ADDRS[i]);
            printf("      *** ACK  SDA=%d SCL=%d addr=0x%02X\n",
                   sda, scl, ADDRS[i]);
        } else if (verbose) {
            printf("      no ACK at 0x%02X (%s)\n",
                   ADDRS[i], esp_err_to_name(p));
        }
    }

    i2c_del_master_bus(bus);
    gpio_reset_pin((gpio_num_t)sda);
    gpio_reset_pin((gpio_num_t)scl);
    return found;
}

/* The eight published pairs, one attributable line each. */
static int named_pass(vext_state_t v, int rst)
{
    int found = 0;
    printf("    documented pairs:\n");
    for (size_t i = 0; i < N_NAMED; i++) {
        int sda = NAMED[i].sda, scl = NAMED[i].scl, stuck;
        printf("    SDA=%-2d SCL=%-2d  %s\n", sda, scl, NAMED[i].source);
        if (sda == rst || scl == rst) {
            printf("      skipped: pin %d is the reset line under test\n", rst);
            continue;
        }
        if (!lines_idle(sda, scl, &stuck)) {
            printf("      skipped: %s\n",
                   (stuck < 0) ? "pin not usable on ESP32-S3"
                               : "line held low, bus not idle");
            if (stuck >= 0) {
                printf("      (GPIO%d reads 0 with a pullup on it)\n", stuck);
            }
            s_pairs_skipped++;
            continue;
        }
        found += probe_pair(sda, scl, v, rst, true);
        vTaskDelay(1);
    }
    return found;
}

/* Every ordered pair in SWEEP_PINS. Quiet: only ACKs print. */
static int sweep_pass(vext_state_t v, int rst)
{
    int found = 0, skipped = 0, probed = 0;

    for (size_t i = 0; i < N_SWEEP; i++) {
        for (size_t j = 0; j < N_SWEEP; j++) {
            int sda = SWEEP_PINS[i], scl = SWEEP_PINS[j], stuck;
            if (i == j || sda == rst || scl == rst) {
                continue;
            }
            if (!lines_idle(sda, scl, &stuck)) {
                skipped++;
                s_pairs_skipped++;
                continue;
            }
            probed++;
            found += probe_pair(sda, scl, v, rst, false);
            /* app_main runs at priority 1; without this the idle task
             * starves and the task watchdog panics mid-sweep. */
            vTaskDelay(1);
        }
    }
    printf("    full sweep: %d pairs probed, %d skipped (line not idle), "
           "%d ACK%s\n", probed, skipped, found, (found == 1) ? "" : "s");
    return found;
}

static void print_verdict(void)
{
    printf("\n================ RESULT ================\n");

    if (s_nhits == 0) {
        printf("NO DEVICE ACKED. Not on any combination tried.\n\n");
        printf("This is a clean negative, not an inconclusive run. It says\n");
        printf("the panel is absent, dead, or not reachable from any GPIO\n");
        printf("this app is allowed to drive - it does NOT say the pinout\n");
        printf("is merely undiscovered.\n\n");
        printf("Exactly what was tried:\n");
        printf("  Vext GPIO%d states : driven LOW, driven HIGH, FLOAT\n",
               VEXT_GPIO);
        printf("  reset options     : none, GPIO16 pulsed, GPIO21 pulsed\n");
        printf("  addresses         : 0x3C, 0x3D\n");
        printf("  documented pairs  : ");
        for (size_t i = 0; i < N_NAMED; i++) {
            printf("(%d,%d)%s", NAMED[i].sda, NAMED[i].scl,
                   (i + 1 < N_NAMED) ? " " : "\n");
        }
        printf("  swept pins        : ");
        for (size_t i = 0; i < N_SWEEP; i++) {
            printf("%d%s", SWEEP_PINS[i], (i + 1 < N_SWEEP) ? "," : "\n");
        }
        printf("  pin pairs probed  : %d\n", s_pairs_probed);
        printf("  pin pairs skipped : %d (line held low, or pin not usable)\n",
               s_pairs_skipped);
        printf("\nNOT tried, on purpose: GPIO 0/3/45/46 (strapping),\n");
        printf("19/20 (USB console), 26..32 (SPI flash), 33..35/37\n");
        printf("(octal-PSRAM lines), 43/44 (UART0). If the panel is on one\n");
        printf("of those, this app cannot find it and neither should it.\n");
        printf("========================================\n");
        return;
    }

    /* Prefer the simplest working configuration: no reset line needed. */
    const hit_t *best = &s_hits[0];
    for (int i = 0; i < s_nhits; i++) {
        if (s_hits[i].rst == RESET_NONE) {
            best = &s_hits[i];
            break;
        }
    }

    printf("FOUND. %d ACK%s across all combinations.\n\n",
           s_nhits, (s_nhits == 1) ? "" : "s");
    printf("  Vext (GPIO%d) : %s\n", VEXT_GPIO, VEXT_NAME[best->vext]);
    printf("  SDA          : GPIO%d\n", best->sda);
    printf("  SCL          : GPIO%d\n", best->scl);
    if (best->rst == RESET_NONE) {
        printf("  reset pin    : none needed\n");
    } else {
        printf("  reset pin    : GPIO%d (pulsed low-high before the bus "
               "came up)\n", best->rst);
    }
    printf("  address      : 0x%02X\n", best->addr);

    printf("\n  did the rail state matter? ");
    int states_working = 0;
    for (int v = 0; v < N_VEXT; v++) {
        if (s_hits_by_vext[v]) {
            states_working++;
        }
    }
    if (states_working == N_VEXT) {
        printf("no - ACKs in all three states,\n"
               "    so GPIO%d is probably not gating this panel's power.\n",
               VEXT_GPIO);
    } else {
        printf("yes - ACKs only with Vext:\n");
        for (int v = 0; v < N_VEXT; v++) {
            if (s_hits_by_vext[v]) {
                printf("    %s (%d ACKs)\n", VEXT_NAME[v], s_hits_by_vext[v]);
            }
        }
    }

    printf("  did reset matter?         ");
    if (s_hits_no_reset && s_hits_with_reset) {
        printf("no - it ACKs with and without a pulse.\n");
    } else if (!s_hits_no_reset) {
        printf("yes - it ONLY ACKed after a reset pulse, so\n"
               "    csi_rx will need that pulse before oled_init().\n");
    } else {
        printf("yes, backwards - it ACKed with no pulse and STOPPED\n"
               "    once GPIO16/21 was driven. Suspect one of those two is\n"
               "    a bus pin here, or a line the panel needs left alone.\n");
    }

    printf("\n  every ACK, unfiltered:\n");
    for (int i = 0; i < s_nhits; i++) {
        printf("    Vext %-25s reset %-6s SDA=%-2d SCL=%-2d addr=0x%02X\n",
               VEXT_NAME[s_hits[i].vext],
               (s_hits[i].rst == RESET_NONE) ? "none" : "pulsed",
               s_hits[i].sda, s_hits[i].scl, s_hits[i].addr);
    }
    if (s_nhits == MAX_HITS) {
        printf("    (table full at %d - more may exist)\n", MAX_HITS);
    }
    printf("\n  An address other than 0x3C/0x3D cannot appear above: only\n");
    printf("  those two are probed. Both are printed when both answer.\n");
    printf("========================================\n");
}

void app_main(void)
{
    uint8_t mac[6] = {0};
    esp_read_mac(mac, ESP_MAC_WIFI_STA);

    /* USB-Serial-JTAG enumerates after boot; the first lines are lost
     * otherwise and the header is the part he needs to see. */
    vTaskDelay(pdMS_TO_TICKS(1500));

    printf("\n\n");
    printf("========================================\n");
    printf("i2c_scan - find the OLED empirically\n");
    printf("board MAC %02x:%02x:%02x:%02x:%02x:%02x\n",
           mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
    printf("(the benched Heltec S3 is 8c:fd:49:b7:b0:6c - if the MAC\n");
    printf(" above is different, you are looking at another board)\n");
    printf("========================================\n");
    printf("%d rail states x %d reset options, %zu documented pairs plus\n",
           (int)N_VEXT, (int)N_RESET, N_NAMED);
    printf("every ordered pair of %zu swept pins, at 0x3C and 0x3D.\n",
           N_SWEEP);
    printf("Takes about a minute. Nothing is written to the panel.\n");

    for (int v = 0; v < N_VEXT; v++) {
        vext_apply((vext_state_t)v);
        printf("\n--- Vext GPIO%d %s ---\n", VEXT_GPIO, VEXT_NAME[v]);

        for (size_t r = 0; r < N_RESET; r++) {
            int rst = RESET_OPTS[r];
            if (rst == RESET_NONE) {
                printf("\n  reset: none\n");
            } else {
                printf("\n  reset: GPIO%d pulsed low %d ms then released\n",
                       rst, RESET_LOW_MS);
            }
            reset_pulse(rst);

            named_pass((vext_state_t)v, rst);
            sweep_pass((vext_state_t)v, rst);
            fflush(stdout);

            if (rst != RESET_NONE) {
                gpio_reset_pin((gpio_num_t)rst);
            }
        }
    }

    print_verdict();

    /* Leave the rail in whatever state produced ACKs, so the panel is
     * powered if he wants to poke at it next; float if nothing answered,
     * which is the state the board boots into. */
    if (s_nhits > 0) {
        vext_apply(s_hits[0].vext);
        printf("\nVext GPIO%d left %s.\n", VEXT_GPIO, VEXT_NAME[s_hits[0].vext]);
    } else {
        vext_apply(VEXT_FLOAT);
        printf("\nVext GPIO%d left floating.\n", VEXT_GPIO);
    }
    printf("Done. Reflash csi_rx to resume capture (see README).\n");
    fflush(stdout);

    while (1) {
        vTaskDelay(pdMS_TO_TICKS(10000));
    }
}
