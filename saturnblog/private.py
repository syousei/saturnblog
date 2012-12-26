#!/usr/bin/env python
# -*- coding: utf-8 -*-

################################################################################
#
# モジュールの読み込み
#
################################################################################

import sys, os, datetime, re, urllib, logging

from datetime import datetime
import pytz

import webapp2
from webapp2_extras import sessions

from google.appengine.ext import db
from google.appengine.ext import blobstore

from google.appengine.ext.webapp import template
template.register_template_library('saturnblog.lib.customfilters')

from google.appengine.ext import blobstore
from google.appengine.ext.webapp import blobstore_handlers

from google.appengine.api import images
from google.appengine.api import mail
from google.appengine.api import memcache
from google.appengine.api import taskqueue

import models, settings


################################################################################
#
# 定数
#
################################################################################

# ブログのURL
BLOG_URL = settings.BLOG_URL

# ブログのパス
BLOG_PATH = settings.BLOG_PATH

# 管理画面のURL
ADMIN_URL = settings.ADMIN_URL

# 管理画面のパス
ADMIN_PATH = settings.ADMIN_PATH

# セッションの暗号化キー
SESSION_SECRET_KEY = settings.SESSION_SECRET_KEY


################################################################################
#
# リクエストハンドラー
#
################################################################################

# ベース
class BaseHandler(webapp2.RequestHandler):

    def render(self, template_file='', template_values={}):

        template_values['BLOG_URL'] = BLOG_URL
        template_values['BLOG_PATH'] = BLOG_PATH
        template_values['ADMIN_URL'] = ADMIN_URL
        template_values['ADMIN_PATH'] = ADMIN_PATH

        path = os.path.join(os.path.dirname(__file__), template_file)
        self.response.out.write(template.render(path, template_values))

    def dispatch(self):
        self.session_store = sessions.get_store(request=self.request)
        try:
            webapp2.RequestHandler.dispatch(self)
        finally:
            self.session_store.save_sessions(self.response)

    @webapp2.cached_property
    def session(self):
        return self.session_store.get_session()


################################################################################

# ホーム
class HomeHandler(BaseHandler):

    def get(self):

        query = models.Entry.all()
        query.order('-published_at')
        entries = query.fetch(10)

        template_values = {
            'page_title' : u'ホーム',
            'entries' : entries,
        }

        self.render('templates/private/home.html', template_values)


################################################################################

# （管理）エントリー一覧
class EntriesHandler(BaseHandler):

    def get(self):

        if self.request.get('category') == '':
            query = models.Entry.all()
            query.order('-published_at')
            entries = query.fetch(query.count())
            template_values = {
                'page_title' : u'ブログ記事一覧',
                'entries' : entries,
            }

        elif self.request.get('category') != '':
            key_name = self.request.get('category')
            category = models.Category.get_by_key_name(key_name)
            query = models.Entry.all()
            query.filter('category = ', category)
            query.order('-published_at')
            entries = query.fetch(query.count())
            template_values = {
                'page_title' : u'%sのブログ記事一覧' % category.name,
                'category' : category,
                'entries' : entries,
            }

        self.render('templates/private/entries.html', template_values)


################################################################################

# （管理）エントリー個別
class EntryHandler(BaseHandler):

    def get(self):

        token = models.generate_random_string(64)
        self.session['token'] = token

        query = models.Category.all()
        query.order('order')
        categories = query.fetch(query.count())

        if self.request.get('mode') == 'new':

            template_values = {
                'mode' : 'new',
                'page_title' : u'ブログ記事の新規作成',
                'token' : token,
                'entry' : { 'published_at' : datetime.now() },
                'categories' : categories,
            }

        elif self.request.get('mode') == 'edit':
            entry = models.Entry.get_by_key_name(self.request.get('key_name'))
            template_values = {
                'mode' : 'edit',
                'page_title' : u'ブログ記事の編集',
                'token' : token,
                'entry' : entry,
                'categories' : categories,
            }

        self.render('templates/private/entry.html', template_values)


    def post(self):

        if self.request.get('token') != self.session.get('token'):
            logging.info('INVALID TOKEN')
            exit()

        key_name = self.request.get('key_name')
        title = self.request.get('title')
        description = self.request.get('description')
        keywords = self.request.get('keywords')
        body = self.request.get('body')
        published_date = self.request.get('published_date')
        published_time = self.request.get('published_time')
        category = self.request.get('category')
        status = self.request.get('status')

        blog = models.Blog.get_or_insert('default')

        if key_name == '':
            serial_number = blog.last_serial_number_entry + 1
            key_name = 'entry-%s' % str(serial_number)
            blog.last_serial_number_entry += 1
            blog.put()

        keywords = keywords.split(',')
        keywords = [keyword.strip() for keyword in keywords]

        published_at = '%s %s' % (published_date, published_time)
        published_at = datetime.strptime(published_at, '%Y/%m/%d %H:%M')
        published_at = published_at.replace(tzinfo=pytz.timezone('Asia/Tokyo'))
        published_at = published_at.astimezone(pytz.utc)

        if category == '':
            category = None
        else:
            category = models.Category.get_by_key_name(category)

        path = '%04d/%02d/%02d/%s' % (
            published_at.year,
            published_at.month,
            published_at.day,
            str(key_name.lstrip('entry-')),
        )

        permalink = '%s%s' % (BLOG_URL, path)

        next_entry = None
        query = models.Entry.all()
        query.filter('published_at > ', published_at)
        query.filter('status = ', 'published')
        query.order('published_at')
        next_entry = query.get()

        prev_entry = None
        query = models.Entry.all()
        query.filter('published_at < ', published_at)
        query.filter('status = ', 'published')
        query.order('-published_at')
        prev_entry = query.get()

        try:
            entry = models.Entry(
                key_name = key_name,
                title = title,
                description = description,
                keywords = keywords,
                body = body,
                published_at = published_at,
                category = category,
                status = status,
                is_temporary = False,
                path = path,
                permalink = permalink,
                next_entry = next_entry,
                prev_entry = prev_entry,
            ).put()

            if next_entry:
                next_entry.prev_entry = entry
                next_entry.put()

            if prev_entry:
                prev_entry.next_entry = entry
                prev_entry.put()

            if status == 'published':
                taskqueue.add(
                    url='%s/worker/update/recent_entries' % ADMIN_PATH,
                    params={ 'entry_key_name': key_name }
                )
                #taskqueue.add(
                #    url='%s/worker/update/tweet_status' % ADMIN_PATH,
                #    params={ 'entry_key_name': key_name }
                #)

            self.redirect('%s/entry/?mode=edit&key_name=%s' % (
                    ADMIN_PATH,
                    key_name,
                )
            )
        except:
            self.error(500)


################################################################################

# 最近のブログ記事を更新
class UpdateRecentEntriesWorker(webapp2.RequestHandler):
    def post(self):
        query = models.Entry.all()
        query.filter('status = ', 'published')
        query.order('-published_at')
        recent_entries = query.fetch(10)
        memcache.set('recent_entries', recent_entries)


################################################################################

# ブログ記事の新規作成をTwitterにポスト
class UpdateTweetStatusWorker(webapp2.RequestHandler):
    def post(self):
        entry_key_name = self.request.get('entry_key_name')
        entry = models.Entry.get_by_key_name(entry_key_name)
        if not entry.tweet_url:
            import simplejson
            import tweepy
            auth = tweepy.OAuthHandler(
                    settings.TWITTER_CONSUMER_KEY,
                    settings.TWITTER_CONSUMER_SECRET
                )
            auth.set_access_token(
                    settings.TWITTER_ACCESS_TOKEN,
                    settings.TWITTER_ACCESS_TOKEN_SECRET
                )
            status = '%s - %s' % (entry.title, entry.permalink)
            api = tweepy.API(auth)
            result = api.update_status(status)
            result = simplejson.loads(result)
            tw_screen_name = result[u'user'][u'screen_name']
            tw_id = result.dict[u'id_str']
            entry.tweet_url = 'https://twitter.com/%s/status/%s' % (screen_name, id)
            entry.put()


################################################################################

# コメント一覧
class CommentsHandler(BaseHandler):

    def get(self):
        query = models.Comment.all()
        query.order('-posted_at')
        comments = query.fetch(query.count())
        template_values = {
            'page_title' : u'コメント一覧',
            'comments' : comments,
        }
        self.render('templates/private/comments.html', template_values)

    def post(self):
        key_names = self.request.get_all('key_name')
        comments = None
        comments = models.Comment.get_by_key_name(key_names)
        for comment in comments:
            try:
                spammer = models.Spammer(
                    key_name = 'spammer-%s' % comment.remote_addr,
                    remote_addr = comment.remote_addr,
                ).put()
                comment.delete()
            except:
                pass
        self.redirect('/saturnblog/comments')

################################################################################

# アイテム一覧
class ItemsHandler(BaseHandler):

    def get(self):
        query = blobstore.BlobInfo.all()
        query.order('-creation')
        blob_infos = query.fetch(25)
        template_values = {
            'page_title' : u'アイテムの一覧',
            'blob_infos' : blob_infos,
        }
        self.render('templates/private/items.html', template_values)

    def post(self):
        key_names = self.request.get_all('key_name')
        items = models.Item.get_by_key_name(key_names)
        blob_keys = []
        for item in items:
            blob_keys.append(item.blob)
        blobstore.delete(blob_keys)
        db.delete(items)
        self.redirect('%s/items' % ADMIN_PATH)


################################################################################

# アイテム
class ItemHandler(BaseHandler):
    def get(self):

        token = models.generate_random_string(64)
        self.session['token'] = token
        template_values = { 'token' : token }

        blob_key = self.request.get('blob_key')
        item_key = self.request.get('item_key')

        if blob_key:
            blob = None
            blob= blobstore.BlobInfo.get(blob_key)
            if blob is not None:
                template_values['blob'] = blob


        elif item_key:
            item = None
            item = models.Item.get_by_key_name(item_key)
            if item is not None:
                template_values = {
                    'upload_url' : upload_url,
                    'token' : token,
                }

        else:
            upload_url = blobstore.create_upload_url('/%s/items' % ADMIN_PATH)
            template_values = {
                'page_title' : u'アイテムの新規作成',
                'upload_url' : upload_url,
                'token' : token,
            }

        self.render('templates/private/item.html', template_values)

    def post(self):
        if self.request.get('token') != self.session.get('token'):
            logging.info('INVALID TOKEN')
            exit()
        file_key = self.request.get('file_key')
        name = self.request.get('name')
        description = self.request.get('description')

        item = models.Item(
            key_name = item_key,
            name = name,
            description = description,
            blog_key = blob_info,
        ).put()

        self.redirect('%s/item?item_key=%s' % (ADMIN_PATH, item.name()))


################################################################################

# アイテムのアップロード
class ItemUploadHandler(blobstore_handlers.BlobstoreUploadHandler):
    def post(self):
        upload_files = self.get_uploads('file')
        blob_info = upload_files[0]
        self.redirect('/item?file_key=%s' % blob_info.key())


################################################################################

# アイテムの編集
class ItemEditHandler(BaseHandler):
    def get(self):
        token = models.generate_random_string(64)
        self.session['token'] = token

        item_key = self.request.get('item_key')
        item = None
        if item_key:
            item = models.Item.get_by_key_name(item_key)
        if item is not None:
            template_values = {
                'page_title' : u'%sの編集' % item.Name,
                'token' : token,
                'item' : item,
            }
            self.render('templates/private/item-edit.html', template_values)
        else:
            self.error(404)


################################################################################

# （管理）アイテムのサーブ
class ItemServeHandler(blobstore_handlers.BlobstoreDownloadHandler):
    def get(self, resource=None):
        if resource is not None:
            resource = str(urllib.unquote(resource))
        width = self.request.get('width')
        width = int(width) if width.isdigit() else None
        height= self.request.get('height')
        height = int(height) if height.isdigit() else None
        blob_info = blobstore.BlobInfo.get(resource)
        if blob_info is not None:
            if blob_info.content_type.startswith('image/') and (width or height):
                image = images.Image(blob_key=blob_info.key())
                if width and height:
                    image.resize(width=width, height=height)
                elif width:
                    image.resize(width=width)
                elif height:
                    image.resize(height=height)
                thumb = image.execute_transforms(output_encoding=images.PNG)
                self.response.headers['Content-Type'] = "image/png"
                self.response.out.write(thumb)
                return
            else:
                self.send_blob(blob_info)
        else:
            self.error(404)


################################################################################

# （管理）カテゴリー一覧
class CategoriesHandler(BaseHandler):

    def get(self):

        query = models.Category.all()
        query.order('order')
        categories = query.fetch(query.count())

        template_values = {
            'page_title' : u'カテゴリー一覧',
            'categories' : categories,
        }

        self.render('templates/private/categories.html', template_values)

    def post(self):

        key_names = self.request.get_all('key_name')

        categories = models.Category.get_by_key_name(key_names)
        db.delete(categories)

        self.redirect('%s/categories' % ADMIN_PATH)


################################################################################

# （管理）カテゴリー
class CategoryHandler(BaseHandler):

    def get(self):

        token = models.generate_random_string(64)
        self.session['token'] = token

        mode = self.request.get('mode')

        if mode == 'new':
            template_values = {
                'page_title' : u'カテゴリーの新規作成',
                'token' : token,
                'category' : { 'name' : u'新規カテゴリー' },
            }

        elif mode == 'edit':
            key_name = self.request.get('key_name')
            category = models.Category.get_by_key_name(key_name)
            template_values = {
                'page_title' : u'カテゴリーの編集',
                'token' : token,
                'category' : category,
            }

        self.render('templates/private/category.html', template_values)


    def post(self):

        if self.request.get('token') != self.session.get('token'):
            logging.info('INVALID TOKEN')
            exit()

        key_name = self.request.get('key_name')
        name = self.request.get('name')
        path = self.request.get('path')
        description = self.request.get('description')
        keywords = self.request.get('keywords')
        order = self.request.get('order')

        blog = models.Blog.get_by_key_name('default')

        if key_name == '':
            serial_number = blog.last_serial_number_category + 1
            key_name = 'category-%s' % str(serial_number)
            blog.last_serial_number_category += 1
            blog.put()

        keywords = keywords.split(',')
        keywords = [keyword.strip() for keyword in keywords]

        entry = models.Category(
            key_name = key_name,
            name = name,
            path = path,
            description = description,
            keywords = keywords,
            order = int(order),
        ).put()

        query = models.Category.all()
        query.order('order')
        categories = query.fetch(query.count())
        memcache.set('categories', categories)

        self.redirect('%s/category/?mode=edit&key_name=%s' % (
                ADMIN_PATH,
                key_name
            )
        )


################################################################################

# （管理）設定・ブログ
class BlogHandler(BaseHandler):

    def get(self):

        token = models.generate_random_string(64)
        self.session['token'] = token

        blog = models.Blog.get_by_key_name('default')

        template_values = {
            'page_title' : u'ブログ設定',
            'token' : token,
            'blog' : blog,
        }

        self.render('templates/private/blog.html', template_values)

    def post(self):

        if self.request.get('token') != self.session.get('token'):
            logging.info('INVALID TOKEN')
            exit()

        name = self.request.get('name')
        description = self.request.get('description')
        keywords = self.request.get('keywords')
        url = self.request.get('url')
        path = self.request.get('path')
        admin_url = self.request.get('admin_url')
        admin_path = self.request.get('admin_path')


        keywords = keywords.split(',')
        keywords = [keyword.strip() for keyword in keywords]

        blog = models.Blog.get_or_insert('default')
        blog.name = name
        blog.description = description
        blog.keywords = keywords
        blog.put()

        memcache.set('blog', blog)

        self.redirect('%s/settings/blog/' % ADMIN_PATH)


################################################################################

# プロフィール
class ProfileHandler(BaseHandler):

    def get(self):

        profile = models.Profile.get_by_key_name('default')
        if profile is None:
            profile = {}

        template_values = {
            'page_title' : u'プロフィール設定',
            'profile' : profile,
        }

        self.render('templates/private/profile.html', template_values)

    def post(self):

        name = self.request.get('name')
        picture = self.request.get('picture')
        oneline = self.request.get('oneline')
        introduction = self.request.get('introduction')
        keywords = self.request.get('keywords')

        keywords = keywords.split(',')
        keywords = [keyword.strip() for keyword in keywords]

        profile = models.Profile.get_or_insert('default')
        profile.name = name
        profile.oneline = oneline
        profile.introduction = introduction
        profile.keywords = keywords
        profile.put()

        memcache.set('profile', profile)

        self.redirect('%s/settings/profile' % ADMIN_PATH)


################################################################################
#
# URIルーティング
#
################################################################################

handlers = [
    (ADMIN_PATH + '/?', HomeHandler),
    (ADMIN_PATH + '/entries/?', EntriesHandler),
    (ADMIN_PATH + '/entry/?', EntryHandler),
    (ADMIN_PATH + '/comments/?', CommentsHandler),
    (ADMIN_PATH + '/items/?', ItemsHandler),
    (ADMIN_PATH + '/item/?', ItemHandler),
    (ADMIN_PATH + '/item/upload/?', ItemUploadHandler),
    (ADMIN_PATH + '/item/serve/([^/]+)?', ItemServeHandler),
    (ADMIN_PATH + '/categories/?', CategoriesHandler),
    (ADMIN_PATH + '/category/?', CategoryHandler),
    (ADMIN_PATH + '/settings/blog/?', BlogHandler),
    (ADMIN_PATH + '/settings/profile/?', ProfileHandler),
    (ADMIN_PATH + '/worker/update/recent_entries/?', UpdateRecentEntriesWorker),
]


################################################################################
#
# WSGIアプリケーションの設定
#
################################################################################

config = {}
config['webapp2_extras.sessions'] = {
    'secret_key' : SESSION_SECRET_KEY,
}

# WSGIアプリケーション
app = webapp2.WSGIApplication(
    handlers,
    debug = True,
    config = config,
)
