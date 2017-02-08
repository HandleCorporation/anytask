from django.conf.urls import patterns, url

urlpatterns = patterns('staff.views',
    url(r'^$', 'staff_page'),
    url(r'/gradebook/$', 'get_gradebook'),
    url(r'/gradebook/(?P<statuses>\w+)$', 'gradebook_page')
)
