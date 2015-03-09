==============
saferedisqueue
==============

A small wrapper around `Redis <http://www.redis.io>`_ (using the "standard"
`Python redis client lib <https://pypi.python.org/pypi/redis>`_) that provides
access to a FIFO queue and allows upstream code to mark pop'ed items as
processed successfully (ACK'ing) or unsucessfully (FAIL'ing).

Failed items are automatically requeued. Addionally a backup is kept for items
that were neither ack'ed nor fail'ed, i.e. in case the consumer crashes. The
backup items will be requeued as soon as one of the consumer(s) comes up
again.

All actions are atomic and it is safe to have multiple producers and consumers
accessing the same queue concurrently.


Version compatibility with redis.py
------------------------------------

===============      ===============
redis.py             saferedisqueue
===============      ===============
2.4.10 - 2.6.x       1.x
2.7.0 - 2.7.5        no compatible version
2.7.6 - 2.10.x       2.x-3.x
===============      ===============


Usage as a library
==================

>>> queue = SafeRedisQueue(name='test')
>>> queue.put("Hello World")
'595d43b2-2e49-4e96-a1d2-0848d1c7f0d3'
>>> queue.put("Foo bar")
'1df060eb-b578-499d-bede-20db9da8184e'
>>> queue.get()
('595d43b2-2e49-4e96-a1d2-0848d1c7f0d3', 'Hello World')
>>> queue.get()
('1df060eb-b578-499d-bede-20db9da8184e', 'Foo bar')

Note: to be compatible with previous versions, 2 aliases ``push/pop`` exist. Start using the new ``put/get`` terminology as soon as possible since ``push/pop`` will be deleted in a future version.


ACK'ing and FAIL'ing
--------------------

>>> queue.put("Good stuff")
>>> queue.put("Bad stuff")
>>> uid_good, payload_good = queue.get()
>>> uid_bad, payload_bad = queue.get()
...
# process the payloads...
...
>>> queue.ack(uid_good)  # done with that one
>>> queue.fail(uid_bad)  # something didn't work out with that one, let's requeue
>>> uid, payload = queue.get()  # get again; we get the requeued payload again
>>> uid == uid_bad
True
...
# try again
...
>>> queue.ack(uid)  # now it worked; ACK the stuff now


get timeout
-----------

`SafeRedisQueue.get` accepts a timeout parameter:

- 0 (the default) blocks forever, waiting for items
- a positive number blocks that amount of seconds
- a negative timeout disables blocking


Constructor parameters
----------------------

`SafeRedisQueue` accepts ``*args, **kwargs`` and passes them to
`redis.StrictRedis`, so use whatever you need.

*Three exceptions*, use these in the keyword arguments to configure
`SafeRedisQueue` itself:

`url`
    Shortcut to use instead of a host/port/db/password combinations.
    Accepts "redis URLs" just as the redis library does, for example:

    - redis://[:password]@localhost:6379/0
    - unix://[:password]@/path/to/socket.sock?db=0

    When using this keyword parameter, all positional arguments (usually
    one the host) are ignored. Those two are equivalent:

    - ``SafeRedisQueue('localhost', port=6379, db=7)``
    - ``SafeRedisQueue(url='redis://localhost:6379/7')``

`name`
    A prefix used for the keys in Redis. Default: "0", which creates the
    following keys in your Redis DB:

    - srq:0:items
    - srq:0:queue
    - srq:0:ackbuf
    - srq:0:ackbuf_aging

    .. attention::

        The internal data structure changed in version 4.0. Pure
        producer instances (i.e. those only using `put`) are backwards-
        compatible, but consumer instances are not.

`autoclean_interval`

    An interval in seconds (default: 60) at which unconfirmed items
    (neither ACK'ed nor FAIL'ed) are requeued automatically. They are
    moved from the internal ackbuf/ackbuf_aging data structures to the
    queue again.

    Using this spawns a thread that does the autocleaning on a regular
    interval.

    Pass ``None`` to disable autocleaning. It's enabled by default!

    It's recommended to pass ``None`` when creating an instances that
    will only be used as a producer, i.e. one that will only use
    `put`/`push`.

    *The mechanism was completely re-done in version 4.0. See CHANGES
    for details.*

`serializer`
    An optional serializer to use on the items. Default: None

    Feel free to write your own serializer. It only requires a ``dumps``
    and ``loads`` methods. Modules like ``pickle``, ``json``,
    ``simplejson`` can be used out of the box.

    Note however, that when using Python 3 the ``json`` module has to be
    wrapped as it by default does not handle the ``bytes`` properly that
    is emitted by the underlying redis.py networking code. This should
    work::

        class MyJSONSerializer(object):
            @staticmethod
            def loads(bytes):
                return json.loads(bytes.decode('utf-8'))

            @staticmethod
            def dumps(data):
                return json.dumps(data)

        queue = SafeRedisQueue(name='foobar',serializer=MyJSONSerializer)

    *Added in version 3.0.0*


Command line usage
==================

For quick'n'dirty testing, you can use the script from the command line to put stuff into the queue::

    $ echo "Hello World" | python saferedisqueue.py producer

...and get it out again::

    $ python saferedisqueue.py consumer
    cbdabbc8-1c0f-4eb0-8733-fdb62a9c0fa6 Hello World
