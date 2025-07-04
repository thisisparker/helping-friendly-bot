#! /bin/env python3

import json
import os
import requests
import textwrap
import re
import sys
import time

import atproto
import websocket
import yaml

from datetime import datetime
from datetime import timedelta

from mastodon import Mastodon

import hfbot
from subscribers import subscribers

script_path = os.path.abspath(__file__)
os.chdir(os.path.dirname(script_path))

with open('apikeys.yaml') as f:
    if '-d' in sys.argv[1:]:
        config = yaml.safe_load(f)['dev']
        print('loaded dev configuration')
    else:
        config = yaml.safe_load(f)['prod']
        print('loaded prod configuration')

    try:
        mastodon_client = Mastodon(access_token=config['mastodon-token'],
            api_base_url=config['mastodon-server'])
    except:
        print('could not log in to masotodon')
        pass

    bsky_client = atproto.Client()
    try:
        bsky_client.login(config['bsky-username'], config['bsky-password'])
    except:
        sys.exit('could not log in to bsky')

    signal_sender = config['signal-number']

    did_to_monitor = config['bsky-did']


def send_signal_message(message, recipient):
    SIGNAL_API_URL = '127.0.0.1:8080' #todo: get this an an env variable or something

    packaged_message = {'message': message,
                        'number': signal_sender,
                        'recipients': [recipient]}

    requests.post(f'http://{SIGNAL_API_URL}/v2/send', json=packaged_message)

def send_alert(song, reply_to):
    check_date = datetime.strftime(datetime.today()-timedelta(hours=6), '%Y-%m-%d')

    if os.path.exists(f'setlists/{check_date}.json'):
        with open(f'setlists/{check_date}.json') as f:
            set_so_far = json.load(f)
    else:
        set_so_far = []

    title = song

    repeat = True if title in [s['title'] for s in set_so_far] else False
    repeat_string = f'{title} again!'

    tweet_content = ''
    embed_post = None
    if repeat:
        tweet_content = repeat_string
        previous_post = next(s for s in set_so_far if s['title'] == title)
        previous_post_record = bsky_client.get_post(previous_post['rkey'], cid=previous_post['cid'])
        previous_post_ref = atproto.models.create_strong_ref(previous_post_record)
        embed_post = atproto.models.AppBskyEmbedRecord.Main(record=previous_post_ref)
    else:
        tweet_content = hfbot.helping_friendly(title) or f"I think this one's called \"{title}\", but I don't know anything about it. Maybe a debut?"

    try:
        mastodon_client.toot(tweet_content)
    except Exception as e:
        print(e)

    post_rec = None
    post_rkey = None
    post_cid = None
    try:
        post_rec = bsky_client.send_post(tweet_content, reply_to=reply_to, embed=embed_post)
    except Exception as e:
        print(e)

    if post_rec:
        post_rkey = post_rec.uri.split('/')[-1]
        post_cid  = post_rec.cid

        try:
            bsky_client.repost(post_rec.uri, post_rec.cid)
        except Exception as e:
            print('Error:', e)

    set_so_far.append({'title':title, 'rkey':post_rkey, 'cid': post_cid})

    with open(f'setlists/{check_date}.json', 'w') as f:
        json.dump(set_so_far, f, indent=4)


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

        send_signal_message(output_string, sub['number'])

def process_message(streamer, message):
    msg = json.loads(message)

    print("new message:", msg.get("commit", []).get("record", []).get("text", ''))

    rkey = msg.get("commit", []).get("rkey", "")
    sender_did = msg.get("did","")

    time.sleep(10)
    try:
        post = bsky_client.get_post(post_rkey=rkey, profile_identify=sender_did)
    except:
        print('unable to fetch bsky post. maybe deleted!')
        return

    if post.value.reply or post.value.embed:
        return
    
    text = post.value.text

    if re.match(r'(\d+/\d+/\d+)', text):
        return

    title_to_match = (text if ':' not in text 
                            else text.split(':')[1].strip())

    title_to_match = title_to_match.lstrip('> ')

    reply_to = atproto.models.AppBskyFeedPost.ReplyRef(parent=atproto.models.create_strong_ref(post),
                                                       root  =atproto.models.create_strong_ref(post))

    send_alert(title_to_match, reply_to=reply_to)

def check_loop():
    try:
        print("monitoring feed for", bsky_client.get_profile(actor=did_to_monitor).handle)
    except:
        sys.exit("Could not look up account with the given DID")
    streamer = websocket.WebSocketApp(f"wss://jetstream2.us-east.bsky.network/subscribe?wantedCollections=app.bsky.feed.post&wantedDids={did_to_monitor}", on_message=process_message)
    streamer.run_forever()

def main():
    print('Starting Helping Friendly Bot stream:', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    check_loop()

if __name__ == '__main__':
    main()