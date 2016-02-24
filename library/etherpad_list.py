#!/usr/bin/env python
# -*- coding: utf-8 -*-

# (c) 2014, Sunil Thaha <sthaha@redhat.com>
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

DOCUMENTATION = '''
---
author: Sunil Thaha
module: etherpad_list
short_description: manages a list of topics in yaml format in etherpad
description:
  - ""
version_added: "1.7"
options:
  url:
    description:
    - The url for the etherpad lite
    required: true
  key:
    description:
    - The apikey provided by etherpad lite
    required: true
  pad:
    description:
    - The etherpad or the pad id
    required: true
  topic:
    description:
    - The top level yaml topic of the list. RESERVED - all, done
    required: true
  contents:
    description:
    - The new list to be merged with the existing list on the pad
    required: true
examples:
  - description: Update horizon dependencies
    code: etherpad_list
            url: "{{ url }}"
            key: '{{api_key}}'
            pad: 'test'
            topic: 'nova'
            contents: "{{ nova }}"
'''
# ### CREDITS ###
# Etherpad client **heavily** based on the popular pip package
# etherpadlite-client: https://github.com/Changaco/python-etherpad_lite
# Modified rather than reused to keep the ResponseError and ApiError(code)
# separate and to respond to these exceptions differently in the Ansible
# module
# ###

from ansible.module_utils.basic import AnsibleModule
from functools import partial
import json
import re
import yaml
try:
    from urllib.request import urlopen
    from urllib.parse import urlencode
except ImportError:
    from urllib2 import urlopen
    from urllib import urlencode


class EtherpadResponseError(Exception):
    pass


class EtherpadApiError(Exception):
    def __init__(self, code, *args):
        super(EtherpadApiError, self).__init__(*args)
        self.code = code


class EtherpadClient(object):
    def __init__(self, url, apikey, version='1', timeout=20, **kwargs):
        self.url = url
        self.version = version
        self.timeout = timeout
        self.default_params = dict(**kwargs)
        self.default_params['apikey'] = apikey

    def __call__(self, api, **params):
        url = '%(url)s/%(version)s/%(api)s' % {
            "url": self.url, "version": self.version, "api": api
        }
        data = urlencode(dict(self.default_params, **params)).encode('ascii')
        response = urlopen(url, data, self.timeout).read().decode('utf-8')

        res = json.loads(response)
        if not res or not isinstance(res, dict):
            raise EtherpadResponseError('API returned: %s' % res)

        code = res.get('code')
        if code != 0:
            raise EtherpadApiError(code, res.get('message', res))

        return res.get('data')

    def __getattr__(self, name):
        return partial(self, name)


# ### module ###

class EtherpadListModule(object):
    module = None

    def __init__(self, module):
        self.module = module
        # add api at the end if it isn't specified
        apikey = module.params['key']
        self.epad = EtherpadClient(self._api_url(), apikey)
        self.pad_id = module.params['pad']

    def run(self):
        # updates the existing list or creates a new list
        # add the new items in 'contents' to the existing list for the topic
        # if a package seems to be removed in the new contents and
        # and is in 'done' topic, it gets removed in the new list

        self._ensure_pad_exists()
        doc = self._parse_pad()

        topic = self.module.params['topic']
        new_contents = set(self.module.params['contents'])
        done = doc['done']

        existing_list = set(doc.get(topic, []))
        updated_list = existing_list.difference(done).union(new_contents)
        contents_changed = existing_list != updated_list

        if contents_changed:
            doc[topic] = sorted(updated_list)
            doc['all'] = sorted(self._all_items(doc, ['all', 'done']))
            updated_yaml = yaml.safe_dump(doc, default_flow_style=False)
            self.epad.setText(padID=self.pad_id, text=updated_yaml)

        result = {'changed': contents_changed}
        self.module.exit_json(**result)

    def _parse_pad(self):
        text = self.epad.getText(padID=self.pad_id)['text']
        doc = yaml.safe_load(text) or {'done': []}    # dict if text is empty
        if 'done' not in doc:
            doc['done'] = []
        return doc

    def _all_items(self, doc, ignore=None):
        ignore = ignore or set()

        all_items = []
        for k, v in doc.items():
            if k not in ignore:
                all_items += v
        return set(all_items)

    def _api_url(self):
        url = self.module.params['url']
        if not re.search('/api/?$', url):
            url += '/api'
        return url

    def _ensure_pad_exists(self):
        try:
            self.epad.createPad(padID=self.pad_id)
            self.epad.setText(padID=self.pad_id, text='')
        except EtherpadApiError as e:
            if e.code == 1 and 'already exist' in e.message:
                return
            self.module.fail_json(msg=e.message, code=e.code)
        except Exception as e:
            self.module.fail_json(msg=e.message)


def main():
    module = AnsibleModule(argument_spec=dict(
        url=dict(type='str', required=True),
        key=dict(type='str', required=True),
        pad=dict(type='str', required=True),
        topic=dict(type='str', required=True),
        contents=dict(type='list', required=True)
    ))
    EtherpadListModule(module).run()

# this is magic, see lib/ansible/module_common.py
#<<INCLUDE_ANSIBLE_MODULE_COMMON>>
if __name__ == '__main__':
    main()
