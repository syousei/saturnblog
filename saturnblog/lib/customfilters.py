#!-*- coding:utf-8 -*-

import datetime

from google.appengine.ext.webapp import template

register = template.create_template_register()

# UTCをJSTにする
@register.filter
def jst(value=None):
    if isinstance(value, datetime.datetime):
        return value + datetime.timedelta(hours=9)

# 指定した文字数で切り、末尾に…を付ける
@register.filter
def truncatewords2(value, arg):
    value = value.strip()
    if len(value) <= arg:
        return value
    arg -= 1
    return value[:arg].strip() + u'…'
