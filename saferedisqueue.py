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

import uuid

import redis


class SafeRedisQueue(object):

    AUTOCLEAN_INTERVAL = 60

    def __init__(self, *args, **kw):
        prefix = 'srq:%s' % kw.pop('name', '0')
        self.QUEUE_KEY = '%s:queue' % prefix
        self.ITEMS_KEY = '%s:items' % prefix
        self.ACKBUF_KEY = '%s:ackbuf' % prefix
        self.BACKUP = '%s:backup' % prefix
        self.BACKUP_LOCK = '%s:backuplock' % prefix
        self.AUTOCLEAN_INTERVAL = kw.pop('autoclean_interval',
                                         self.AUTOCLEAN_INTERVAL)
        self.serializer = kw.pop('serializer', None)

        url = kw.pop('url', None)
        if url is not None:
            self._redis = redis.StrictRedis.from_url(url, **kw)
        else:
            self._redis = redis.StrictRedis(*args, **kw)

        self._redis_renameifexists = self._redis.register_script("""
            if redis.pcall('exists', KEYS[1]) == 1
            then
                return redis.pcall('rename', KEYS[1], KEYS[2])
            else
                return {ok='OK'}
            end
        """)

        self._redis_renamenxifexists = self._redis.register_script("""
            if redis.pcall('exists', KEYS[1]) == 1
            then
                return redis.pcall('renamenx', KEYS[1], KEYS[2])
            else
                return {ok='OK'}
            end
        """)

    def _autoclean(self):
        if self.AUTOCLEAN_INTERVAL is None:
            return
        if self._redis.exists(self.BACKUP_LOCK):
            return
        if self._redis.exists(self.BACKUP):
            # Get the lock
            if self._redis.setnx(self.BACKUP_LOCK, 1):
                # There's a potential deadlock here:
                # If we crash during the while loop, the BACKUP_LOCK will never
                # be set to expire, blocking the creation of a new backup queue.
                # Could be solved by setting the expire immediately, although
                # then the guard could expire before we are done with the
                # requeuing. Although that is very unlikely.
                while self._redis.rpoplpush(self.BACKUP, self.QUEUE_KEY):
                    pass
                with self._redis.pipeline() as pipe:
                    self._redis_renameifexists(
                        keys=[self.ACKBUF_KEY, self.BACKUP],
                        client=pipe)
                    pipe.expire(self.BACKUP_LOCK, self.AUTOCLEAN_INTERVAL)
                    pipe.execute()
        else:
            with self._redis.pipeline() as pipe:
                try:
                    pipe.watch(self.BACKUP_LOCK)
                    if pipe.exists(self.BACKUP_LOCK) is False:
                        pipe.multi()
                        self._redis_renamenxifexists(
                            keys=[self.ACKBUF_KEY, self.BACKUP],
                            client=pipe)
                        pipe.setex(self.BACKUP_LOCK, self.AUTOCLEAN_INTERVAL, 1)
                        pipe.execute()
                    else:
                        pipe.unwatch()
                except redis.WatchError:
                    pass

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
        self._autoclean()
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
                   .lrem(self.BACKUP, 0, uid)\
                   .hdel(self.ITEMS_KEY, uid)\
                   .execute()

    def fail(self, uid):
        """Report item as not successfully consumed.

        Removes uid from ackbuffer and re-enqueues it.
        """
        self._redis.pipeline()\
                   .lrem(self.ACKBUF_KEY, 0, uid)\
                   .lrem(self.BACKUP, 0, uid)\
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
