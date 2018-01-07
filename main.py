import json
import re
import threading
from typing import Dict, List, Iterable, Optional

import requests
import telegram
from bs4 import BeautifulSoup
from telegram.bot import Bot
from telegram.ext import CommandHandler, Updater


class RockAmRing(Bot):
    bot = None

    def __init__(self, token: str):
        if not token or token == "<YOUR_TOKEN>":
            raise ValueError("`token` must have a valid value ({} given).".format(token))
        super().__init__(token)

    @staticmethod
    def get_band_names() -> List[str]:
        content = requests.get("http://rock-am-ring.de/lineup").content
        soup = BeautifulSoup(content, 'html.parser')
        band_divs = soup.findAll("div", {"class": "Label"})
        band_names = []

        for div in band_divs:
            span = div.find('span')
            if span:
                band_names.append(span.text.strip())

        return band_names

    def send_bands(self, uid: str, bands: Iterable[str]):
        self.send_message(chat_id=uid, text=self.get_sendable_bands_string(bands),
                          parse_mode=telegram.ParseMode.MARKDOWN, disable_web_page_preview=True)

    @staticmethod
    def write_bands(uid: str, bands: Iterable[str]):
        with open("bands_{}".format(uid), "w+") as fd:
            fd.write("\n".join(bands))

    def get_bands(self, uid: str) -> List[str]:
        bands = self.get_band_names()

        self.write_bands(uid, bands)

        return bands

    @staticmethod
    def get_old(uid: str) -> List[str]:
        try:
            with open("bands_{}".format(uid), "r") as old_bands_fd:
                return [band.strip() for band in old_bands_fd.readlines()]
        except OSError:
            return []

    def get_new(self, uid: str) -> Dict[str, set]:
        old_bands = self.get_old(uid)
        current_bands = self.get_bands(uid)
        removed = set()

        for old_band in old_bands:
            if old_band not in current_bands:
                removed.add(old_band)

        new_bands = set(current_bands).difference(old_bands)

        return {"new": new_bands, "removed": removed}

    def get_removed(self, uid: str) -> List[str]:
        return list(self.get_new(uid)['removed'])

    @staticmethod
    def get_band_url(band_name: str, check=True) -> Optional[str]:
        name = "-".join(band_name.split())
        name = name.lower().replace("&", "und")
        name = re.sub("[^a-z0-9-]", "", name)

        url = "http://www.rock-am-ring.com/lineup/{}".format(name)
        if check and not requests.get(url).ok:
            url = "http://www.rock-am-ring.com/lineup/{}-1".format(name)
            if not requests.get(url).ok:
                print('{} not ok for {} - return None'.format(url, band_name))
                return None

        return url

    @staticmethod
    def get_telegram_url_markdown(band_name: str, url: str) -> str:
        if not url:
            return band_name

        return "[{}]({})".format(band_name, url)

    def get_sendable_bands_string(self, bands: Iterable[str]) -> str:
        return "\n".join([self.get_telegram_url_markdown(band, self.get_band_url(band)) for band in bands])

    def bands(self, update):
        uid = update.message.chat_id
        bands = self.get_bands(uid)

        if bands:
            self.send_bands(uid, bands)
        else:
            self.send_message(chat_id=update.message.chat_id, text="Bisher wurden keine Bands announced.")

    def new_bands(self, update):
        uid = update.message.chat_id
        bands = list(self.get_new(uid)['new'])
        if bands:
            self.send_bands(uid, bands)
        else:
            self.send_message(chat_id=update.message.chat_id, text="Es wurden keine neuen Bands announced.")

    def removed_bands(self, update):
        uid = update.message.chat_id
        bands = list(self.get_new(uid)['removed'])
        if bands:
            self.send_bands(uid, bands)
        else:
            self.send_message(chat_id=uid, text="Es wurden keine Bands abgesagt.")

    def start(self, update):
        uid = update.message.chat_id
        self.write_bands(uid, [])


def sched_new(rar: RockAmRing):
    import os
    for file in os.listdir("."):
        try:
            uid = re.findall(r"bands_(.*)", file)[0]
            if uid:
                bands = rar.get_new(uid)['new']
                if bands:
                    rar.send_bands(uid, bands)
        except IndexError:
            pass

    schedule(rar)


def schedule(rar, time=3600):
    t = threading.Timer(time, sched_new, args=[rar])
    t.daemon = True
    t.start()


if __name__ == "__main__":
    try:
        with open("secret.json", "r") as f:
            token = json.load(f)['token']

        rar = RockAmRing(token)
        updater = Updater(bot=rar)
        dispatcher = updater.dispatcher

        schedule(rar)

        dispatcher.add_handler(CommandHandler("bands", rar.bands))
        dispatcher.add_handler(CommandHandler("neu", rar.new_bands))
        dispatcher.add_handler(CommandHandler("abgesagt", rar.removed_bands))
        dispatcher.add_handler(CommandHandler("start", rar.start))
        dispatcher.add_handler(
            CommandHandler("status", lambda b, u: b.send_message(chat_id=u.message.chat_uid, text="Ok")))

        updater.start_polling()
    except Exception as e:
        print(e)
