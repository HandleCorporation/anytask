from django.conf.urls import patterns, url


urlpatterns = patterns('api.views',
                       url(r'^v1/api/course/(?P<course_id>\d+)/issues$', 'get_issues'),
                       url(r'^v1/api/issue/(?P<issue_id>\d+)$', 'get_issue'),
                       )
