# Python 2 backwards compatiblity
import sys
if sys.version_info[0] < 3:
    u = lambda x: x.decode()
    b = lambda x: x
    unichr = unichr
    basestring = basestring
    unicode = unicode
    bytes = str
    nativestr = lambda x: \
        x if isinstance(x, str) else x.encode('utf-8', 'replace')
else:
    u = lambda x: x
    unichr = chr
    unicode = str
    bytes = bytes
    b = lambda x: x.encode('latin-1') if not isinstance(x, bytes) else x
    nativestr = lambda x: \
        x if isinstance(x, str) else x.decode('utf-8', 'replace')


from uuid import uuid1

import mock
import pytest

from saferedisqueue import SafeRedisQueue


def test_put_returns_uid_string():
    queue = SafeRedisQueue(
        name='saferedisqueue-test-%s' % uuid1().hex,
        autoclean_interval=1)
    # TODO: mock uuid.uuid4 here
    uid = queue.put('blub')
    assert len(uid) == 36
    assert type(uid) is str


def test_put_internally_converts_uuid_to_str():
    queue = SafeRedisQueue(
        name='saferedisqueue-test-%s' % uuid1().hex,
        autoclean_interval=1)

    # mock it
    queue._redis = mock.Mock()
    queue._redis.pipeline.return_value = pipeline_mock = mock.Mock()
    pipeline_mock.hset.return_value = hset_mock = mock.Mock()

    uid = queue.put('blub')
    pipeline_mock.hset.assert_called_with(queue.ITEMS_KEY, uid, 'blub')
    hset_mock.lpush.assert_called_with(queue.QUEUE_KEY, uid)


def test_decode_responses_true():
    queue = SafeRedisQueue(
        name='saferedisqueue-test-%s' % uuid1().hex,
        decode_responses=True)
    unicode_string = unichr(3456) + u('abcd') + unichr(3421)
    queue.put(unicode_string)
    return_val = queue.get()[1]
    assert isinstance(return_val, unicode)
    assert unicode_string == return_val


def test_decode_responses_false():
    queue = SafeRedisQueue(name='saferedisqueue-test-%s' % uuid1().hex)
    unicode_string = unichr(3456) + u('abcd') + unichr(3421)
    queue.put(unicode_string)
    return_val = queue.get()[1]
    assert isinstance(return_val, bytes)
    assert nativestr(unicode_string) == nativestr(return_val)


# Serializer tests
# Try with json and pickle serializer

try:
    import simplejson as json
except ImportError:
    import json as json

import pickle as PickleSerializer


class MyJSONSerializer(object):
    @staticmethod
    def loads(bytes):
        return json.loads(bytes.decode('utf-8'))

    @staticmethod
    def dumps(data):
        return json.dumps(data)


@pytest.mark.parametrize("serializer", [
    MyJSONSerializer,
    PickleSerializer,
])
def test_serializer(serializer):

    queue = SafeRedisQueue(
        name='saferedisqueue-test-%s' % uuid1().hex,
        autoclean_interval=None,
        serializer=serializer
    )

    item = {'test': 'good', 'values': ['a', 'b', 'c']}

    # Test when there is an element
    queue.push(item)
    uid_item, payload_item = queue.pop()
    assert type(item) == type(payload_item)
    assert item == payload_item

    # Test when there is no element and it times out
    uid_item, payload_item = queue.pop(timeout=1)
    assert None == uid_item
    assert None == payload_item


def test_serializer_calls():
    serializer_mock = mock.Mock()
    serializer_mock.dumps.return_value = '{"dumps": "return"}'
    serializer_mock.loads.return_value = {"loads": "return"}

    queue = SafeRedisQueue(
        name='saferedisqueue-test-%s' % uuid1().hex,
        autoclean_interval=None,
        serializer=serializer_mock
    )

    item = {'test': 'good', 'values': ['a', 'b', 'c']}
    queue.push(item)
    serializer_mock.dumps.assert_called_with(item)

    assert queue.pop()[1] == {"loads": "return"}
    serializer_mock.loads.assert_called_with(b('{"dumps": "return"}'))


def test_autoclean_while_waiting():
    """If items is not acked/failed, it will appear again in the queue."""
    queue = SafeRedisQueue(
        name='saferedisqueue-test-%s' % uuid1().hex,
        autoclean_interval=0.1,
    )

    item = "example payload"
    queue.push(item)
    uid1, item1 = queue.pop()
    assert nativestr(item1) == nativestr(item)
    # While waiting here the item should be requeued and we should get
    # it again.
    uid2, item2 = queue.pop(timeout=0)
    assert uid2 == uid1
    assert nativestr(item2) == nativestr(item1)
