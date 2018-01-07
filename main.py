import json
import re
import threading
from typing import Dict, List, Iterable, Optional

import requests
import telegram
from bs4 import BeautifulSoup
from telegram.bot import Bot
from telegram.ext import CommandHandler, Updater


class RockAmRing:
    bot = None

    def __init__(self, token):
        self.bot = Bot(token)

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

    def send_bands(self, bands: Iterable[str]):
        self.bot.send_message(chat_id=id, text=self.get_sendable_bands_string(bands),
                              parse_mode=telegram.ParseMode.MARKDOWN, disable_web_page_preview=True)

    @staticmethod
    def write_bands(bands: Iterable[str], id: str):
        with open("bands_{}".format(id), "w+") as fd:
            fd.write("\n".join(bands))

    def get_bands(self, id: str) -> List[str]:
        bands = self.get_band_names()

        self.write_bands(bands, id)

        return bands

    @staticmethod
    def get_old(id: str) -> List[str]:
        try:
            with open("bands_{}".format(id), "r") as old_bands_fd:
                return [band.strip() for band in old_bands_fd.readlines()]
        except OSError:
            return []

    def get_new(self, id: str) -> Dict[str, set]:
        old_bands = self.get_old(id)
        current_bands = self.get_bands(id)
        removed = set()

        for old_band in old_bands:
            if old_band not in current_bands:
                removed.add(old_band)

        new_bands = set(current_bands).difference(old_bands)

        return {"new": new_bands, "removed": removed}

    def get_removed(self, id: str) -> List[str]:
        return list(self.get_new(id)['removed'])

    @staticmethod
    def get_band_url(band_name: str, check=True) -> Optional[str]:
        name = "-".join(band_name.split())
        name = name.lower().replace("&", "und")
        name = re.sub("[^a-z0-9-]", "", name)

        url = "http://www.rock-am-ring.com/lineup/{}".format(name)
        if check and not requests.get(url).ok:
            url = "http://www.rock-am-ring.com/lineup/{}-1".format(name)
            if not requests.get(url).ok:
                print('{} not ok - return None'.format(url))
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
        bands = self.get_bands(update.message.chat_id)

        if bands:
            self.send_bands(bands)
        else:
            self.bot.send_message(chat_id=update.message.chat_id, text="Bisher wurden keine Bands announced.")

    def new_bands(self, update):
        bands = list(self.get_new(update.message.chat_id)['new'])
        if bands:
            self.send_bands(bands)
        else:
            self.bot.send_message(chat_id=update.message.chat_id, text="Es wurden keine neuen Bands announced.")

    def removed_bands(self, update):
        bands = list(self.get_new(update.message.chat_id)['removed'])
        if bands:
            self.send_bands(bands)
        else:
            self.bot.send_message(chat_id=update.message.chat_id, text="Es wurden keine Bands abgesagt.")

    # noinspection PyMethodMayBeStatic
    def start(self, update):
        with open("bands_{}".format(update.message.chat_id), "bw+") as fd:
            fd.write(b"")


def sched_new(rar: RockAmRing):
    import re
    import os
    for file in os.listdir("."):
        try:
            id = re.findall(r"bands_(.*)", file)[0]
            if id:
                bands = rar.get_new(id)['new']
                if bands:
                    rar.send_bands(bands)
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
        updater = Updater(bot=rar.bot)
        dispatcher = updater.dispatcher

        schedule(rar)

        dispatcher.add_handler(CommandHandler("bands", rar.bands))
        dispatcher.add_handler(CommandHandler("neu", rar.new_bands))
        dispatcher.add_handler(CommandHandler("abgesagt", rar.removed_bands))
        dispatcher.add_handler(CommandHandler("start", rar.start))
        dispatcher.add_handler(
            CommandHandler("status", lambda b, u: b.send_message(chat_id=u.message.chat_id, text="Ok")))

        updater.start_polling()
    except Exception as e:
        print(e)
