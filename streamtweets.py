#! /bin/env python3

import os
import subprocess
import textwrap
import re
import sys
import time

import tweepy
import yaml

from mastodon import Mastodon

import hfbot

with open('apikeys.yaml') as f:
    config = yaml.safe_load(f)
    bearer_token = config['bearer-token']

    tweet_client = tweepy.Client(
            consumer_key=config['twitter-api-key'],
            consumer_secret=config['twitter-api-secret'],
            access_token=config['twitter-access-token'],
            access_token_secret=config['twitter-access-token-secret']
            )

    mastodon_client = Mastodon(access_token=config['mastodon-token'],
            api_base_url=config['mastodon-server'])
    
    signal-sender = config.get('signal-number', '')

class PhishStreamer(tweepy.StreamingClient):
    def on_response(self, response):
        if not any(r.tag == 'phish_ftr' for r in response.matching_rules):
            return
        
        text = response.data.text

        print('New @phish_ftr tweet:', text)

        print('\n***\n')
        
        if re.match(r'(\d+/\d+/\d+)', text):
            return

        title_to_match = (text if ':' not in text 
                                    else text.split(':')[1].strip())

        title_to_match = title_to_match.lstrip('> ')

        tweet_content = ''

        try:
            tweet_content = hfbot.helping_friendly(title_to_match)
        except:
            print('Hit an exception trying to match')

        if tweet_content:
            time.sleep(5)

            try:
                tweet_client.create_tweet(
                        in_reply_to_tweet_id=response.data.id,
                        text=tweet_content)
            except tweepy.errors.Forbidden:
                print('Tweet seems to be deleted. Skipping!')
                return

            try:
                mastodon_client.toot(tweet_content)
            except Exception as e:
                print(e)

        for sub in subscribers:
            output_string = hfbot.helping_friendly(
                                title_to_match, sub['username'])

            if not output_string:
                output_string = f":( @phish_ftr tweeted something I " \
                                f"couldn't figure out: {text}"
            print(*textwrap.wrap(output_string, 
                                 width=os.get_terminal_size().columns-2),
                    sep='\n')

            print('---')

            command = (f'signal-cli -a {signal-sender} send -m')

            split_command = command.split()
            subprocess.run(split_command + [output_string] + [sub['number']],
                           stdout=subprocess.DEVNULL)


#    def on_errors(self, errors):
#        print(f'Received error code {errors}')
#        sys.exit(1)

def main():
    streamer = PhishStreamer(bearer_token)
    existing_rules = streamer.get_rules().data or []
    existing_rules = [r.id for r in existing_rules if r.tag == 'phish_ftr']
    if existing_rules:
        streamer.delete_rules(existing_rules)

    search_rule = 'from:phish_ftr -has:links -has:images -is:quote'

    print(f'Starting tweet streamer with the rule: {search_rule}')

    streamer.add_rules(tweepy.StreamRule(search_rule, tag='phish_ftr'))
    streamer.filter()

if __name__ == '__main__':
    main()
