
from uuid import uuid1
import time

import pytest

from saferedisqueue import SafeRedisQueue


def test_autocleanup():
    queue = SafeRedisQueue(
        name='saferedisqueue-test-%s' % uuid1().hex,
        autoclean_interval=1)
    queue.push('bad')
    queue.push('good')
    assert queue._redis.llen(queue.QUEUE_KEY) == 2
    assert queue._redis.llen(queue.ACKBUF_KEY) == 0
    assert queue._redis.llen(queue.BACKUP) == 0

    uid_bad, payload_bad = queue.pop()
    # Pop triggered first autoclean run before popping. At that time the
    # ackbuf was still empty, so nothing was moved to backup. But the
    # backup lock was set, to delay the next autoclean run for
    # autoclean_interval seconds.
    assert queue._redis.llen(queue.QUEUE_KEY) == 1
    assert queue._redis.llen(queue.ACKBUF_KEY) == 1  # bad item
    assert queue._redis.llen(queue.BACKUP) == 0

    uid_good, payload_good = queue.pop()
    # Autoclean started but instantly aborted due to backup lock.
    assert queue._redis.llen(queue.ACKBUF_KEY) == 2
    assert queue._redis.llen(queue.BACKUP) == 0
    assert queue._redis.llen(queue.QUEUE_KEY) == 0

    queue.ack(uid_good)  # done with that one
    assert queue._redis.llen(queue.ACKBUF_KEY) == 1  # bad item
    assert queue._redis.llen(queue.BACKUP) == 0
    assert queue._redis.llen(queue.QUEUE_KEY) == 0

    # Pop after a autoclean_interval triggers cleanup internally
    time.sleep(1.2)
    assert queue.pop(timeout=-1) == (None, None)
    assert queue._redis.llen(queue.ACKBUF_KEY) == 0
    assert queue._redis.llen(queue.BACKUP) == 1
    assert queue._redis.llen(queue.QUEUE_KEY) == 0

    # Next pop triggers autoclean again; requeus; pops bad item again
    time.sleep(1.2)
    assert queue.pop(timeout=-1) == (uid_bad, payload_bad)

    # After pop, queue is empty again, item waiting in ackbuf
    assert queue._redis.llen(queue.ACKBUF_KEY) == 1
    assert queue._redis.llen(queue.BACKUP) == 0
    assert queue._redis.llen(queue.QUEUE_KEY) == 0


@pytest.mark.parametrize("func_name, ok_return_val, err_return_val", [
    ('renameifexists', 'OK', 'OK'),
    ('renamenxifexists', 1, 0),
])
def test_lua_rename_scripts(func_name, ok_return_val, err_return_val):
    queue = SafeRedisQueue()
    key1 = 'test_saferedisqueue_' + uuid1().hex
    key2 = 'test_saferedisqueue_' + uuid1().hex
    key3 = 'test_saferedisqueue_' + uuid1().hex
    key4 = 'test_saferedisqueue_' + uuid1().hex

    func = getattr(queue, '_redis_' + func_name)

    assert queue._redis.exists(key1) is False
    assert queue._redis.exists(key2) is False

    queue._redis.set(key1, 'foobar')
    assert queue._redis.exists(key1) is True
    assert queue._redis.exists(key2) is False

    assert func(keys=[key1, key2]) == ok_return_val
    assert queue._redis.exists(key1) is False
    assert queue._redis.get(key2) == 'foobar'

    assert func(keys=[key1, key2]) == 'OK'
    assert func(keys=[key3, key2]) == 'OK'

    queue._redis.set(key4, 'foobar')
    assert func(keys=[key4, key2]) == err_return_val

    # cleanup
    queue._redis.delete(key1)
    queue._redis.delete(key2)
    queue._redis.delete(key3)
    queue._redis.delete(key4)


# Serializer tests
# Try with json and pickle serializer

try:
    import simplejson as JSONSerializer
except ImportError:
    import json as JSONSerializer

import pickle as PickleSerializer


@pytest.mark.parametrize("serializer", [
    JSONSerializer,
    PickleSerializer,
])
def test_serializer(serializer):

    queue = SafeRedisQueue(
        name='saferedisqueue-test-%s' % uuid1().hex,
        autoclean_interval=1,
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
