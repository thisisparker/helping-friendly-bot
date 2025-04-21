#! /bin/env python3

import json
import os
import random
import subprocess
import textwrap
import re
import sys
import time

import atproto
import requests
import yaml

from datetime import datetime
from datetime import timedelta

from bs4 import BeautifulSoup
from mastodon import Mastodon

import hfbot
from subscribers import subscribers

with open('apikeys.yaml') as f:
    config = yaml.safe_load(f)
    bearer_token = config['bearer-token']

    mastodon_client = Mastodon(access_token=config['mastodon-token'],
            api_base_url=config['mastodon-server'])

    bsky_client = atproto.Client()
    try:
        bsky_client.login(config['bsky-username'], config['bsky-password'])
    except:
        pass

    signal_sender = config.get('signal-number', '')


def send_alert(song, set_so_far):
    title = song

    repeat = True if title in set_so_far else False
    repeat_string = f'{title} again!'

    tweet_content = ''
    if repeat:
        tweet_content = repeat_string
    else:
        tweet_content = hfbot.helping_friendly(title) or f"I think this one's called \"{title}\", but I don't know anything about it. Maybe a debut?"

    if tweet_content:
        try:
            mastodon_client.toot(tweet_content)
        except Exception as e:
            print(e)

        try:
            bsky_client.send_post(tweet_content)
        except Exception as e:
            print(e)


    for sub in subscribers:
        if repeat:
            output_string = repeat_string
        else:
            output_string = hfbot.helping_friendly(title, 
                                                   username=sub['username'])

        if not output_string:
            output_string = tweet_content
        print(*textwrap.wrap(output_string, 
                             width=os.get_terminal_size().columns-2),
                sep='\n')

        print('---')

        command = (f'signal-cli -a {signal-sender} --trust-new-identities=always send -m')

        split_command = command.split()
        subprocess.run(split_command + [output_string] + [sub['number']],
                       stdout=subprocess.DEVNULL)

def check_loop(known_set):
    started = False if not known_set else True
    setlist = []

    while True:
        current_time = datetime.strftime(datetime.now(), '%H:%M:%S')

        res = requests.get('https://live.phish.net')
        soup = BeautifulSoup(res.content, features='html.parser')

        setlist = [a.get('title') for a in soup.find('div', class_='setlist-body').find_all('a')]

        if not started and (len(setlist) > 2 or len(setlist) == 0):
            print(f"Show not started as of {current_time}. Trying again in 60s.")
            print(f"Current setlist shown as {setlist}")
            time.sleep(60)
            continue
        else:
            if not(setlist[0].startswith('Tell')):
                    started = True

        if len(setlist) == len(known_set):
            print("No new song. Will check again in 30s.")
            time.sleep(30)
        elif len(setlist) > len(known_set):
            for i in range(len(known_set)-len(setlist), 0):
                send_alert(setlist[i], known_set)
                known_set.append(setlist[i])
            with open(f'setlists/{check_date}.json', 'w') as f:
                json.dump(known_set, f, indent=4)
            time.sleep(120)
        elif len(setlist) < len(known_set):
            print('Something has gone awry. Known set longer than live setlist.')
            print('Saving live setlist and waiting 10s.')
            known_set = setlist.copy()
            time.sleep(10)

def main():
    check_date = datetime.strftime(datetime.today()-timedelta(hours=6), '%Y-%m-%d')
    print(f'Requesting setlist for {check_date}')

    if os.path.exists(f'setlists/{check_date}.json'):
        print(f'Found {check_date}.json')
        with open(f'setlists/{check_date}.json') as f:
            known_set = json.load(f)
    else:
        known_set = []
    
    check_loop(known_set)

if __name__ == '__main__':
    main()