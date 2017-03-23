# -*- coding: utf-8 -*-

from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.utils.translation import ugettext_lazy as _
from django import forms

from datetime import datetime

from years.common import get_current_year
from groups.models import Group
from courses.models import Course
from mail.models import Message

from colorfield.fields import ColorField

from anytask.storage import OverwriteStorage

import os
import django_filters
import copy


def get_upload_path(instance, filename):
    return os.path.join('images', 'user_%d' % instance.user.id, filename)


class UserStatus(models.Model):
    COLOR_DEFAULT = '#818A91'

    STATUS_ACTIVE = 'active'
    STATUS_EXTRAMURAL = 'extramural'
    STATUS_FULLTIME = 'fulltime'
    STATUS_NOT_ACTIVE = 'not_active'
    STATUS_ACADEMIC = 'academic'

    USER_STATUSES = (
        (STATUS_ACTIVE, _(STATUS_ACTIVE)),
        (STATUS_EXTRAMURAL, _(STATUS_EXTRAMURAL)),
        (STATUS_FULLTIME, _(STATUS_FULLTIME)),
        (STATUS_NOT_ACTIVE, _(STATUS_NOT_ACTIVE)),
        (STATUS_ACADEMIC, _(STATUS_ACADEMIC))
    )

    TYPE_ACTIVITY = 'activity'
    TYPE_FILIAL = 'filial'
    TYPE_ADMISSION = 'admission'
    TYPE_EDUCATION_FORM = 'education_form'

    TYPE_STATUSES = (
        (TYPE_ACTIVITY, _(u'status_studenta')),
        (TYPE_FILIAL, _(u'filial')),
        (TYPE_ADMISSION, _(u'status_postupleniya')),
        # (TYPE_EDUCATION_FORM, _(u'Форма обучения')),
    )

    name = models.CharField(max_length=254, db_index=True, null=False, blank=False)
    type = models.CharField(max_length=191, db_index=False, null=True, blank=True, choices=TYPE_STATUSES)
    tag = models.CharField(max_length=254, db_index=False, null=True, blank=True, choices=USER_STATUSES)
    color = ColorField(default=COLOR_DEFAULT)

    def __unicode__(self):
        return u'{0}'.format(self.name)


class UserProfile(models.Model):
    user = models.ForeignKey(User, db_index=True, null=False, blank=False, unique=True, related_name='profile')
    middle_name = models.CharField(max_length=128, db_index=True, null=True, blank=True)
    user_status = models.ManyToManyField(UserStatus, db_index=True, null=True, blank=True, related_name='users_by_status')

    avatar = models.ImageField('profile picture', upload_to=get_upload_path, blank=True, null=True, storage=OverwriteStorage())
    birth_date = models.DateField(blank=True, null=True)

    info = models.TextField(default="", blank=True, null=True)

    phone = models.CharField(max_length=128, null=True, blank=True)
    city_of_residence = models.CharField(max_length=191, null=True, blank=True)

    university = models.CharField(max_length=191, null=True, blank=True)
    university_in_process = models.BooleanField(null=False, blank=False, default=False)
    university_class = models.CharField(max_length=50, null=True, blank=True)
    university_department = models.CharField(max_length=191, null=True, blank=True)
    university_year_end = models.CharField(max_length=20, null=True, blank=True)

    additional_info = models.TextField(null=True, blank=True)

    unit = models.CharField(default="", max_length=128, unique=False, null=True, blank=True)
    position = models.CharField(default="", max_length=128, unique=False, null=True, blank=True)
    academic_degree = models.CharField(default="", max_length=128, unique=False, null=True, blank=True)
    academic_title = models.CharField(default="", max_length=128, unique=False, null=True, blank=True)

    show_email = models.BooleanField(db_index=False, null=False, blank=False, default=True)
    send_my_own_events = models.BooleanField(db_index=False, null=False, blank=False, default=False)

    unread_messages = models.ManyToManyField(Message, null=True, blank=True, related_name='unread_messages')
    deleted_messages = models.ManyToManyField(Message, null=True, blank=True, related_name='deleted_messages')
    send_notify_messages = models.ManyToManyField(Message, null=True, blank=True, related_name='send_notify_messages')

    added_time = models.DateTimeField(auto_now_add=True, default=datetime.now)
    update_time = models.DateTimeField(auto_now=True, default=datetime.now)

    updated_by = models.ForeignKey(User, db_index=False, null=True, blank=True)

    login_via_yandex = models.BooleanField(db_index=False, null=False, blank=False, default=True)

    ya_uid = models.IntegerField(null=True, blank=True)
    ya_login = models.CharField(default="", max_length=128, unique=False, null=True, blank=True)

    ya_contest_uid = models.IntegerField(null=True, blank=True)
    ya_contest_oauth = models.CharField(default="", max_length=128, unique=False, null=True, blank=True)
    ya_contest_login = models.CharField(default="", max_length=128, unique=False, null=True, blank=True)

    ya_passport_uid = models.IntegerField(null=True, blank=True)
    ya_passport_oauth = models.CharField(default="", max_length=128, unique=False, null=True, blank=True)
    ya_passport_login = models.CharField(default="", max_length=128, unique=False, null=True, blank=True)
    ya_passport_email = models.CharField(default="", max_length=128, unique=False, null=True, blank=True)

    language = models.CharField(default="ru", max_length=128, unique=False, null=True, blank=True)

    def is_current_year_student(self):
        return Group.objects.filter(year=get_current_year()).filter(students=self.user).count() > 0

    def __unicode__(self):
        return unicode(self.user)

    def is_active(self):
        for status in self.user_status.all():
            if status.tag == 'not_active' or status.tag == 'academic':
                return False
        return True

    def set_status(self, new_status):
        if not isinstance(new_status, UserStatus):
            new_status = UserStatus.objects.get(id=new_status)

        for status in self.user_status.all():
            if status.type == new_status.type:
                self.user_status.remove(status)
        self.user_status.add(new_status)

    def get_unread_count(self):
        return self.unread_messages.exclude(id__in=self.deleted_messages.all()).count()

    def can_sync_contest(self):
        for course in Course.objects.filter(is_active=True):
            if course.get_user_group(self.user) and course.send_to_contest_from_users:
                return True
        return False


class UserProfileLog(models.Model):
    user = models.ForeignKey(User, db_index=True, null=False, blank=False, related_name='profiles_logs_by_user')
    second_name = models.CharField(max_length=128, db_index=True, null=True, blank=True)
    user_status = models.ManyToManyField(UserStatus, db_index=True, null=True, blank=True)

    avatar = models.ImageField('profile picture', upload_to=get_upload_path, blank=True, null=True,
                               storage=OverwriteStorage())
    birth_date = models.DateField(blank=True, null=True)

    info = models.TextField(default="", blank=True, null=True)

    unit = models.CharField(default="", max_length=128, unique=False, null=True, blank=True)
    position = models.CharField(default="", max_length=128, unique=False, null=True, blank=True)
    academic_degree = models.CharField(default="", max_length=128, unique=False, null=True, blank=True)
    academic_title = models.CharField(default="", max_length=128, unique=False, null=True, blank=True)

    show_email = models.BooleanField(db_index=False, null=False, blank=False, default=True)
    send_my_own_events = models.BooleanField(db_index=False, null=False, blank=False, default=False)

    added_time = models.DateTimeField(auto_now_add=True, default=datetime.now)
    update_time = models.DateTimeField(auto_now=True, default=datetime.now)

    ya_uid = models.IntegerField(null=True, blank=True)
    ya_login = models.CharField(default="", max_length=128, unique=False, null=True, blank=True)
    ya_contest_oauth = models.CharField(default="", max_length=128, unique=False, null=True, blank=True)
    ya_passport_oauth = models.CharField(default="", max_length=128, unique=False, null=True, blank=True)

    updated_by = models.ForeignKey(User, db_index=False, null=True, blank=True)

    def is_current_year_student(self):
        return Group.objects.filter(year=get_current_year()).filter(students=self.user).count() > 0

    def __unicode__(self):
        return unicode(self.user)


class UserProfileFilter(django_filters.FilterSet):
    # user_status_education_form = django_filters.ChoiceFilter(label=_(u'<strong>Форма обучения</strong>'), name='user_status')
    user_status = django_filters.ChoiceFilter(label=_('status_studenta'), name='user_status')

    def set(self):
        self.filters['user_status'].field.label = u'<strong>{0}</strong>'.format(
            self.filters['user_status'].field.label)
        activity_choices = [(status.id, status.name) for status in UserStatus.objects.filter(type='activity')]
        activity_choices.insert(0, (u'', _(u'luboj')))
        self.filters['user_status'].field.choices = tuple(activity_choices)

        # education_form_choices = [(status.id, _(status.name)) for status in UserStatus.objects.filter(type='education_form')]
        # education_form_choices.insert(0, (u'', _(u'luboj')))
        # self.filters['user_status_education_form'].field.choices = tuple(education_form_choices)

    class Meta:
        model = UserProfile
        fields = ['user_status']


def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)


def user_profile_log_save_to_log_post_save(sender, instance, created, **kwargs):
    user_profile_log = UserProfileLog()
    user_profile_log_dict  = copy.deepcopy(instance.__dict__)
    user_profile_log_dict['id'] = None
    user_profile_log.__dict__ = user_profile_log_dict
    user_profile_log.save()
    user_profile_log.user_status.add(*instance.user_status.all())

post_save.connect(create_user_profile, sender=User)
post_save.connect(user_profile_log_save_to_log_post_save, sender=UserProfile)
