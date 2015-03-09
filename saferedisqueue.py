# -*- coding: utf-8 -*-
"""
saferedisqueue
~~~~~~~~~~~~~~

A small wrapper around Redis that provides access to a FIFO queue and allows
upstream code to mark pop'ed items as processed successfully (ACK'ing) or
unsucessfully (FAIL'ing).

:copyright: (c) Fabian Neumann, ferret go GmbH
:license: BSD, see LICENSE for details
"""

from threading import Thread
import time
import uuid

import redis


class SafeRedisQueue(object):

    AUTOCLEAN_INTERVAL = 60

    def __init__(self, *args, **kw):
        prefix = 'srq:%s' % kw.pop('name', '0')
        self.QUEUE_KEY = '%s:queue' % prefix
        self.ITEMS_KEY = '%s:items' % prefix
        self.ACKBUF_KEY = '%s:ackbuf' % prefix
        self.ACKBUF_AGING = '%s:ackbuf_aging' % prefix
        self.AUTOCLEAN_INTERVAL = kw.pop('autoclean_interval',
                                         self.AUTOCLEAN_INTERVAL)
        self.serializer = kw.pop('serializer', None)

        url = kw.pop('url', None)
        if url is not None:
            self._redis = redis.StrictRedis.from_url(url, **kw)
        else:
            self._redis = redis.StrictRedis(*args, **kw)

        self._redis_ackbuf_to_aging = self._redis.register_script("""
            local ackbuf = KEYS[1]
            local ackbuf_aging = KEYS[2]
            local now_micros = ARGV[1]
            local ackbuflen = redis.call('llen', ackbuf)
            local iterations = math.min(ackbuflen, 100)
            for i=1,iterations,1
            do
                redis.pcall('zadd', ackbuf_aging, now_micros + i, redis.pcall('rpop', ackbuf))
            end
            return ackbuflen - iterations
            """)

        self._redis_zset_to_list_if_older = self._redis.register_script("""
            local zset = KEYS[1]
            local list = KEYS[2]
            local max_age_s = ARGV[1]
            local now_micros = ARGV[2]
            local max_score = now_micros - (max_age_s * 10^6)
            local values = redis.call('ZRANGEBYSCORE', zset, '-inf', max_score, 'LIMIT', 0, 100)
            if #values > 0
            then
                redis.call('LPUSH', list, unpack(values))
                redis.call('ZREM', zset, unpack(values))
                return redis.call('ZCOUNT', zset, '-inf', max_score)
            else
                return 0
            end
            """)

        def autoclean_loop(srq):
            interval = min(max(float(srq.AUTOCLEAN_INTERVAL) * 0.5, 0.1), 5)
            while True:
                srq._autoclean(max_seconds=interval * 0.9)
                time.sleep(interval)

        if self.AUTOCLEAN_INTERVAL is not None:
            self._autoclean_thread = Thread(
                target=autoclean_loop, name="autocleaner", args=(self,))
            self._autoclean_thread.daemon = True
            self._autoclean_thread.start()

    def _autoclean(self, max_seconds):
        deadline = time.time() + max_seconds
        while True:
            now = time.time()
            if now >= deadline:
                break
            now_micros = int(now * 10**6)
            ackbuf_remaining = self._redis_ackbuf_to_aging(
                    keys=[self.ACKBUF_KEY, self.ACKBUF_AGING],
                    args=[now_micros])
            aa_remaining = self._redis_zset_to_list_if_older(
                    keys=[self.ACKBUF_AGING, self.QUEUE_KEY],
                    args=[self.AUTOCLEAN_INTERVAL, now_micros])
            if ackbuf_remaining + aa_remaining == 0:
                break

    def put(self, item):
        """Adds an item to the queue.

        Generates a uid for later referral.
        Enqueues the uid and stores the item.
        """
        uid = str(uuid.uuid4())

        if self.serializer is not None:
            item = self.serializer.dumps(item)

        self._redis.pipeline()\
                .hset(self.ITEMS_KEY, uid, item)\
                .lpush(self.QUEUE_KEY, uid)\
                .execute()
        return uid

    # Kept for backwards compatibility
    push = put

    def get(self, timeout=0):
        """Return next item from queue. Blocking by default.

        Blocks if queue is empty, see `timeout` parameter.

        Internally this also pops uid from queue and writes it to
        ackbuffer.

        :param timeout: blocking timeout in seconds
                        - 0: block forever (default)
                        - negative: disable blocking

        """
        if timeout < 0:
            uid = self._redis.rpoplpush(self.QUEUE_KEY, self.ACKBUF_KEY)
        else:
            uid = self._redis.brpoplpush(self.QUEUE_KEY, self.ACKBUF_KEY, timeout)
        item = self._redis.hget(self.ITEMS_KEY, uid)

        # Deserialize only if the item exists: it is equal to None if it times out
        if self.serializer is not None and item is not None:
            item = self.serializer.loads(item)

        return uid, item

    # Kept for backwards compatibility
    pop = get

    def ack(self, uid):
        """Acknowledge item as successfully consumed.

        Removes uid from ackbuffer and deletes the corresponding item.
        """
        self._redis.pipeline()\
                   .lrem(self.ACKBUF_KEY, 0, uid)\
                   .zrem(self.ACKBUF_AGING, uid)\
                   .hdel(self.ITEMS_KEY, uid)\
                   .execute()

    def fail(self, uid):
        """Report item as not successfully consumed.

        Removes uid from ackbuffer and re-enqueues it.
        """
        self._redis.pipeline()\
                   .lrem(self.ACKBUF_KEY, 0, uid)\
                   .zrem(self.ACKBUF_AGING, uid)\
                   .lpush(self.QUEUE_KEY, uid)\
                   .execute()


if __name__ == "__main__":
    import sys

    def _usage():
        sys.stdout.writelines([
            'Commandline usage: python saferedisqueue.py <consumer | producer | demo>\n'
            'Example:\n'
            '    $ echo "Hello World" | python saferedisqueue.py producer\n'
            '    $ python saferedisqueue.py consumer\n'
            '    cbdabbc8-1c0f-4eb0-8733-fdb62a9c0fa6 Hello World\n'
        ])
        sys.exit(1)

    if len(sys.argv) != 2:
        _usage()

    queue = SafeRedisQueue(name='test')

    if sys.argv[1] == 'producer':
        for line in sys.stdin.readlines():
            queue.put(line.strip())
    elif sys.argv[1] == 'consumer':
        while True:
            uid, item = queue.get()
            queue.ack(uid)
            print(uid, item)
    elif sys.argv[1] == 'demo':
        map(queue.put, ['Hello', 'World'])
        while True:
            uid, item = queue.get(timeout=1)
            if uid is None:
                sys.exit()
            queue.ack(uid)
            print(uid, item)
    else:
        _usage()
