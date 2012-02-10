# -*- coding: utf-8 -*-
"""
saferedisqueue
~~~~~~~~~~~~~~

A small wrapper around Redis that provides access to a FIFO queue and allows
upstream code to mark pop'ed items as processed successfully (ACK'ing) or
unsucessfully (FAIL'ing). Failed items are automatically requeued. Addionally
a backup is kept for items that were neither ack'ed nor fail'ed, i.e. in case
the consumer crashes.

Note: automatic requeueing of items from the backup queue is currently not
implemented, but a development branch already exists.

All actions are atomic and it is safe to have multiple producers and consumers
accessing the same queue concurrently.

:copyright: (c) Ferret Go GmbH
:license: All Rights Reserved. For now.
"""

__version__ = '0.1.0'


import uuid

import redis


class SafeRedisQueue(object):

    QUEUE_KEY = 'fb_queue'
    ACKBUF_KEY = 'fb_ackbuf'
    ITEM_KEY_PREFIX = 'fb_item'

    def __init__(self, *args, **kwargs):
        self._redis = redis.StrictRedis(*args, **kwargs)

    def _item_key(self, uid):
        return '%s:%s' % (self.ITEM_KEY_PREFIX, uid)

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
        uid = self._redis.brpoplpush(self.QUEUE_KEY, self.ACKBUF_KEY, timeout)
        item = self.get_item(uid)
        return uid, item

    def ack_item(self, uid):
        """Acknowledge item as successfully consumed.

        Removes uid from ackbuffer and deletes the corresponding item.
        """
        self._redis.pipeline()\
                   .lrem(self.ACKBUF_KEY, uid)\
                   .delete(self._item_key(uid))\
                   .execute()

    def fail_item(self, uid):
        """Report item as not successfully consumed.

        Removes uid from ackbuffer and re-enqueues it.
        """
        self._redis.pipeline()\
                   .lrem(self.ACKBUF_KEY, uid)\
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
