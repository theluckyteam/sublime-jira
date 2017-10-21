# coding=utf-8
import sublime, sublime_plugin
import re
import types
import json
import urllib
from urllib.error import URLError


def parse_issue_stream(stream):
    # Разбить выражение на строки и понять каким образом его обрабатывать
    lines = []
    parts = stream.split("\n")
    for part in parts:
        if part.strip() != '':
            lines.append(part)

    # Смысл имеет только выражение, содержащее минимум одну строку
    if len(lines) < 1:
        return None

    # Подготовить описание для задачи из выражения
    description = "\n".join(lines[1:]) if len(lines) > 1 else ''

    # Далее имеет смысл только первая строка выражения
    stream = lines[0]

    # Подготовим оцениваемое время на работу с задачей
    temp_result = re.search(r'\~(.+)', stream)
    estimate = temp_result.group(1).strip() if temp_result is not None else ''
    stream = re.sub(r'\~(.+)', '', stream).strip()

    # Подготовим метки
    labels = re.findall(r'\#(\S+)', stream)
    stream = re.sub(r'\#(\S+)', '', stream).strip()

    # Подготовим название
    summary = stream

    # Подготовить структуру данных для заведения задачи
    issue = {
        "summary": summary,
        "description": description,
        "estimate": estimate,
        "labels": labels
    }

    return issue


class TokenGettingError(Exception):
    """ Ошибка получения токена """
    pass


class TokenFailedError(Exception):
    """ Неверный токен авторизации """
    pass


class IssueCreatingError(Exception):
    """ Ошибка создания задачи """
    pass


class CreateJiraIssueCommand(sublime_plugin.TextCommand):
    def settings(self):
        return self.view.settings()

    def run(self, edit, project, issuetype):

        settings = self.settings()

        issue_project = project
        issue_type = issuetype
        issue_creation_url = settings.get('jira_issue_creation_url')
        issue_assignee = settings.get('jira_issue_assignee')
        issue_component = settings.get('jira_issue_component')

        try:
            # Переберем все выделенные области в текущем view
            for region in self.view.sel():
                issue_expression = self.view.substr(region)
                issue_attributes = parse_issue_stream(issue_expression)
                issue_definition = {
                    "fields": {
                        "summary": issue_attributes['summary'],
                        "description": issue_attributes['description'],
                        "issuetype": {
                            "id": issue_type
                        },
                        "project": {
                            "id": issue_project,
                        },
                        "labels": issue_attributes['labels'],
                        "timetracking": {
                            "remainingEstimate": issue_attributes['estimate']
                        },
                        "assignee": {
                            "name": issue_assignee,
                        },
                        "components": [
                            {
                                "id": issue_component
                            }
                        ]
                    }
                }

                issue = self.create_issue(issue_creation_url, issue_definition)

                issue_result = issue['key'] + ' - ' + issue_expression
                self.view.replace(edit, region, issue_result)

        except:
            sublime.message_dialog('При создании задачи произошла ошибка. Проверьте аргументы и попробуйте снова.')

    def clear_access_token(self):
        settings = self.settings()
        settings.erase('jira_access_token')

    def access_token(self):
        settings = self.settings()

        if settings.has('jira_access_token'):
            access_token = settings.get('jira_access_token')
        else:
            url = settings.get('jira_auth_url')
            username = settings.get('jira_auth_username')
            password = settings.get('jira_auth_password')
            data = {
                "username": username,
                "password": password,
            }

            access_token = self.request_access_token(url, data)
            settings.set('jira_access_token', access_token)

        return access_token

    def request_access_token(self, url, data):

        json_data = json.dumps(data, ensure_ascii=False)
        json_bytes = json_data.encode('utf-8')
        json_bytes_length = len(json_bytes)

        request = urllib.request.Request(url)
        request.add_header('Content-Type', 'application/json; charset=utf-8')
        request.add_header('Content-Length', json_bytes_length)

        sublime.status_message('Request to "%s"' % url)
        try:
            response = urllib.request.urlopen(request, json_bytes)
            response_data = response.read().decode('utf-8')
            result = json.loads(response_data)
            cookie_auth = result['session']

        except:
            raise TokenGettingError('Could not get access token.')

        return cookie_auth

    def create_issue(self, url, definition):
        attempt = 3
        while attempt > 0:
            try:
                access_token = self.access_token()
                attempt -= 1
                return self.request_create_issue(url, definition, access_token)

            except TokenFailedError:
                self.clear_access_token()

    def request_create_issue(self, url, definition, token):

        json_data = json.dumps(definition, ensure_ascii=False)
        json_bytes = json_data.encode('utf-8')
        json_bytes_length = len(json_bytes)

        request = urllib.request.Request(url)
        request.add_header('Cookie', '='.join([token['name'], token['value']]))
        request.add_header('Content-Type', 'application/json; charset=utf-8')
        request.add_header('Content-Length', json_bytes_length)

        sublime.status_message('Request to "%s"' % url)
        try:
            response = urllib.request.urlopen(request, json_bytes)
            response_data = response.read().decode('utf-8')

            return json.loads(response_data)

        except URLError as error:
            if error.code == 401:
                raise TokenFailedError('Token is failed.')
            else:
                raise IssueCreatingError('Could not create issue.')

        except:
            raise IssueCreatingError('Could not create issue.')
