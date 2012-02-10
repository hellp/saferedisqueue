# -*- coding: utf-8 -*-
"""
saferedisqueue
~~~~~~~~~~~~~~

A small wrapper around Redis that provides access to a FIFO queue and allows
upstream code to mark pop'ed items as processed successfully (ACK'ing) or
unsucessfully (FAIL'ing). Failed items are automatically requeued. Addionally
a backup is kept for items that were neither ack'ed nor fail'ed, i.e. in case
the consumer crashes. The backup items will be requeued as soon as one of the
consumer(s) comes up again.

All actions are atomic and it is safe to have multiple producers and consumers
accessing the same queue concurrently.

:copyright: (c) Ferret Go GmbH, Sean Buttinger, Fabian Neumann
:license: All Rights Reserved. For now.
"""

__version__ = '0.1.0'


import uuid

import redis


class SafeRedisQueue(object):

    QUEUE_KEY = 'srq_queue'
    ACKBUF_KEY = 'srq_ackbuf'
    BACKUP = 'srq_backup'
    BACKUP_LOCK = 'srq:lock:backup'
    ITEM_KEY_PREFIX = 'srq_item'
    AUTOCLEAN_TIMEOUT = 60

    def __init__(self, *args, **kwargs):
        self._redis = redis.StrictRedis(*args, **kwargs)

    def _item_key(self, uid):
        return '%s:%s' % (self.ITEM_KEY_PREFIX, uid)

    def _autoclean(self):
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
                self._redis.pipeline()\
                    .multi()\
                    .renamenx(self.ACKBUF_KEY, self.BACKUP)\
                    .expire(self.BACKUP_LOCK, self.AUTOCLEAN_TIMEOUT)\
                    .execute()
        else:
            with self._redis.pipeline() as pipe:
                try:
                    pipe.watch(self.BACKUP_LOCK)
                    if not pipe.exists(self.BACKUP_LOCK):
                        pipe.multi()\
                            .renamenx(self.ACKBUF_KEY, self.BACKUP)\
                            .setex(self.BACKUP_LOCK, self.AUTOCLEAN_TIMEOUT, 1)\
                            .execute()
                    else:
                        pipe.unwatch()
                except redis.WatchError:
                    pass

    def push_item(self, item):
        """Adds an item to the queue.

        Generates a uid for later referral.
        Enqueues the uid and stores the item.
        """
        uid = uuid.uuid4()
        self._redis.pipeline()\
                .set(self._item_key(uid), item)\
                .lpush(self.QUEUE_KEY, uid)\
                .execute()

    def get_item(self, uid):
        """Get item for uid.
        """
        item = self._redis.get(self._item_key(uid))
        return item

    def pop_item(self, timeout=0):
        """Get next item from queue. Blocks if queue is empty.

        Pops uid from queue and writes it to ackbuffer.
        Returns the corresponding item.
        """
        self._autoclean()
        uid = self._redis.brpoplpush(self.QUEUE_KEY, self.ACKBUF_KEY, timeout)
        item = self.get_item(uid)
        return uid, item

    def ack_item(self, uid):
        """Acknowledge item as successfully consumed.

        Removes uid from ackbuffer and deletes the corresponding item.
        """
        self._redis.pipeline()\
                   .lrem(self.ACKBUF_KEY, uid)\
                   .lrem(self.BACKUP, uid)\
                   .delete(self._item_key(uid))\
                   .execute()

    def fail_item(self, uid):
        """Report item as not successfully consumed.

        Removes uid from ackbuffer and re-enqueues it.
        """
        self._redis.pipeline()\
                   .lrem(self.ACKBUF_KEY, uid)\
                   .lrem(self.BACKUP, uid)\
                   .lpush(self.QUEUE_KEY, uid)\
                   .execute()


if __name__ == "__main__":
    import sys
    queue = SafeRedisQueue()

    def _usage():
        sys.stdout.writelines([
            'Commandline usage: python saferedisqueue.py <consumer | producer>\n'
            'Example:\n'
            '    $ echo "Hello World!" | python saferedisqueue.py producer\n'
            '    $ python saferedisqueue.py consumer\n'
            '    cbdabbc8-1c0f-4eb0-8733-fdb62a9c0fa6 Hello World!\n'
        ])
        sys.exit(1)

    if len(sys.argv) != 2:
        _usage()

    if sys.argv[1] == 'producer':
        for line in sys.stdin.readlines():
            queue.push_item(line.strip())
        # for i in range(10):
        #     queue.push_item("Quick brown fox jumps over hullifoop.")
    elif sys.argv[1] == 'consumer':
        while True:
            uid, item = queue.pop_item()
            print uid, item
    else:
        _usage()
