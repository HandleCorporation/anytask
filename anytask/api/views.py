from __future__ import unicode_literals

import base64
import json

from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.contrib.auth import authenticate, login

from courses.models import Course
from issues.models import Issue


def login_required_basic_auth(view):
    def get_401_response():
        response = HttpResponse()
        response.status_code = 401
        response['WWW-Authenticate'] = 'Basic realm="AnyTask API"'
        return response

    def check_auth(request, *args, **kwargs):
        if 'HTTP_AUTHORIZATION' not in request.META:
            return get_401_response()

        auth_str = request.META['HTTP_AUTHORIZATION']
        auth_str_parts = auth_str.split()

        if auth_str_parts[0].lower() != "basic":
            return get_401_response()

        username, password = base64.b64decode(auth_str_parts[1]).split(":", 1)
        user = authenticate(username=username, password=password)
        if user is None or not user.is_active:
            return get_401_response()

        login(request, user)
        request.user = user
        return view(request, *args, **kwargs)
    return check_auth


def unpack_user(user):
    profile = user.get_profile()
    return {
        "id": user.id,
        "name": user.get_full_name(),
        "first_name": user.first_name,
        "last_name": user.last_name,
        "username": user.username,
        "middle_name": profile.middle_name,
    }


def unpack_task(task):
    return {
        "id": task.id,
        "title": task.title,
    }


def unpack_issue(issue):
    task = issue.task
    ret = {
        "id": issue.id,
        "mark": issue.mark,
        "create_time": issue.create_time.isoformat() + "Z",
        "update_time": issue.update_time.isoformat() + "Z",
        "responsible": None,
        "followers": map(lambda x: unpack_user(x), issue.followers.all()),
        "status": issue.status_field.get_name(lang='en'),
        "student": unpack_user(issue.student),
        "task": unpack_task(task)
    }

    if issue.responsible:
        ret["responsible"] = unpack_user(issue.responsible.username)

    return ret


def unpack_file(request, f):
    return {
        "id": f.id,
        "filename": f.filename(),
        "path": f.file.url,
        "url": request.build_absolute_uri(f.file.url),
    }


def unpack_event(request, event):
    ret = {
        "id": event.id,
        "timestamp": event.timestamp.isoformat() + "Z",
        "author": unpack_user(event.author),
        "message": event.get_message(),
        # "files": list(event.file_set.all())
        "files": map(lambda x: unpack_file(request, x), event.file_set.filter(deleted=False)),
    }

    return ret


@login_required_basic_auth
def get_issues(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    user = request.user

    if not course.user_is_teacher(user):
        return HttpResponseForbidden()

    issues = []
    for task in course.task_set.all():
        for issue in task.issue_set.all():
            issues.append(unpack_issue(issue))

    return HttpResponse(json.dumps(issues),
                        content_type="application/json")


@login_required_basic_auth
def get_issue(request, issue_id):
    user = request.user
    issue = get_object_or_404(Issue, id=issue_id)
    access_ok = False

    if user in (issue.student,
                issue.responsible):
        access_ok = True

    if not access_ok and issue.followers.filter(id=user.id).count() != 0:
        access_ok = True

    if not access_ok:
        course = issue.task.course
        if course.user_is_teacher(user):
            access_ok = True

    if not access_ok:
        return HttpResponseForbidden()

    ret = unpack_issue(issue)
    ret["events"] = map(lambda x: unpack_event(request, x), issue.get_history())

    return HttpResponse(json.dumps(ret),
                        content_type="application/json")
