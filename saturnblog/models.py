#!/usr/bin/env python
# -*- coding: utf-8 -*-

import random, datetime

from google.appengine.ext import db
from google.appengine.ext import blobstore

################################################################################
#
# データストアのモデル
#
################################################################################

# ブログの設定
class Blog(db.Model):
    # blog
    name = db.StringProperty()
    description = db.StringProperty()
    keywords = db.StringListProperty()
    # status
    last_serial_number_entry = db.IntegerProperty(default=0)
    last_serial_number_comment = db.IntegerProperty(default=0)
    last_serial_number_item = db.IntegerProperty(default=0)
    last_serial_number_category = db.IntegerProperty(default=0)
    # Entry List
    recent_entries_key_names = db.StringListProperty(default=[])


################################################################################

# アイテム
class Item(db.Model):
    name = db.StringProperty(required=True)
    description = db.TextProperty()
    created_at = db.DateTimeProperty(required=True, auto_now_add=True)
    blob = blobstore.BlobReferenceProperty(required=True)


################################################################################

# カテゴリー
class Category(db.Model):
    name = db.StringProperty(required=True)
    path = db.StringProperty(required=True)
    description = db.TextProperty()
    keywords = db.StringListProperty()
    order = db.IntegerProperty(required=True)

    def count_entries(self):
        query = Entry.all()
        query.filter('category = ', self)
        query.filter('status = ', 'published')
        return query.count()


################################################################################

# ブログ記事
class Entry(db.Model):
    title = db.StringProperty()
    description = db.TextProperty()
    keywords = db.StringListProperty()
    body = db.TextProperty()
    published_at = db.DateTimeProperty(auto_now_add=True)
    category = db.ReferenceProperty(Category, default=None)
    status = db.StringProperty(
        choices=('draft', 'programmed', 'published'),
        default='draft',
    )
    path = db.StringProperty()
    permalink = db.StringProperty()
    next_entry = db.SelfReferenceProperty(collection_name='next_entry_set')
    prev_entry = db.SelfReferenceProperty(collection_name='prev_entry_set')
    tweet_url = db.StringProperty()


    def count_comments(self):
        query = Comment.all()
        query.filter('entry = ', self)
        return query.count()

    def get_comments(self):
        query = Comment.all()
        query.filter('entry = ', self)
        query.order('-posted_at')
        return query.fetch(query.count())


################################################################################

# コメント
class Comment(db.Model):
    author = db.StringProperty(required=True)
    body = db.TextProperty(required=True)
    posted_at = db.DateTimeProperty(required=True, auto_now_add=True)
    entry = db.ReferenceProperty(required=True, reference_class=Entry, default=None)
    remote_addr = db.StringProperty(required=True)


################################################################################

# プロフィール
class Profile(db.Model):
    name = db.StringProperty()
    picture = db.BlobProperty()
    oneline = db.StringProperty()
    introduction = db.TextProperty()
    keywords = db.StringListProperty()


################################################################################

# スパマー
class Spammer(db.Model):
    remote_addr = db.StringProperty()

################################################################################
#
# 関数
#
################################################################################

# スパム判定
def is_spammer(remote_addr):
    key_name = 'spammer-%s' % remote_addr
    result = None
    result = Spammer.get_by_key_name(key_name)
    if spammer is None:
        return False
    else:
        return True


################################################################################

# ブログ記事とそれに付いたコメントを取得
def get_entry_and_comments(entry_key):
    entry = None
    comments = None
    entry = Entry.get_by_key_name(entry_key)
    if entry is not None:
        query = Comment.all()
        query.filter('entry = ', entry)
        comments = query.fetch(1000)
    return entry, comments


################################################################################

# a-zA-Zで始まるランダムな文字列を生成
def generate_random_string(length=16):
    seed_numbers = ['1','2','3','4','5','6','7','8','9','0']
    seed_alphabets = [
        'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n',
        'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z',
        'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N',
        'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z'
    ]
    str = random.choice(seed_alphabets)
    seed_mix = seed_numbers + seed_alphabets
    for i in range(length-1):
        str += random.choice(seed_mix)
    return(str)


################################################################################

# Datastoreエンティティのkey_nameを生成
def generate_key_name(kind, digit=16):
    key_name = generate_random_string(digit)
    if kind.get_by_key_name(key_name):
        generate_key_name(kind, digit)
    else:
        return key_name


################################################################################

# EOF