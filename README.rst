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
2.7.6 - 2.10.1       2.x
>=2.10.2             untested
===============      ===============


Usage as a library
==================

>>> queue = SafeRedisQueue(name='test')
>>> queue.push("Hello World")
>>> queue.push("Foo bar")
>>> queue.pop()
('595d43b2-2e49-4e96-a1d2-0848d1c7f0d3', 'Hello World')
>>> queue.pop()
('1df060eb-b578-499d-bede-20db9da8184e', 'Foo bar')


ACK'ing and FAIL'ing
--------------------

>>> queue.push("Good stuff")
>>> queue.push("Bad stuff")
>>> uid_good, payload_good = queue.pop()
>>> uid_bad, payload_bad = queue.pop()
...
# process the payloads...
...
>>> queue.ack(uid_good)  # done with that one
>>> queue.fail(uid_bad)  # something didn't work out with that one, let's requeue
>>> uid, payload = queue.pop()  # pop again; we get the requeued payload again
>>> uid == uid_bad
True
...
# try again
...
>>> queue.ack(uid)  # now it worked; ACK the stuff now


pop timeout
-----------

`SafeRedisQueue.pop` accepts a timeout parameter:

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
    - srq:0:backup
    - srq:0:backuplock

`autoclean_interval`
    An interval in seconds (default: 60) at which *unacknowledged* items are
    requeued automatically. (They are moved from the internal ackbuf and backup data
    structures to the queue again.)

    Pass ``None`` to disable autocleaning. It's enabled by default!


Command line usage
==================

For quick'n'dirty testing, you can use the script from the command line to put stuff into the queue::

    $ echo "Hello World" | python saferedisqueue.py producer

...and get it out again::

    $ python saferedisqueue.py consumer
    cbdabbc8-1c0f-4eb0-8733-fdb62a9c0fa6 Hello World
