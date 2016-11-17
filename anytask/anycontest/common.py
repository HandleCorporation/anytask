# -*- coding: utf-8 -*-
import requests
import logging
import os
import xmltodict
from BeautifulSoup import BeautifulStoneSoup

from time import sleep
from django.conf import settings
from issues.model_issue_field import IssueField
from django.contrib.auth.models import User

logger = logging.getLogger('django.request')


class FakeResponse(object):
    def __init__(self):
        self.url = None

    @staticmethod
    def json():
        return None


def get_compiler_id(course, extension):
    compiler_id = settings.CONTEST_EXTENSIONS[extension]
    if course.id not in settings.CONTEST_EXTENSIONS_COURSE:
        return compiler_id

    if extension not in settings.CONTEST_EXTENSIONS_COURSE[course.id]:
        return compiler_id

    return settings.CONTEST_EXTENSIONS_COURSE[course.id][extension]


def get_problem_compilers(problem_id, contest_id):
    contest_req = FakeResponse()
    problem_compilers = []

    try:
        contest_req = requests.get(settings.CONTEST_API_URL + 'contest?contestId=' + str(contest_id),
                                   headers={'Authorization': 'OAuth ' + settings.CONTEST_OAUTH})
        for problem in contest_req.json()['result']['problems']:
            if problem['alias'] == problem_id:
                problem_compilers = problem['compilers']
    except Exception as e:
        logger.exception("Exception while request to Contest: '%s' : '%s', Exception: '%s'",
                         contest_req.url, contest_req.json(), e)

    return problem_compilers


def upload_contest(event, extension, file, compiler_id=None):
    problem_req = FakeResponse()
    submit_req = FakeResponse()
    reg_req = FakeResponse()
    message = "OK"

    try:
        issue = event.issue
        student_profile = issue.student.get_profile()
        contest_id = issue.task.contest_id
        course = event.issue.task.course
        if not compiler_id:
            compiler_id = get_compiler_id(course, extension)

        if student_profile.ya_contest_oauth and course.send_to_contest_from_users:
            OAUTH = student_profile.ya_contest_oauth
            reg_req = requests.get(
                settings.CONTEST_API_URL + 'status?contestId=' + str(contest_id),
                headers={'Authorization': 'OAuth ' + OAUTH})
            if 'error' in reg_req.json():
                return False, reg_req.json()["error"]["message"]

            if not reg_req.json()['result']['isRegistered']:
                reg_req = requests.get(
                    settings.CONTEST_API_URL + 'register-user?uidToRegister=' + str(student_profile.ya_contest_uid) +
                    '&contestId=' + str(contest_id),
                    headers={'Authorization': 'OAuth ' + settings.CONTEST_OAUTH})
            if 'error' in reg_req.json():
                return False, reg_req.json()["error"]["message"]
        else:
            OAUTH = settings.CONTEST_OAUTH

        problem_req = requests.get(settings.CONTEST_API_URL + 'problems?contestId=' + str(contest_id),
                                   headers={'Authorization': 'OAuth ' + settings.CONTEST_OAUTH})
        problem_id = None
        for problem in problem_req.json()['result']['problems']:
            if problem['title'] == issue.task.problem_id:
                problem_id = problem['id']
                break

        if problem_id is None:
            logger.error("Cant find problem_id '%s' for issue '%s'", issue.task.problem_id, issue.id)
            return False, "Cant find problem '{0}' in Yandex.Contest".format(issue.task.problem_id)

        for i in range(3):
            with open(os.path.join(settings.MEDIA_ROOT, file.file.name), 'rb') as f:
                files = {'file': f}
                submit_req = requests.post(settings.CONTEST_API_URL + 'submit',
                                           data={'compilerId': compiler_id,
                                                 'contestId': contest_id,
                                                 'problemId': problem_id},
                                           files=files,
                                           headers={'Authorization': 'OAuth ' + OAUTH})
                if not 'error' in submit_req.json():
                    break
                sleep(0.5)

        if 'error' in submit_req.json():
            return False, submit_req.json()["error"]["message"]

        run_id = submit_req.json()['result']['value']
        sent = True
        logger.info("Contest submission with run_id '%s' sent successfully.", run_id)
        issue.set_byname(name='run_id', value=run_id)
    except Exception as e:
        logger.exception("Exception while request to Contest: '%s' : '%s', '%s' : '%s', Exception: '%s'",
                         problem_req.url, problem_req.json(), submit_req.url, submit_req.json(), e)
        sent = False
        message = "Unexpected error"

    return sent, message


def escape(text):
    symbols = ["&", "'", '"', "<", ">"]
    symbols_escaped = ["&amp;", "&#39;", "&quot;", "&lt;", "&gt;"]

    for i, j in zip(symbols, symbols_escaped):
        text = text.replace(i, j)

    return text


def check_submission(issue):
    results_req = FakeResponse()
    verdict = False
    comment = ''

    try:
        run_id = issue.get_byname('run_id')
        student_profile = issue.student.get_profile()
        course = issue.task.course
        if student_profile.ya_contest_oauth and course.send_to_contest_from_users:
            OAUTH = student_profile.ya_contest_oauth
        else:
            OAUTH = settings.CONTEST_OAUTH
        contest_id = issue.task.contest_id
        results_req = requests.get(
            settings.CONTEST_API_URL + 'results?runId=' + str(run_id) + '&contestId=' + str(contest_id),
            headers={'Authorization': 'OAuth ' + OAUTH})

        contest_verdict = results_req.json()['result']['submission']['verdict']
        if contest_verdict == 'ok':
            comment = u'<p>Вердикт Я.Контест: ok</p>'
            verdict = True
        elif contest_verdict == 'precompile-check-failed':
            contest_messages = []
            for precompile_check in results_req.json()['result']['precompileChecks']:
                contest_messages.append(precompile_check['message'])
            comment = u'<p>Вердикт Я.Контест: precompile-check-failed</p><pre>' + \
                      escape(u'\n'.join(contest_messages)) + \
                      u'</pre>'
        else:
            comment = u'<p>Вердикт Я.Контест: ' \
                      + results_req.json()['result']['submission']['verdict'] + '</p><pre>' \
                      + escape(results_req.json()['result']['compileLog'][18:]) + '</pre>'
            if results_req.json()['result']['tests']:
                test = results_req.json()['result']['tests'][-1]
                test_resourses = u'<p><u>Ресурсы</u> ' + str(test['usedTime']) \
                                 + 'ms/' + '%.2f' % (test['usedMemory']/(1024.*1024)) + 'Mb</p>'
                if 'input' in test:
                    test_input = u'<p><u>Ввод</u></p><p>' + \
                                 escape(test['input']) if test['input'] else ""
                    test_input += '</p>'
                else:
                    test_input = ""
                if 'output' in test:
                    test_output = u'<p><u>Вывод программы</u></p><p>' + \
                                  escape(test['output']) if test['output'] else ""
                    test_output += '</p>'
                else:
                    test_output = ""
                if 'answer' in test:
                    test_answer = u'<p><u>Правильный ответ</u></p><p>' + \
                                  escape(test['answer']) if test['answer'] else ""
                    test_answer += '</p>'
                else:
                    test_answer = ""
                if 'error' in test:
                    test_error = u'<p><u>Stderr</u></p><p>' + \
                                 escape(test['error']) if test['error'] else ""
                    test_error += '</p>'
                else:
                    test_error = ""
                if 'message' in test:
                    test_message = u'<p><u>Сообщение чекера</u></p><p>' + \
                                   escape(test['message']) if test['message'] else ""
                    test_message += '</p>'
                else:
                    test_message = ""
                comment += u'<p><u>Тест ' + str(test['testNumber']) + '</u>' \
                           + test_resourses + test_input + test_output \
                           + test_answer + test_error + test_message + '</p>'

        logger.info("Contest submission verdict with run_id '%s' got successfully.", run_id)
        got_verdict = True
    except Exception as e:
        logger.exception("Exception while request to Contest: '%s' : '%s', Exception: '%s'",
                         results_req.url, results_req.json(), e)
        got_verdict = False

    return got_verdict, verdict, comment


def comment_verdict(issue, verdict, comment):
    author = User.objects.get(username="anytask")
    field, field_get = IssueField.objects.get_or_create(name='comment')
    event = issue.create_event(field, author=author)
    event.value = u'<div class="contest-response-comment not-sanitize">' + comment + u'</div>'
    event.save()
    if issue.status_field.tag != issue.status_field.STATUS_ACCEPTED:
        if verdict:
            issue.set_status_by_tag(issue.status_field.STATUS_VERIFICATION)
        else:
            issue.set_status_by_tag(issue.status_field.STATUS_REWORK)
    issue.save()


def get_contest_mark(contest_id, problem_id, ya_login):
    results_req = FakeResponse()
    contest_mark = None
    user_id = None
    try:
        results_req = requests.get(
            'https://contest.yandex.ru/action/api/download-log?contestId=' + str(contest_id) + '&snarkKey=spike')
        try:
            contest_dict = xmltodict.parse(results_req.content)

            users = contest_dict['contestLog']['users']['user']

            for user in users:
                if user['@loginName'] == ya_login:
                    user_id = user['@id']
                    break

            submits = contest_dict['contestLog']['events']['submit']
            submits.reverse()

            for submit in submits:
                if submit['@userId'] == user_id and submit['@problemTitle'] == problem_id and submit['@verdict'] == 'OK':
                    contest_mark = submit['@score']
                    break
        except:
            soup = BeautifulStoneSoup(results_req.content)
            users = soup.contestlog.users.user

            while users:
                if users != '\n':
                    if users['loginname'] == ya_login:
                        user_id = users['id']
                        break
                users = users.next

            submits = soup.contestlog.events.submit

            while submits:
                if submits != '\n' and submits.name != 'testinglog' and submits.has_key('userid'):
                    if submits['userid'] == user_id and submits['problemtitle'] == problem_id and submits['verdict'] == 'OK':
                        contest_mark = submits['score']
                        break
                submits = submits.next

    except Exception as e:
        logger.exception("Exception while request to Contest: '%s' : '%s', Exception: '%s'",
                         results_req.url, e)
    return contest_mark


def get_contest_info(contest_id):
    contest_req = FakeResponse()

    try:
        contest_req = requests.get(settings.CONTEST_API_URL + 'contest?contestId=' + str(contest_id),
                                   headers={'Authorization': 'OAuth ' + settings.CONTEST_OAUTH})

        if 'error' in contest_req.json():
            return False, contest_req.json()["error"]["message"]

        contest_info = contest_req.json()['result']
        got_info = True
    except Exception as e:
        logger.exception("Exception while request to Contest: '%s' : '%s', Exception: '%s'",
                         contest_req.url, contest_req.json(), e)
        contest_info = {}
        got_info = False

    return got_info, contest_info
