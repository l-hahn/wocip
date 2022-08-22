import logging
import network
import binascii
import machine
from math import sqrt


class WlanSniffer:
    def fibonacci_n(n):
        fivesqrt = sqrt(5)
        return int((((1+fivesqrt)/2)**n-((1-fivesqrt)/2)**n)/fivesqrt)

    def __init__(self, led_pin="LED", retry_limit=0, logger=None):
        self.led = machine.Pin(led_pin, machine.Pin.OUT)
        self.wlan = network.WLAN(network.STA_IF)
        self.detected_wlans = {}
        self.retry_limit = 1 if retry_limit == 0 else retry_limit
        self.fibonacci = retry_limit == 0
        self.logger = logger if logger is not None else logging.getLogger()

        self.wlan.active(True)


    def _update_retry_limit(self, round):
        return (
            WlanSniffer.fibonacci_n(round)
            if self.fibonacci
            else
            self.retry_limit
        )


    def w_led_on(self):
        self.led.value(1)


    def w_led_off(self):
        self.led.value(0)


    def get_sniffed_wlans(self):
        return dict(self.detected_wlans)


    def sniff(self):
        retry_limit = self.retry_limit
        found_round = 0
        retry = 0

        self.w_led_on()

        while retry != retry_limit:
            self.logger.debug(f"Retry {retry}")
            found_wlans = self.wlan.scan()
            retry += 1
            detected = False

            for found_wlan in found_wlans:
                ssid, bssid, channel, RSSI, security, hidden = found_wlan
                ssid = ssid.decode('utf-8')
                bssid = binascii.hexlify(bssid).decode()
                if ssid not in self.detected_wlans.keys():
                    self.detected_wlans[ssid] = {
                        "ssid": ssid,
                        "bssid": [bssid],
                        "channel": channel,
                        "rssi": RSSI,
                        "security": security,
                        "hidden": hidden,
                        "order_found": found_round
                    }
                    self.logger.info(f"NEW WLAN: {self.detected_wlans[ssid]}")
                    detected = True
                elif bssid not in self.detected_wlans[ssid]['bssid']:
                    self.logger.info(f"NEW BSSID: {bssid} for WLAN '{ssid}'")
                    self.detected_wlans[ssid]['bssid'].append(bssid)
                if detected:
                    found_round += 1
                    old_retry_limit = retry_limit
                    retry_limit = self._update_retry_limit(found_round)
                    self.logger.debug(f"Set retry limit from {old_retry_limit} to {retry_limit}")
                    detected = False
                    retry = 0
        self.w_led_off()


def main():
    logging.basicConfig(level=logging.DEBUG)
    log = logging.getLogger("WlanSniffer")
    sniffer = WlanSniffer(logger=log)
    sniffer.sniff()
    wlans = sniffer.get_sniffed_wlans()

    with open("sniffed_wlans.txt", "w") as file:
        for wlan in wlans.values():
            line = ", ".join(
                f"{str(k)}:{str(v)}"
                for k,v in wlan.items()
            )
            log.info(f"Found WLAN: {line}")
            file.write(f"{line}\n")

if __name__ == "__main__":
    main()

