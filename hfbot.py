#! /bin/env python3

import json
import os
import sqlite3
import sys
import time
import textwrap

import requests
import yaml

from datetime import datetime, timedelta

from slugify import slugify
from thefuzz import fuzz, process
from tqdm import tqdm

API_ROOT = 'https://api.phish.net/v5'

with open('apikeys.yaml') as f:
    config = yaml.safe_load(f)
    apikey = config['api-key']

def update_songs_list():
    songs = requests.get(f'{API_ROOT}/songs.json?apikey={apikey}').json()['data']

    song_dict = {s['song']: s['slug'] for s in songs}
    song_dict.update({s['abbr']: s['slug'] for s in songs if s['abbr']})

    with open('slugs.json', 'w') as f:
        json.dump(song_dict, f, indent=4)

def update_cached_songs():
    update_songs_list()

    with open('slugs.json', 'r') as f:
        songs = json.load(f)

    slugs = set(songs.values())

    for s in tqdm(slugs):
        try:
            get_song_data(s, ttl=7200)
            time.sleep(2)
        except:
            pass

def get_song_slug(title):
    with open('slugs.json') as f:
        slug_dict = json.load(f)

    matched_song_title, confidence = process.extractOne(
                    title, list(slug_dict.keys()))

    song_slug = (slug_dict.get(matched_song_title) if confidence > 90 else
                    slugify(title, 
                    replacements=[[c, ''] for c in "/'.:"]))

    return song_slug


def get_song_data(slug, ttl=999979200):
    """Given a song slug, return the `data` blob from local sqlite db or, \
    if older than `ttl` seconds, Phish.net API"""
    conn = sqlite3.connect('phishnetcache.db',
                            detect_types=sqlite3.PARSE_DECLTYPES)
    conn.execute('create table if not exists songs (id integer primary key, slug text, data_blob text, last_update timestamp)')

    cached_song_data = conn.execute('select * from songs where slug=?', 
                                    (slug,)).fetchone()

    if (cached_song_data and 
            cached_song_data[3] + timedelta(seconds=ttl) > datetime.now()):
        song_data = json.loads(cached_song_data[2])
    else:
        song_search = requests.get(f'{API_ROOT}/songs/slug/{slug}.json'
                                   f'?apikey={apikey}').json()
        if not song_search['data']:
            raise Exception('Could not find that song in the Phish.net database.')

        song_data = song_search['data'][0]

        if cached_song_data:
            conn.execute('update songs set data_blob=?, last_update=? '
                         'where id=?', (json.dumps(song_data), datetime.now(),
                         cached_song_data[0]))
        else:
            conn.execute('insert into songs (slug, data_blob, last_update) '
                         'values (?, ?, ?)', (slug, json.dumps(song_data), 
                          datetime.now()))
        conn.commit()

    conn.close()
    return song_data


def get_shows_for_song(slug, ttl=79200):
    """Given a song slug, return the `data` blob of shows where it  was played"""

    conn = sqlite3.connect('phishnetcache.db',
                            detect_types=sqlite3.PARSE_DECLTYPES)
    conn.execute('create table if not exists shows (id integer primary key, slug text, data_blob text, last_update timestamp)')

    cached_show_data = conn.execute('select * from shows where slug=?', 
                                    (slug,)).fetchone()

    if (cached_show_data and 
            cached_show_data[3] + timedelta(seconds=ttl) > datetime.now()):
        show_data = json.loads(cached_show_data[2])
    else:
        show_data = requests.get(f"{API_ROOT}/setlists/slug/{slug}.json?apikey={apikey}").json()['data']

        if cached_show_data:
            conn.execute('update shows set data_blob=?, last_update=? '
                         'where id=?', (json.dumps(show_data), datetime.now(),
                         cached_show_data[0]))
        else:
            conn.execute('insert into shows (slug, data_blob, last_update) '
                         'values (?, ?, ?)', (slug, json.dumps(show_data), 
                          datetime.now()))
        conn.commit()

    conn.close()

    show_data = [s for s in show_data if s['artist_name'] == 'Phish']
    show_data = sorted(show_data, key=lambda s: s['showdate'])
    return show_data


def get_shows_attended(username, ttl=14400):
    conn = sqlite3.connect('phishnetcache.db',
                            detect_types=sqlite3.PARSE_DECLTYPES)
    conn.execute('create table if not exists users (id integer primary key, username text, data_blob text, last_update timestamp)')

    cached_user_data = conn.execute('select * from users where username=?', 
                                    (username,)).fetchone()

    if (cached_user_data and 
            cached_user_data[3] + timedelta(seconds=ttl) > datetime.now()):
        user_show_data = json.loads(cached_user_data[2])
    else:
        user_show_data = requests.get(f'{API_ROOT}/attendance/username/'
                                      f'{username}.json?apikey={apikey}'
                                      ).json()['data']

        if cached_user_data:
            conn.execute('update users set data_blob=?, last_update=? '
                         'where id=?', (json.dumps(user_show_data), 
                                        datetime.now(),
                                        cached_user_data[0]))
        else:
            conn.execute('insert into users (username, data_blob, last_update) '
                         'values (?, ?, ?)', (username, 
                                              json.dumps(user_show_data), 
                                              datetime.now()))
        conn.commit()

    conn.close()

    user_show_data = [s for s in user_show_data if s['artist_name'] == 'Phish']
    user_show_data = sorted(user_show_data, key=lambda s: s['showdate'])
    return user_show_data

def helping_friendly(song, gap='', username=None):
    slug = get_song_slug(song)

    try:
        song_data = get_song_data(slug)
    except Exception as e:
        return None        

    if gap:
        song_data['gap'] = gap
    else:
        song_data['gap'] = str(int(song_data['gap']) + 1)

    shows_where_played = get_shows_for_song(slug)

    output_string = f"This is {song_data['song']}"
    if song_data['artist'] != 'Phish':
        output_string += f" by {song_data['artist']}"
    if len(shows_where_played) >= 2:
        output_string += f", last played {song_data['last_played']} ({song_data['gap']} shows ago)."
    if int(song_data['gap']) > 100:
        output_string += " A bust-out!"

    output_string += f" Phish have played this song {song_data['times_played']} "
    output_string += "time" if song_data['times_played'] == '1' else "times"
    output_string += f" since {song_data['debut']}."
    if int(song_data['times_played']) < 10:
        output_string += " A rare one!"

    if username:
        shows_attended = get_shows_attended(username)
        
        shows_where_played_id_list = [s['showid'] for s in shows_where_played]
        shows_where_seen = [s for s in shows_attended if s['showid'] in
                                shows_where_played_id_list]

        # Sometimes phish.net has already added the current show to its API.
        # This removes that show from the data if it's present.
        today_string = datetime.today().strftime('%Y-%m-%d')
        if shows_where_seen and shows_where_seen[-1]['showdate'] == today_string:
            shows_where_seen.pop(-1)

        if not shows_where_seen:
            output_string += " You have not seen this song before!"
        else:
            most_recent_show = shows_where_seen[-1]
            if len(shows_where_seen) == 1:
                output_string += f" You have seen this song once before, "
            else:
                output_string += f" You have seen this song "\
                                 f"{len(shows_where_seen)} times before,"\
                                 f" most recently "
            output_string += f"on {most_recent_show['showdate']} at "\
                             f"{most_recent_show['venue']} in "\
                             f"{most_recent_show['city']}."

    return output_string


def main():
    try:
        output_string = helping_friendly(str(sys.argv[1:]))
    except Exception as e:
        print('***ERROR!', str(e))

    print(*textwrap.wrap(output_string, width=os.get_terminal_size().columns), sep='\n')

if __name__ == '__main__':
    main()
