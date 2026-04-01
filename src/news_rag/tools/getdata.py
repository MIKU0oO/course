#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import re

import requests
from lxml import etree

from ..config import DEFAULT_ARTICLES_FILE, ensure_runtime_dirs
from ..retry import retry


articles = []


@retry(retry=3, sleep=5)
def get_html(url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
    response = requests.get(url, headers=headers)
    response.encoding = "utf-8"
    if response.status_code == 200:
        return response.text
    print(response.status_code)
    return "ERROR"


def get_text(text):
    if isinstance(text, str):
        return re.sub("\\r|\\n|\\t|　| ", "", text).strip(" ")
    if isinstance(text, list):
        return "".join([re.sub("\\r|\\n|\\t|　| ", "", item).strip(" ") for item in text])
    return ""


def analyse_detail(detail_html, detail_url):
    tree = etree.HTML(detail_html)
    lis = tree.xpath('//div[@class="article"]|//div[@class="text_c"]')
    for li in lis:
        title = get_text(li.xpath("./h1/text()"))
        publish_info = get_text(li.xpath('.//span[@class="date"]/text()|//div[@class="lai"]//text()'))
        content = get_text(li.xpath('.//div[@id="ozoom"]//p/text()'))
        articles.append({"title": title, "url": detail_url, "pusblish_info": publish_info, "content": content})


def main() -> None:
    ensure_runtime_dirs()
    year_list = [str(year) for year in range(2023, 2024)]
    month_list = [str(month).zfill(2) for month in range(1, 13)]
    day_list = [str(day).zfill(2) for day in range(1, 32)]

    for year in year_list:
        for month in month_list:
            for day in day_list:
                head = f"http://paper.people.com.cn/rmrb/html/{year}-{month}/{day}/"
                for index in range(1, 21):
                    url = f"{head}nbs.D110000renmrb_{str(index).zfill(2)}.htm"
                    html = get_html(url)
                    if html == "ERROR":
                        continue
                    tree = etree.HTML(html)
                    lis = tree.xpath('//div[@class="news"]/ul|//div[@id="titleList"]/ul')
                    for li in lis:
                        detail_url_list = li.xpath("./li/a/@href")
                        name_list = li.xpath("./li/a//text()")
                        for name, relative_url in zip(name_list, detail_url_list):
                            detail_url = f"{head}{relative_url}"
                            print(name, detail_url)
                            detail_html = get_html(detail_url)
                            if detail_html != "ERROR":
                                analyse_detail(detail_html, detail_url)

    DEFAULT_ARTICLES_FILE.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_ARTICLES_FILE.write_text(json.dumps(articles, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
