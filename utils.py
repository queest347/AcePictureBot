from http.cookiejar import LWPCookieJar
from robobrowser import RoboBrowser
from urllib.parse import urlparse
from requests import Session
from config import website_logins
from config import extra_api_keys
from config import settings
from PIL import Image
import urllib.request
import configparser
import subprocess
import requests
import hashlib
import pickle
import random
import json
import time
import re
import os

s = None


def make_paste(text, title="", expire="10M"):
    post_url = "https://paste.ee/api"
    payload = {'key': extra_api_keys['pasteee'],
               'paste': text,
               'description': title}
    headers = {'content-type': 'application/json'}
    r = requests.post(post_url,
                      data=json.dumps(payload),
                      headers=headers)
    return r.json()['paste']['link']


def file_to_list(file):
    if "/" not in file:
        file = os.path.join(settings['list_loc'], file)
    lines = list(filter(None,
                 open(file, 'r', encoding='utf-8').read().splitlines()))
    to_list = []
    split_by = False
    keep_s = -1
    try:
        if ":" in lines[0]:
            split_by = ":"
            keep_s = 0
            keep_e = 0
        elif "||" in lines[0]:
            split_by = "||"
            keep_s = 0
            keep_e = 2
            if (lines[3].count("||")) == 2:
                keep_e = 3
    except:
        # File is empty
        return []

    for line in lines:
        # Comment line
        if line[0] == "#":
            continue
        if split_by:
            line = line.split(split_by)
            if keep_s >= 0:
                line = line[keep_s:keep_e]
        to_list.append(line)
    return to_list


def short_str(string, cap=30):
    if not string:
        return string
    try:
        count = 0
        if string[cap + 5]:
            for char in string:
                count += 1
                if count >= cap or not char:
                    break
            string = string[:count].strip()
            return string + "[...]"
    except:
        return string.strip()


def scrape_site(url, cookie_file=""):
    global s
    s = Session()
    if cookie_file:
        s.cookies = LWPCookieJar(cookie_file)
        try:
            s.cookies.load(ignore_discard=True)
        except:
            # Cookies don't exsit yet
            pass
    s.headers['User-Agent'] = 'Mozilla/5.0 (X11; Ubuntu; rv:39.0)'
    s.headers['Accept'] = 'text/html'
    s.headers['Connection'] = 'keep-alive'
    browser = RoboBrowser(session=s,
                          parser='html5lib')
    try:
        browser.open(url)
        return browser
    except:
        print("[WARNING] TIMEOUT WITH WEBSITE: {0}".format(url))
        return False


def video_to_gif(video):
    """
    Return encoded gif path
    """
    try:
        save_to = os.path.join(settings['image_loc'], "downloads")
        SCRIPT_LOC = settings['webm_script']
        filename = os.path.join(
            save_to,
            hashlib.md5(
                open(video, 'rb').read()).hexdigest() + ".gif")
        command = [SCRIPT_LOC,
                   video,
                   filename]
        DEVNULL = open(os.devnull, 'w')
        pipe = subprocess.Popen(command, stdout=DEVNULL, bufsize=10**8)
        pipe.wait()
        if "gif" not in video:
            os.remove(video)
    except Exception as v:
        # Shouldn't happen but it's here to print in case
        print(v)
        return False

    return filename


def download_image(url, path="", filename=""):
    imgTypes = {"jpg": "image/jpeg",
                "jpeg": "image/jpeg",
                "png": "image/png",
                "gif": "image/gif",
                "webm": "video/webm"}
    filepath = urlparse(url).path
    ext = os.path.splitext(filepath)[1].lower()
    if not ext[ext.rfind(".")+1:] in imgTypes:
        return False

    hdr = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64)',
           'Connection': 'keep-alive'}
    req = urllib.request.Request(url, headers=hdr)
    response = urllib.request.urlopen(req)
    data = response.read()
    if path == "":
        path = os.path.join(settings['image_loc'], "downloads")
    else:
        path = os.path.join(settings['image_loc'], path)

    if filename == "":
        hash = hashlib.md5(data).hexdigest()
        filename = "%s%s" % (hash, ext)

    if not os.path.exists(path):
        os.makedirs(path)

    if not os.path.isfile(os.path.join(path, filename)):
        tweet_image = os.path.join(path, filename)
        with open(tweet_image, "wb") as code:
            code.write(data)
    else:
        tweet_image = os.path.join(path, str(filename))

    if "webm" in ext[ext.rfind(".")+1:]:
        tweet_image = video_to_gif(tweet_image)
        if not tweet_image:
            return False

    if ((os.stat(tweet_image).st_size / 1000000) > 2.8):
        # Filesize too big, return False if normal image
        # Try to compress if a gif
        if "gif" in ext[ext.rfind(".")+1:]:
            tweet_image = video_to_gif(tweet_image)
            # Still too large
            if ((os.stat(tweet_image).st_size / 1000000) > 2.8):
                os.remove(tweet_image)
                return False
        else:
            os.remove(tweet_image)
            return False

    pil_image = Image.open(tweet_image)
    pil_image.load()
    width, height = pil_image.size
    del pil_image
    if ext == ".gif":
        max_size = -160
        min_size = 610
    else:
        max_size = -610
        min_size = 610
    if (width - height) <= max_size:
        os.remove(tweet_image)
        return False
    elif (width - height) >= min_size:
        os.remove(tweet_image)
        return False

    return tweet_image


def get_image_online(tags, site=0, high_page=10, ignore_list="", path=""):
    if ":" not in path:
        path = os.path.join(settings['image_loc'], path)
    config = configparser.ConfigParser()
    config.read(settings['settings'])
    websites = (dict(config.items('Websites')))
    if websites['sankakucomplex'] == "False" and site == 0:
        site = 1
    if websites['danbooru'] == "False" and site == 1:
        site = 0

    if ignore_list:
        try:
            ignore_urls = pickle.load(open(
                    os.path.join(settings['ignore_loc'], ignore_list), 'rb'))
        except:
            ignore_urls = []
    else:
        ignore_list = "img_urls.pkl"
        ignore_urls = []

    tried_pages = [high_page]
    try_count = 0
    low_page = 0
    page = 0
    x = None
    found_image = False
    found_page = False
    good_image = False
    no_images = False
    if site == 0:
        cookie_file = "sankakucomplex.txt"
        url_start = "https://chan.sankakucomplex.com"
        url_search = "https://chan.sankakucomplex.com/?tags="
        url_login = "https://chan.sankakucomplex.com/user/login/"
        pid = False
        login = True
        form_num = 0
        form_user = "user[name]"
        form_password = "user[password]"
        username = website_logins['sankakucomplex_username']
        password = website_logins['sankakucomplex_password']
    elif site == 1:
        cookie_file = "danbooru.txt"
        url_start = "https://danbooru.donmai.us"
        url_search = "https://danbooru.donmai.us/posts?tags="
        pid = False
        login = False
    elif site == 2:
        cookie_file = "safebooru.txt"
        url_start = "http://safebooru.org"
        url_search = "http://safebooru.org/index.php?page=post&s=list&tags="
        pid = True
        login = False
    elif site == 3:
        cookie_file = "yande.txt"
        url_start = "https://yande.re"
        url_search = "https://yande.re/post?tags="
        pid = False
        login = False
    elif site == 4:
        cookie_file = "konachan.txt"
        url_start = "http://konachan.com"
        url_search = "http://konachan.com/post?tags="
        pid = False
        login = False

    if isinstance(tags, list):
        tags = '+'.join(tags)

    if site == 0:
        if "rating:safe" not in tags:
            tags += "+rating:safe"

    if login:
        if not os.path.exists(cookie_file):
            global s
            browser = scrape_site(url_login, cookie_file)
            form = browser.get_form(form_num)
            form[form_user].value = username
            form[form_password].value = password
            browser.submit_form(form)
            s.cookies.save()

    if pid:
        rand = 40
        tried_pages = [high_page * rand]
    else:
        rand = 1

    while not good_image:
        while not found_image:
            while not found_page:
                no_images = False
                try_count += 1
                if try_count == 15:
                    return False
                page = str(int(random.randint(low_page, high_page) * rand))
                while int(page) in tried_pages:
                    if int(page) == 0:
                        break
                    if not x:
                        x = high_page
                    page = str(int(random.randint(low_page, high_page) * rand))
                    if int(page) > int(x):
                        continue
                tried_pages.append(int(page))
                x = min(tried_pages)
                if not pid:
                    page_url = "&page=" + str(page)
                elif not pid:
                    page_url = "&pid=" + str(page)
                url = "%s%s%s" % (url_search, tags, page_url)
                browser = scrape_site(url, cookie_file)
                if site == 0:
                    if browser.find('div', text="No matching posts"):
                        no_images = True
                elif site == 1:
                    if browser.find('p', text="Nobody here but us chickens!"):
                        no_images = True
                elif site == 2:
                    if browser.find('h1', text="Nothing found, try google? "):
                        no_images = True
                    elif len(browser.find_all('span',
                             attrs={'class': "thumb"})) < 2:
                        no_images = True
                elif site == 3 or site == 4:
                    if browser.find('p', text="Nobody here but us chickens!"):
                        no_images = True
                time.sleep(1)
                if not no_images:
                    break
                elif no_images and int(page) == 0:
                    return False
            good_image_links = []
            image_links = browser.find_all('a')
            for link in image_links:
                try:
                    link['href']
                except:
                    continue
                if site == 0:
                    if "/post/show/" not in link['href']:
                        continue
                elif site == 1:
                    if "/posts/searches" in link['href']:
                        continue
                    if "events" in link['href']:
                        continue
                    if "random" in link['href']:
                        continue
                    if "/posts/" not in link['href']:
                        continue
                elif site == 2:
                    if "&id=" not in link['href']:
                        continue
                elif site == 3:
                    if "/post/show/" not in link['href']:
                        continue
                elif site == 4:
                    if "/post/show/" not in link['href']:
                        continue
                good_image_links.append(link['href'])
            if good_image_links == []:
                return False
            random.shuffle(good_image_links)
            if site == 0:
                url = "%s%s" % (url_start, random.choice(good_image_links))
            else:
                url = "%s/%s" % (url_start, random.choice(good_image_links))
            try_count = 0
            while url in ignore_urls:
                url = "%s/%s" % (url_start, random.choice(good_image_links))
                try_count = try_count + 1
                if try_count == 20:
                    break
            ignore_urls.append(url)
            browser.open(url)
            image_tags = []
            if site == 0:
                site_tag = browser.find('ul', id="tag-sidebar")
                site_tag = site_tag.find_all('li')
                for tag in site_tag:
                    text = tag.text
                    text = text.split("(?)")
                    text = text[0]
                    text = text.replace("&#39;", "\'")
                    image_tags.append(text)
            elif site == 1:
                site_tag = browser.find('section', id="tag-list")
                site_tag = site_tag.find_all('li')
                for tag in site_tag:
                    text = tag.find_all('a')
                    text = text[1]
                    text = text.text
                    text = text.replace("&#39;", "\'")
                    image_tags.append(text)
            elif site == 2:
                site_tag = browser.find('ul', id="tag-sidebar")
                site_tag = site_tag.find_all('li')
                for tag in site_tag:
                    tag = tag.find('a')
                    text = tag.text
                    text = text.replace("&#39;", "\'")
                    image_tags.append(text)
            elif site == 3:
                site_tag = browser.find('ul', id="tag-sidebar")
                site_tag = site_tag.find_all('li')
                for tag in site_tag:
                    text = tag.find_all('a')
                    text = text[1]
                    text = text.text
                    text = text.replace("&#39;", "\'")
                    image_tags.append(text)
            elif site == 4:
                site_tag = browser.find('ul', id="tag-sidebar")
                site_tag = site_tag.find_all('li')
                for tag in site_tag:
                    text = tag.find_all('a')
                    text = text[1]
                    text = text.text
                    text = text.replace("&#39;", "\'")
                    image_tags.append(text)

            if any([item.lower()in settings['ignore_tags']
                    for item in image_tags]):
                continue

            if "waifu" in ignore_list or "husbando" in ignore_list:
                if any(" (cosplay)" in s for s in image_tags):
                    continue

            break

        pickle.dump(ignore_urls, open(
            os.path.join(settings['ignore_loc'], ignore_list), 'wb'))
        image_url = browser.find('img', attrs={'id': 'image'})

        if not image_url:
            image_url = browser.find('video', attrs={'id': 'image'})
        if site == 0:
            try:
                url = "https:%s" % (image_url['src'])
            except:
                return False
        elif site == 1:
            try:
                url = url_start + image_url['src']
            except:
                return False
        elif site == 2:
            url = image_url['src']

        tweet_image = download_image(url, path)

        return tweet_image


def get_image(path):
    if ":" not in path:
        path = os.path.join(settings['image_loc'], path)
    try:
        img = random.choice(next(os.walk(path))[2])
    except:
        return False
    return os.path.join(path, img)


def get_command(string):
    string = string.lower()
    gender = ""
    if "waifu" in string:
        gender = "Waifu"
    elif "husbando" in string:
        gender = "Husbando"

    rep = {"waifu": "{GENDER}", "husbando": "{GENDER}",
           "anime?": "source", "anime ?": "source",
           "is this from": "source", "sauce": "source"}
    rep = dict((re.escape(k), v) for k, v in rep.items())
    pattern = re.compile("|".join(rep.keys()))
    string = pattern.sub(lambda m: rep[re.escape(m.group(0))], string)
    triggers = file_to_list(
                    os.path.join(settings['list_loc'],
                                 "commands.txt"))
    command = [s for s in triggers if str(s).lower() in string.lower()]
    if not command:
        return False
    else:
        command = command[0]
        if type(command) is bool:
            return False
    command = command.replace("{GENDER}", gender)
    return command


def short_string(string, limit=40):
    if string == "":
        return string
    try:
        count = 0
        if string[limit + 5]:
            for a in string:
                count += 1
                if count >= limit and a == " ":
                    break
            string = string[:count].strip()
            return string + "[..]"
    except:
        return string.strip()


def gender(string):
    string = string.lower()
    if "waifu" in string:
        return 0
    elif "husbando" in string:
        return 1
    return False