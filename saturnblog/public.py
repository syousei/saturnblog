#!/usr/bin/env python
# -*- coding: utf-8 -*-

################################################################################
#
# モジュールの読み込み
#
################################################################################

import os, logging, urllib

from datetime import datetime

import webapp2
from webapp2_extras import sessions

from google.appengine.ext import blobstore
from google.appengine.ext.webapp import blobstore_handlers

from google.appengine.ext.webapp import template
template.register_template_library('saturnblog.lib.customfilters')

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

        blog = memcache.get('blog')
        if blog is not None:
            template_values['blog'] = blog
        else:
            logging.info("Memcached can't get blog.")
            blog = models.Blog.get_by_key_name('default')
            template_values['blog'] = blog
            memcache.set('blog', blog)

        profile = memcache.get('profile')
        if profile is not None:
            template_values['profile'] = profile
        else:
            logging.info("Memcached can't get profile.")
            profile = models.Profile.get_by_key_name('default')
            template_values['profile'] = profile
            memcache.set('profile', profile)

        categories = memcache.get('categories')
        if categories is not None:
            template_values['categories'] = categories
        else:
            logging.info("Memcached can't get categories.")
            query = models.Category.all()
            query.order('order')
            categories = query.fetch(query.count())
            template_values['categories'] = categories
            memcache.set('categories', categories)

        recent_entries = memcache.get('recent_entries')
        if recent_entries is not None:
            template_values['recent_entries'] = recent_entries
        else:
            logging.info("Memcached can't get recent_entries.")
            query = models.Entry.all()
            query.filter('status = ', 'published')
            query.order('-published_at')
            recent_entries = query.fetch(10)
            template_values['recent_entries'] = recent_entries
            memcache.set('recent_entries', recent_entries)

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

# アイテムのサーブ
class ItemServeHandler(blobstore_handlers.BlobstoreDownloadHandler):

    def get(self, blob_key=None):
        if blob_key is not None:
            blog_key = str(urllib.unquote(blob_key))
        width = self.request.get('width')
        width = int(width) if width.isdigit() else None
        height= self.request.get('height')
        height = int(height) if height.isdigit() else None
        blob_info = blobstore.BlobInfo.get(blob_key)
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
#        blob_info = blobstore.BlobInfo.get(blob_key)
#        self.send_blob(blob_info)


################################################################################

# ホーム
class HomeHandler(BaseHandler):

    def get(self):

        query = models.Entry.all()
        query.filter('status = ', 'published')
        query.order('-published_at')
        entries = query.fetch(20)

        template_values = {
            'page_title' : u'ホーム',
            'entries' : entries,
        }

        self.render('templates/public/home.html', template_values)


################################################################################

# カテゴリー
class CategoryHandler(BaseHandler):

    def get(self, path=None):

        if path is not None:

            query = models.Category.all()
            query.filter('path = ', path)
            category = query.get()

            query = models.Entry.all()
            query.filter('category = ', category)
            query.filter('status = ', 'published')
            query.order('-published_at')
            entries = query.fetch(query.count())

            template_values = {
                'page_title' : category.name,
                'category' : category,
                'entries' : entries,
            }

            self.render('templates/public/category.html', template_values)

        else:
          self.error(404)


################################################################################

# エントリー一覧（年）
class EntryByYearHandler(BaseHandler):

    def get(self, year=None):

        if year is not None:
            """
            filter_from = '%s-12-31 23:59:59' % str(int(year)-1)
            filter_from = datetime.strptime(filter_from, '%Y-%m-%d %H:%M:%S')
            filter_to = '%s-01-01 00:00:00' % str(int(year)+1)
            filter_to = datetime.strptime(filter_to, '%Y-%m-%d %H:%M:%S')

            query = models.Entry.all()
            query.filter('published_at > ', filter_from)
            query.filter('published_at < ', filter_to)
            query.filter('stauts = ', 'published')
            query.order('-published_at')
            entries = query.fetch(query.count())

            template_values = {
                'page_title' : u'%s年のブログ記事' % year,
                'entries' : entries,
                'from' : filter_from,
                'to' : filter_to,
            }
            """
            template_values = { 'page_title' : u'年のブログ記事' }
            self.render('templates/public/entries.html', template_values)

        else:
            self.error(404)

################################################################################

# エントリー一覧（年月）
class EntryByMonthHandler(BaseHandler):

    def get(self, year=None, month=None):

        if year is not None and month is not None:

            template_values = { 'page_title' : u'年月のブログ記事' }
            self.render('templates/public/entries.html', template_values)

        else:
            self.error(404)

################################################################################

# エントリー一覧（年月日）
class EntryByDayHandler(BaseHandler):

    def get(self, year=None, month=None, day=None):

        if year is not None and month is not None and day is not None:

            template_values = { 'page_title' : u'年月日のブログ記事' }
            self.render('templates/public/entries.html', template_values)

        else:
            self.error(404)

################################################################################

# エントリー（パーマリンク）
class EntryHandler(BaseHandler):

    def get(self, year=None, month=None, day=None, serial_number=None):
        entry = None
        entry_key = 'entry-%s' % serial_number
        entry = models.Entry.get_by_key_name(entry_key)
        if entry is None or entry.status != 'published':
                self.error(404)
                exit()

        import markdown
        entry.body = markdown.markdown(entry.body)

        comments = None
        query = models.Comment.all()
        query.filter('entry = ', entry)
        query.order('posted_at')
        comments = query.fetch(query.count())

        template_values = {
            'page_title' : entry.title,
            'entry' : entry,
            'comments': comments,
        }
        self.render('templates/public/entry.html', template_values)

    def post(self, year=None, month=None, day=None, serial_number=None):

        if not serial_number:
            self.error(404)
            exit()

        entry = None
        entry_key = 'entry-%s' % serial_number
        entry = models.Entry.get_by_key_name(entry_key)
        if entry is None or entry.status != 'published':
            self.error(404)
            exit()

        blog = None
        blog = models.Blog.get_or_insert('default')
        if blog is None:
            self.error(404)
            exit()

        spammer = None
        spammer = models.Spammer.get_by_key_name(
            'spammer-%s' % os.environ['REMOTE_ADDR']
        )
        if result is not None:
            self.error(500)
            exit()

        serial_number = blog.last_serial_number_comment + 1
        comment_key = 'comment-%s' % str(serial_number)
        blog.last_serial_number_comment += 1
        blog.put()

        author = self.request.get('author')
        body = self.request.get('body')

        try:
            comment = models.Comment(
                key_name = comment_key,
                author = author,
                body = body,
                entry = entry,
                remote_addr = os.environ['REMOTE_ADDR'],
            ).put()

            # 管理者にメールで通知
            mail_to = settings.ADMIN_MAIL
            mail_from = 'ishimaru.masato@gmail.com'
            mail_subject = 'ブログ記事にコメントが投稿されました'
            mail_body = '%s\n%s\n\n%s\n%s\n%s' % (
                entry.title,
                entry.permalink,
                datetime.now(),
                author,
                body,
            )
            mail.send_mail(mail_from, mail_to, mail_subject, mail_body)
            self.redirect('%s/%s#comments' % (BLOG_PATH, entry.path))
        except:
            self.error(500)


################################################################################

# トラックバック
class TrackBackHandler(BaseHandler):

    def post():

        pass

################################################################################

# RSS2.0
class RSSHandler(BaseHandler):

    def get(self):

        query = models.Entry.all()
        query.filter('status = ', 'published')
        query.order('-published_at')
        entries = query.fetch(20)

        template_values = {
            'entries' : entries,
            'pubDate' : entries[0].published_at,
            'lastBuildDate' : entries[0].published_at,
        }

        self.render('templates/public/rss2.0.xml', template_values)


################################################################################

# RSS2.0
class SitemapXMLHandler(BaseHandler):

    def get(self):

        query = models.Category.all()
        query.order('name')
        categories = query.fetch(query.count())

        query = models.Entry.all()
        query.filter('status = ', 'published')
        query.order('-published_at')
        entries = query.fetch(query.count())

        template_values = {
            'categoies' : categories,
            'entries' : entries,
            'pubDate' : entries[0].published_at,
            'lastBuildDate' : entries[0].published_at,
        }

        self.render('templates/public/sitemap.xml', template_values)


################################################################################
#
# URIルーティング
#
################################################################################

handlers = [
    (BLOG_PATH +'/?', HomeHandler),
    (BLOG_PATH +'/rss/?', RSSHandler),
    (BLOG_PATH +'/sitemap/?', SitemapXMLHandler),
    (BLOG_PATH +'/items/([^/]+)?', ItemServeHandler),
    (BLOG_PATH +'/trackback/(\d+)?', TrackBackHandler),
    (BLOG_PATH +'/(\d{4})/?', EntryByYearHandler),
    (BLOG_PATH +'/(\d{4})/(\d{2})/?', EntryByMonthHandler),
    (BLOG_PATH +'/(\d{4})/(\d{2})/(\d{2})/?', EntryByDayHandler),
    (BLOG_PATH +'/(\d{4})/(\d{2})/(\d{2})/(\d+)/?', EntryHandler),
    (BLOG_PATH +'/(\w+)/?', CategoryHandler),
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
    debug = False,
    config = config,
)
