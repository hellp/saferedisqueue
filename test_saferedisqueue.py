
from uuid import uuid1
import time

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
