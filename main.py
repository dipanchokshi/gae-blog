import webapp2
import os
import logging
import jinja2
import models
import config
import secure

from collections import Counter
from google.appengine.api import memcache
from google.appengine.ext import db


class BaseRequestHandler(webapp2.RequestHandler):
    """Supplies a common template generation function.
    generate() augments the template variables."""

    def generate(self, template_name, template_values={}):
        values = {}
        values.update(template_values)
        path = os.path.join(os.path.dirname(__file__), 'html/')
        jinja_environment = jinja2.Environment(
                                loader=jinja2.FileSystemLoader(path),
                                autoescape=False)
        template = jinja_environment.get_template(template_name)
        self.response.out.write(template.render(template_values))

    def generate_tag_list(self):
        tag_entries = db.GqlQuery("SELECT tag FROM BlogPost")
        tags_all = [str(item.tag) for item in tag_entries]  # excecute query
        c = Counter(tags_all)    # provides dict with count of each tag
        return sorted(c.iteritems())  # returns list w/ tuples in alpha. order

    def set_secure_cookie(self, name, value):
        hashed_user = secure.make_secure_val(value)
        self.response.headers.add_header('Set-Cookie', '%s=%s; Path=/'
                                            % (name, hashed_user))

    def remove_secure_cookie(self, name):
        self.response.headers.add_header('Set-Cookie', '%s=; Path=/' % name)

    def check_secure_cookie(self):
        try:
            user_id_cookie_val = self.request.cookies.get('user_id')
            user_id = user_id_cookie_val.split('|')[0]
            return secure.check_secure_val(user_id_cookie_val)
        except AttributeError:
            return None


def main_page_posts(update=False):
    key = 'main_page_posts'
    posts = memcache.get(key)
    if posts is None or update:
        logging.error('DB Query: Main Page')
        posts = db.GqlQuery("""
                                SELECT *
                                FROM BlogPost
                                ORDER BY created
                                DESC
                                LIMIT 10
                            """)
        memcache.set(key, posts)
    return posts


def tag_cache(tag_name, update=False):
    key = 'tag_%s' % tag_name
    tag = memcache.get(key)
    if tag is None or update:
        logging.error('DB Query: Tag')
        tag = db.GqlQuery("""
                                SELECT *
                                FROM BlogPost
                                WHERE tag='%s'
                            """
                            % tag_name)
        memcache.set(key, tag)
    return tag


class NewPostHandler(BaseRequestHandler):
    """Generages and Handles New Blog Post Entires."""

    def get(self):
        if self.check_secure_cookie():
            self.generate('newpost.html', {
                            'tag_list': self.generate_tag_list(),
                            'user': 'admin'
                         })
        else:
            self.redirect('/blog/login')
            return

    def post(self):
        subject = self.request.get('subject')
        content = self.request.get('content')
        content = content.replace('\n', '<br>')
        image_url = self.request.get('image_url')
        tag = self.request.get('tag')

        if subject and content and tag and image_url:
            blog_entry = models.BlogPost(subject=subject,
                                            content=content,
                                            image_url=image_url,
                                            tag=tag,
                                            author=config.blog_author)
            blog_entry.put()
            post_id = str(blog_entry.key().id())
            blog_entry.post_id = post_id
            blog_entry.put()
            main_page_posts(True)

            #rerun query and update the cache.
            tag_cache(tag, True)
            self.redirect('/blog/%s' % post_id)
            return
        else:
            self.generate('newpost.html', {
                            'newpost_error': 'Subject and content required.',
                            'subject': subject,
                            'content': content,
                            'image_url': image_url,
                            'tag': tag,
                            'tag_list': self.generate_tag_list(),
                            'user': 'admin'
                            })


class BlogPostHandler(BaseRequestHandler):
    """Main Blog Page Handler"""
    def get(self):
        user = None
        blog_entries = main_page_posts()
        if self.check_secure_cookie():
            user = 'admin'
        self.generate('blog.html', {'blog_entries': blog_entries,
                        'tag_list': self.generate_tag_list(),
                        'user': user
                        })


class PermalinkHandler(BaseRequestHandler):
    def get(self, post_id):
        """Generator of permalink page for each blog entry"""
        user = None

        # postid variable gets passed in (i.e. /blog/(\d+))
        post_num = int(post_id)
        blog_post = models.BlogPost.get_by_id(post_num)

        if self.check_secure_cookie():
            user = 'admin'
        if not blog_post:
            self.generate('404.html', {})
        else:
            self.generate('blogpost.html', {
                            'blog_post': blog_post,
                            'post_id': post_id,
                            'tag_list': self.generate_tag_list(),
                            'user': user
                            })


class TagHandler(BaseRequestHandler):
    """Tag Page Handler"""
    def get(self, tag_name):
        tag_list = dict(self.generate_tag_list())
        user = None
        if self.check_secure_cookie():
            user = 'admin'
        if tag_name not in tag_list.keys():
            self.redirect('/blog')
            return
        else:
            blog_entries = tag_cache(tag_name)
            self.generate('blog.html', {
                            'blog_entries': blog_entries,
                            'tag_list': self.generate_tag_list(),
                            'user': user
                            })


class LoginHandler(BaseRequestHandler):
    """Admin Login Page Handler"""
    def get(self):
        if self.check_secure_cookie():
            self.redirect('/blog')
            return
        else:
            self.generate('login.html', {})

    def post(self):
        username = str(self.request.get('username'))
        password = str(self.request.get('password'))

        user = models.Admin.login_validation(username)

        if user and secure.valid_pw(username, password, user.admin_pw_hash):
            if secure.valid_pw(username, password, user.admin_pw_hash):
                self.set_secure_cookie('user_id', str(user.key().id()))
                self.redirect('/blog/newpost')
                return
            else:
                self.generate('login.html', {
                                'username': username,
                                'error_login': 'Invalid rname and/or password'
                                 })
        else:
            self.generate('login.html', {
                            'error_login': 'User does not exist'
                             })


class LogoutHandler(BaseRequestHandler):
    """Logout Handler"""
    def get(self):
        self.remove_secure_cookie('user_id')
        self.redirect('/blog')
        return


class AboutHandler(BaseRequestHandler):
    """About Page Handler"""
    def get(self):
        user = None
        if self.check_secure_cookie():
            user = 'admin'
        self.generate('about.html', {
                        'tag_list': self.generate_tag_list(),
                        'user': user
                         })


class ContactHandler(BaseRequestHandler):
    """Contact Page Handler"""
    def get(self):
        user = None
        if self.check_secure_cookie():
            user = 'admin'
        self.generate('contact.html', {
                        'tag_list': self.generate_tag_list(),
                        'user': user
                        })


class AdminPrefHandler(BaseRequestHandler):
    """Admin Preferences Page Handler"""
    def get(self):
        user = None
        if not self.check_secure_cookie():
            self.redirect('/blog')
            return
        else:
            user = 'admin'
            self.generate('admin-pref.html', {'user': user})


class UsernameChangeHandler(BaseRequestHandler):
    """Change Username Page Handler"""
    def get(self):
        user = None
        if not self.check_secure_cookie():
            self.redirect('/blog')
            return
        else:
            user = 'admin'
        self.generate('username-change.html', {'user': user})

    def post(self):
        user = 'admin'
        new_username = str(self.request.get('new_username'))
        password = str(self.request.get('password'))

        user_id_cookie_val = self.request.cookies.get('user_id')
        u = models.Admin.get_user(user_id_cookie_val)

        if u and secure.valid_pw(u.admin_username, password, u.admin_pw_hash):
            if secure.valid_pw(u.admin_username, password, u.admin_pw_hash):
                u.admin_pw_hash = secure.make_pw_hash(new_username, password)
                u.admin_username = new_username
                u.put()
                self.generate('username-change.html', {
                                'error_change_username': 'Change successful.',
                                'user': user
                                             })
            else:
                self.generate('username-change.html', {
                              'new_username': new_username,
                              'error_change_username': 'Invalid password',
                              'user': user
                              })
        else:
            self.generate('login.html', {'error_login': 'User does not exist'
                                        })


class PasswordChangeHandler(BaseRequestHandler):
    def get(self):
        user = None
        if not self.check_secure_cookie():
            self.redirect('/blog')
            return
        else:
            user = 'admin'
            self.generate('pw-change.html', {'user': user})

    def post(self):
        user = 'admin'
        password = str(self.request.get('password'))
        verify_password = str(self.request.get('verify_password'))

        if password != verify_password:
            self.generate('pw-change.html', {
                    'error_change_pw': 'Passwords do not match. Please retry.',
                    'user': user
                    })
        elif len(password) < 6:
            self.generate('pw-change.html', {
                    'error_change_pw': 'Password must be greater than 6 char.',
                    'user': user
                    })
        else:
            user_id_cookie_val = self.request.cookies.get('user_id')
            user = models.Admin.get_user(user_id_cookie_val)
            user.admin_pw_hash = secure.make_pw_hash(
                                                user.admin_username, password)
            user.put()
            self.generate('pw-change.html', {
                                        'error_change_pw': 'Password changed.',
                                        'user': user
                                      })


class AdminHandler(BaseRequestHandler):
    #FOR TESTING PURPOSES ONLY
    def get(self):
        pw_hash = secure.make_pw_hash(config.admin_username, config.admin_pw)
        admin = models.Admin(admin_username=config.admin_username,
                                admin_pw_hash=pw_hash)
        admin.put()
        self.redirect('/blog')
        return

app = webapp2.WSGIApplication([('/blog/?', BlogPostHandler),
                               ('/blog/newpost', NewPostHandler),
                               ('/blog/about', AboutHandler),
                               ('/blog/contact', ContactHandler),
                               ('/blog/login', LoginHandler),
                               ('/blog/logout', LogoutHandler),
                               ('/blog/admin', AdminHandler),
                               ('/blog/admin-pref', AdminPrefHandler),
                               ('/blog/pwchange', PasswordChangeHandler),
                               ('/blog/userchange', UsernameChangeHandler),
                               ('/blog/(\d+)', PermalinkHandler),
                               ('/blog/tags/(.*)', TagHandler)],
                                debug=True)
