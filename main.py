import json
import re
import threading
import time
from typing import List, Iterable

import requests
from bs4 import BeautifulSoup, Tag
from telegram.bot import Bot
from telegram.ext import CommandHandler, Updater
from telegram.parsemode import ParseMode


def read_latest():
    from datetime import datetime
    fmt = "%H:%M:%S"

    bands = []
    with open('latest', 'r') as fd:
        timestamp = datetime.strptime(time.strftime(fmt), fmt) - datetime.strptime(fd.readline().strip(), fmt)
        if timestamp.total_seconds() > 3600:
            return None
        for line in fd.readlines():
            try:
                bands.append(Band.from_line(line))
            except ValueError:
                pass

    return bands


def write_latest(bands):
    timestamp = time.strftime("%H:%M:%S")

    with open("latest", "w+") as fd:
        fd.write(timestamp + "\n")
        fd.write("\n".join([str(band) for band in bands]))


class Band:
    def __init__(self, name: str, url: str):
        self.name = name
        self.url = url

    @classmethod
    def from_soup(cls, div: Tag):
        span = div.find('span')
        link = div.find('a', {'class': 'BandBlock-link'})

        if not link or not span:
            raise ValueError("Couldn't find name/url tag in band div")

        name = span.text.strip()
        url = "https://rock-am-ring.de{}".format(link.get('href'))

        return cls(name, url)

    @classmethod
    def from_line(cls, line: str):
        name, url = re.findall(r"\[(.*?)]\((.*?)\)", line.strip())[0]

        return cls(name, url)

    def __eq__(self, other):
        return self.name == other.name

    def __hash__(self):
        return hash(tuple((self.name, self.url)))

    def __str__(self):
        if not self.url:
            return self.name

        return "[{}]({})".format(self.name, self.url)


class Message:
    def __init__(self, uid: str, bot: Bot, content: List[str] = None):
        self.content = content
        self.uid = uid
        self.bot = bot

    def _split(self, content: List[str] = None, seperator: str = "\n") -> List[str]:
        if not content and not self.content:
            return []

        max_length = 4096
        messages = []
        current = ""

        for item in content:
            if len(current) + len(item) > max_length:
                messages.append(current)
                current = ""

            current = seperator.join([current, item])
        messages.append(current)

        return messages

    def send_bands(self, bands: Iterable[Band]):
        if bands:
            self.send([str(band) for band in bands], parse_mode=ParseMode.MARKDOWN)
        else:
            self.send(["Keine neuen Announcements."])

    def send(self, content: List[str], *, parse_mode=None, disable_web_page_preview=False):
        if not content:
            content = self.content

        messages = self._split(content)

        first = True
        for message in messages:
            self.bot.send_message(chat_id=self.uid,
                                  text=message,
                                  parse_mode=parse_mode,
                                  disable_web_page_preview=disable_web_page_preview,
                                  disable_notification=not first)
            first = False


# noinspection PyShadowingNames
class User:
    def __init__(self, uid):
        self.id = uid

    def write_bands(self, bands: Iterable[Band]):
        with open("bands_{}".format(self.id), "w+") as fd:
            fd.write("\n".join([str(band) for band in bands]))

    def get_old_bands(self) -> Iterable[Band]:
        try:
            with open("bands_{}".format(self.id), "r") as old_bands_fd:
                return [Band.from_line(line) for line in old_bands_fd.readlines()]
        except OSError:
            return []

    def get_new_bands(self, bands: Iterable[Band]) -> Iterable[Band]:
        old_bands = set(self.get_old_bands())

        return set(bands).difference(old_bands)


# noinspection PyShadowingNames
class Users(list):
    def __init__(self):
        super().__init__()

        import os

        for file in os.listdir("."):
            match = re.findall(r"bands_(-?\d+)", file)
            if match:
                self.append(User(match))

    def get(self, uid: str):
        try:
            return next(filter(lambda user: user.id == uid, self))
        except StopIteration:
            return User(uid)


# noinspection PyShadowingNames
class RockAmRing(Bot):
    def __init__(self, token: str):
        if not token or token == "<YOUR_TOKEN>":
            raise ValueError("`token` must have a valid value ({} given).".format(token))

        self.users = Users()
        super().__init__(token)

    @staticmethod
    def get_band_items() -> Iterable[Band]:
        try:
            latest = read_latest()
        except OSError:
            latest = None
        if latest:
            return latest

        content = requests.get("http://rock-am-ring.de/lineup").content
        soup = BeautifulSoup(content, 'html.parser')
        band_divs = soup.find_all("div", {"class": "BandBlock"})
        bands = []

        for div in band_divs:
            try:
                bands.append(Band.from_soup(div))
            except ValueError:
                pass

        write_latest(bands)

        return bands

    def send_bands(self, uid: str, bands: Iterable[Band]):
        bands = list(bands)
        bands.sort(key=lambda x: x.name)
        Message(uid, self).send_bands(bands)

    def get_bands(self, uid: str) -> Iterable[Band]:
        bands = self.get_band_items()

        self.users.get(uid).write_bands(bands)

        return bands

    def get_new(self, uid: str):
        bands = self.get_band_items()
        return self.users.get(uid).get_new_bands(bands)

    def bands(self, update):
        uid = update.message.chat_id
        bands = self.get_bands(uid)

        self.send_bands(uid, bands)

    def new_bands(self, update):
        uid = update.message.chat_id
        bands = list(self.get_new(uid))
        self.send_bands(uid, bands)

    def start(self, update):
        uid = update.message.chat_id
        self.users.get(uid).write_bands([])


# noinspection PyShadowingNames
def sched_new(rar: RockAmRing):
    import os
    for file in os.listdir("."):
        try:
            uid = re.findall(r"bands_(.*)", file)[0]
            if uid:
                bands = rar.get_new(uid)
                if bands:
                    rar.send_bands(uid, bands)
        except IndexError:
            pass

    schedule(rar)


# noinspection PyShadowingNames
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

        dispatcher.add_handler(CommandHandler("bands", lambda b, u: b.bands(u)))
        dispatcher.add_handler(CommandHandler("neu", lambda b, u: b.new_bands(u)))
        dispatcher.add_handler(CommandHandler("start", lambda b, u: b.start()))
        dispatcher.add_handler(CommandHandler("status",
                                              lambda b, u: b.send_message(chat_id=u.message.chat_id,
                                                                          text="[{}] Ok".format(u.message.chat_id))))

        updater.start_polling()
    except Exception as e:
        print(e)
