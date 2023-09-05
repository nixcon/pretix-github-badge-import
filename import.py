#! /usr/bin/env python

from typing import Optional, Any, Generator, List

import argparse
import hashlib
import copy

import requests
import diskcache

import json


class PretixAPI:
    def __init__(self, http_client: requests.Session, org_id: str, event_id: str):
        self._http_client = http_client
        self._org_id = org_id
        self._event_id = event_id

    def orders(self) -> Generator[dict, None, None]:
        url = f"https://pretix.eu/api/v1/organizers/{self._org_id}/events/{self._event_id}/orders/"
        params = {'status': ['n','p']}

        response = self._http_client.get(url, params=params)
        response.raise_for_status()

        data = response.json()
        yield from data['results']
        while data['next']:
            response = self._http_client.get(data['next'])
            response.raise_for_status()
            data = response.json()
            yield from data['results']

            
    def patch_order(self, position_id: str, order: dict):
        #print(position_id, json.dumps(order, indent=2))


        if order['country'] is None:
            del order['country']

        if order.get('attendee_name_parts'):
            del order['attendee_name']
        
        response = self._http_client.patch(f'https://pretix.eu/api/v1/organizers/{self._org_id}/events/{self._event_id}/orderpositions/{position_id}/', json=order)
        response.raise_for_status()
        

        
    def upload_avatar(self, data: bytes, content_type='image/png', content_disposition='attachment; filename="avatar.png"') -> str:
        response = self._http_client.post('https://pretix.eu/api/v1/upload', data=data, headers={'content-type': content_type, 'content-disposition': content_disposition})
        response.raise_for_status()
        j = response.json()
        return j['id']
            
    def upload_answer_file(self, order_id, answer_id, data: bytes):
        pass


class Cache:
    def __init__(self, prefix: str, directory: str, serialize_fn = lambda x: x, deserialize_fn = lambda x: x) -> None:
        self._prefix = prefix
        self._cache = diskcache.Cache(directory)
        self._serialize_fn = serialize_fn
        self._deserialize_fn = deserialize_fn

    def _calculate_key(self, key: str) -> str:
        return f"{self._prefix}-${key}"
        
    def get(self, key: str) -> Any:
        key = self._calculate_key(key)
        data = self._cache.get(key)
        if data:
            return self._deserialize_fn(data)
        else:
            return None
        
    def set(self, key: str, content: Any) -> None:
        key = self._calculate_key(key)
        data = self._serialize_fn(content)
        self._cache.set(key, data)


class GHApi:
    http_client: requests.Session

    def __init__(self, http_client: requests.Session, cache: Optional[Cache] = None) -> None:
       self.http_client = http_client
       self.cache = cache

    def get_user_metadata(self, /, username: str) -> dict:
        url = f"https://api.github.com/users/{username}"
        response = self.http_client.get(url)
        response.raise_for_status()
        metadata = response.json()

        return metadata

    def get_avatar_url(self, /, username: str) -> str:
        metadata = self.get_user_metadata(username=username)
        avatar_url = metadata['avatar_url']
        return avatar_url

    def get_avatar(self, *, username: str) -> bytes:
        response = self.http_client.get(self.get_avatar_url(username=username), allow_redirects=True)
        response.raise_for_status()
        return response.content


def get_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument('--github-token-file', action='store', type=str, default='.github.token')
    p.add_argument('--pretix-token-file', action='store', type=str, default='.pretix.token')
    p.add_argument('--org', action='store', type=str, default='nixcon')
    p.add_argument('--year', action='store', type=str, default='2023')
    p.add_argument('github_user_question_id', action='store', type=int)
    p.add_argument('avatar_file_question', action='store', type=int)

    return p


def main():
    parser = get_parser()
    args = parser.parse_args()

    with open(args.pretix_token_file, 'r') as fh:
        pretix_token = fh.read().strip()

    gh_cache = Cache('github', 'cache')
    avatar_cache = Cache('avatar', 'cache')
    pretix_upload_id_cache = Cache('pretix_avatar_upload_id_cache', 'cache')

    pretix_session = requests.Session()
    pretix_session.headers['Authorization'] = f'Token {pretix_token} '
    del pretix_token

    gh_session = requests.Session()

    if args.github_token_file:
        with open(args.github_token_file, 'r') as fh:
            github_token = fh.read().strip()
        gh_session.headers['Authorization'] = f'Token {github_token}'
        del github_token

    gh_client = GHApi(gh_session)

    pretix_client = PretixAPI(pretix_session, args.org, args.year)

    for order in pretix_client.orders():
        for position in order['positions']:
            position_id = position['id']
            answers = position['answers']
            for question in answers:
                if question['question'] == args.github_user_question_id:
                    username = question['answer'].strip().lstrip('@')
                    avatar_url = gh_cache.get(username)
                    if avatar_url is None:
                        try:
                            avatar_url = gh_client.get_avatar_url(username=username)
                            gh_cache.set(username, avatar_url)
                        except Exception as e:
                            print('Failed to retrieve avatar for ', order['email'], question['answer'], e)
                        #else:
                        #    print(order['code'], order['email'], question['answer'], avatar_url)
                    #else:
                    #    print(order['code'], order['email'], question['answer'], avatar_url)

                    if not avatar_url:
                        print('no avatar url for ', username)

                    if avatar_url:
                        avatar_data = avatar_cache.get(avatar_url)
                        if not avatar_data:
                            avatar_response = gh_session.get(avatar_url, allow_redirects=True)
                            avatar_response.raise_for_status()

                            avatar_data = avatar_response.content
                            avatar_cache.set(avatar_url, avatar_data)

                        assert avatar_data
                        #print(len(avatar_data))

                        h = hashlib.sha256(avatar_data).hexdigest()


                        pretix_id = pretix_upload_id_cache.get(h)
                        if not pretix_id:
                            pretix_id = pretix_client.upload_avatar(avatar_data)
                        assert pretix_id

                        #print(answers)
                        new_answers = copy.deepcopy(answers)
                        found_question = False
                        for na in new_answers:
                            if na['question'] == args.avatar_file_question:
                                found_question = True
                                na['answer'] = pretix_id

                        if not found_question:
                            a = {'question': args.avatar_file_question, 'answer': pretix_id}
                            new_answers += [ a ]

                        #print(new_answers)
                        if username in ['andir'] or True:
                            pos = copy.deepcopy(position)
                            pos['answers'] = new_answers
                            pretix_client.patch_order(position_id, pos)

                        #print(pretix_id)


if __name__ == "__main__":
    main()
