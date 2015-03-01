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
import uuid
import multiprocessing
import time

from redlock import Redlock
import redis


class UnknownInstruction(Exception):
    pass


class SafeRedisQueue(object):

    AUTOCLEAN_INTERVAL = 60

    def __init__(self, *args, **kw):
        self.logger = multiprocessing.get_logger()
        prefix = 'srq:%s' % kw.pop('name', '0')
        self.QUEUE_KEY = '%s:queue' % prefix
        self.ITEMS_KEY = '%s:items' % prefix
        self.ACKBUF = '%s:ackbuf' % prefix
        self.ACKBUF_AGING = '%s:ackbuf_aging' % prefix
        self.ACKBUF_AGING_REDLOCK = '%s:ackbuf_aging_redlock' % prefix
        self.ACKBUF_EXP_PREFIX = '%s:ackbuf_expired-' % prefix
        self.AUTOCLEAN_INTERVAL = kw.pop('autoclean_interval',
                                         self.AUTOCLEAN_INTERVAL)
        self.serializer = kw.pop('serializer', None)

        url = kw.pop('url', None)
        if url is not None:
            self._redis = redis.StrictRedis.from_url(url, **kw)
        else:
            self._redis = redis.StrictRedis(*args, **kw)

        self._dlm = Redlock([(args, kw)], retry_count=1)
        self.logger.info(self._dlm)

        self._redis_activate_queue = self._redis.register_script("""
            local main_queue_existed = redis.pcall('exists', '{queue_key}') == 1
            if main_queue_existed
            then
                redis.pcall('rename', '{queue_key}', KEYS[2])
            end
            if redis.pcall('exists', KEYS[1]) == 1
            then
                redis.pcall('rename', KEYS[1], '{queue_key}')
                if main_queue_existed
                then
                    redis.pcall('lpush', '{queue_key}', ARGV[1])
                end
            end
        """.format(queue_key=self.QUEUE_KEY))

        self._redis_renamenxifexists = self._redis.register_script("""
            if redis.pcall('exists', KEYS[1]) == 1
            then
                return redis.pcall('renamenx', KEYS[1], KEYS[2])
            else
                return 0
            end
        """)

        def autoclean_loop(srq_instance):
            while True:
                self._autoclean()
                time.sleep(self.AUTOCLEAN_INTERVAL)

        if self.AUTOCLEAN_INTERVAL:
            Thread(target=autoclean_loop, name="autocleaner",
                   args=(self, )).start()

    def _autoclean(self):
        lock = self._dlm.lock(self.ACKBUF_AGING_REDLOCK, self.AUTOCLEAN_INTERVAL * 1000)
        if lock is False or lock.validity < 250:
            self.logger.info('autoclean NO LOCK :( %r', lock)
            return
        self.logger.info('autoclean GOT LOCK :) %r', lock)

        if not self._redis.exists(self.ACKBUF_AGING):
            self.logger.info('autoclean RENAME TO ACKBUF_AGING')
            # Rename ACKBUF to ACKBUF_AGING
            self._redis_renamenxifexists(keys=[self.ACKBUF, self.ACKBUF_AGING])
        else:
            # Expire ACKBUF_AGING and push an SRQ instruction to the main queue.
            new_name = self.ACKBUF_EXP_PREFIX + uuid.uuid1().hex
            activate_instr = '__srqinstr__:{uid}:activate:{queue_name}'.format(
                uid=uuid.uuid1(), queue_name=new_name)
            self.logger.info('autoclean EXPIRE ACKBUF_AGING to %r %r', new_name, activate_instr)
            with self._redis.pipeline() as pipe:
                pipe.multi()
                pipe.rename(self.ACKBUF_AGING, new_name)
                pipe.lpush(self.QUEUE_KEY, activate_instr)
                pipe.execute()
        self.logger.info('autoclean DONE')

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
        "ackbuffer", where it waits to be ack'ed or fail'ed.

        :param timeout: blocking timeout in seconds
                        - 0: block forever (default)
                        - negative: disable blocking

        """
        while True:
            if timeout < 0:
                uid = self._redis.rpoplpush(self.QUEUE_KEY, self.ACKBUF)
            else:
                uid = self._redis.brpoplpush(self.QUEUE_KEY, self.ACKBUF, timeout)

            if uid is not None and uid.startswith('__srqinstr__'):
                self._handle_special_instruction(uid)
                self.ack(uid)
                continue
            else:
                break

        item = self._redis.hget(self.ITEMS_KEY, uid)

        # Deserialize only if the item exists: it is equal to None if it times out
        if self.serializer is not None and item is not None:
            item = self.serializer.loads(item)

        return uid, item

    # Kept for backwards compatibility
    pop = get


    def _handle_special_instruction(self, instr_string):
        """
        Handle a special instruction for internal usage by SafeRedisQueue.
        Those are encoded in a key::

            "__srqinstr__:<uuid>:<instruction_name>[:<remainder>]"

        """
        self.logger.info('HANDLE instruction %r', instr_string)
        _preamble, _instr_id, instr, remainder = instr_string.split(':', 3)
        if instr == 'activate':
            waiting_q = remainder
            new_waiting_q = '{query_key}-waiting-{uid}'.format(
                query_key=self.QUEUE_KEY, uid=uuid.uuid1())
            activate_instr = '__srqinstr__:{uid}:activate:{queue_name}'.format(
                uid=uuid.uuid1(), queue_name=new_waiting_q)
            self.logger.info('HANDLE INST: new_waiting_q:%r  activate_instr:%r', new_waiting_q, activate_instr)
            self._redis_activate_queue(
                keys=[waiting_q, new_waiting_q],
                args=[activate_instr])
        else:
            raise UnknownInstruction('Unknown instruction: %r' % instr)


    def ack(self, uid):
        """Acknowledge item as successfully consumed.

        Removes uid from ackbuffer and deletes the corresponding item.
        """
        self._redis.pipeline()\
                   .lrem(self.ACKBUF, 0, uid)\
                   .lrem(self.ACKBUF_AGING, 0, uid)\
                   .hdel(self.ITEMS_KEY, uid)\
                   .execute()

    def fail(self, uid):
        """Report item as not successfully consumed.

        Removes uid from ackbuffer and re-enqueues it.
        """
        self._redis.pipeline()\
                   .lrem(self.ACKBUF, 0, uid)\
                   .lrem(self.ACKBUF_AGING, 0, uid)\
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
