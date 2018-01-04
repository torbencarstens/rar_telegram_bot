import requests
from bs4 import BeautifulSoup

def get_band_names():
    content = requests.get("http://rock-am-ring.de/lineup").content
    soup = BeautifulSoup(content, 'html.parser')
    band_divs = soup.findAll("div", {"class": "Label"})
    band_names = []

    for div in band_divs:
        span = div.find('span')
        if span:
            band_names.append(span.text.strip())
    return band_names


import json
import re
import threading
import telegram
from telegram.bot import Bot
from telegram.ext import CommandHandler, Updater

bot = None


def get_bands(id):
    bands = get_band_names()

    with open("bands_{}".format(id), "w+") as fd:
        fd.write("\n".join(bands))

    return bands


def get_old(id):
    try:
        with open("bands_{}".format(id), "r") as old_bands_fd:
            return [band.strip() for band in old_bands_fd.readlines()]
    except OSError as e:
        return []


def get_new(id):
    old_bands = get_old(id)
    current_bands = get_bands(id)
    removed = set()

    for old_band in old_bands:
        if old_band not in current_bands:
            removed.add(old_band)

    new_bands = set(current_bands).difference(old_bands)

    return {"new": new_bands, "removed": removed}


def get_band_url(band_name):
    name = "-".join(band_name.split())
    name = name.lower().replace("&", "und")
    name = re.sub("[^a-z0-9-]", "", name)

    url = "http://www.rock-am-ring.com/lineup/{}".format(name)
    if not requests.get(url).ok:
        url = "http://www.rock-am-ring.com/lineup/{}-1".format(name)
        if not requests.get(url).ok:
            print('{} not ok - return None'.format(url))
            return None

    return url


def get_telegram_url_markdown(band_name, url):
    if not url:
        return band_name

    return "[{}]({})".format(band_name, url)


def get_sendable_bands_string(bands):
    return "\n".join([get_telegram_url_markdown(band, get_band_url(band)) for band in bands])


def bands(_bot: Bot, update):
    global bot
    bot = _bot
    bands = get_bands(update.message.chat_id)

    if bands:
        bot.send_message(chat_id=update.message.chat_id, text=get_sendable_bands_string(bands), parse_mode=telegram.ParseMode.MARKDOWN, disable_web_page_preview=True)
    else:
        bot.send_message(chat_id=update.message.chat_id, text="Bisher wurden keine Bands announced.")


def new_bands(_bot: Bot, update):
    global bot
    bot = _bot
    bands = get_new(update.message.chat_id)['new']
    if bands:
        bot.send_message(chat_id=update.message.chat_id, text=get_sendable_bands_string(bands), parse_mode=telegram.ParseMode.MARKDOWN, disable_web_page_preview=True)
    else:
        bot.send_message(chat_id=update.message.chat_id, text="Es wurden keine neuen Bands announced.")


def removed_bands(_bot: Bot, update):
    global bot
    bot = _bot
    bands = get_new(update.message.chat_id)['removed']
    if bands:
        bot.send_message(chat_id=update.message.chat_id, text=get_sendable_bands_string(bands), parse_mode=telegram.ParseMode.MARKDOWN, disable_web_page_preview=True)
    else:
        bot.send_message(chat_id=update.message.chat_id, text="Es wurden keine Bands abgesagt.")


def start(new_bot: Bot, update):
    global bot
    bot = new_bot

    with open("bands_{}".format(update.message.chat_id), "w+") as fd:
        fd.write("[]")


def sched_new():
    global bot
    if not bot:
        schedule(30)
    import re
    import os
    for file in os.listdir("."):
        try:
            id = re.findall(r"bands_(.*)", file)[0]
            if id:
                bands = get_new(id)['new']
                if bands:
                    bot.send_message(chat_id=id, text=get_sendable_bands_string(bands), parse_mode=telegram.ParseMode.MARKDOWN, disable_web_page_preview=True)
        except IndexError:
            pass

    schedule()


def schedule(time=3600):
    t = threading.Timer(time, sched_new)
    t.daemon = True
    t.start()


if __name__ == "__main__":
    try:
        with open("secret.json", "r") as f:
            token = json.load(f)['token']

        updater = Updater(token=token)
        dispatcher = updater.dispatcher

        schedule()

        dispatcher.add_handler(CommandHandler("bands", bands))
        dispatcher.add_handler(CommandHandler("neu", new_bands))
        dispatcher.add_handler(CommandHandler("abgesagt", removed_bands))
        dispatcher.add_handler(CommandHandler("start", start))
        dispatcher.add_handler(CommandHandler("status", lambda b, u: b.send_messsage(u.message.chat_id, text="Ok")))

        updater.start_polling()
    except Exception as e:
        print(e)