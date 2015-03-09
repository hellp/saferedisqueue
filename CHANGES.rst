=======
Changes
=======

4.0b0 – 2015-03-09
------------------

- BREAKING CHANGE: the data structures used on the Redis server side
  changed. While pure consumer instances (i.e. those only using `put`)
  are backwards compatibility, consuming instances are **not**. This
  means multiple consumers working on one queue must be compatible.
  Before upgrading, make sure the queue is emptied.

- The automatic requeue mechanism was reimplemented: Instead of a
  complicated algorithm that used locks and was so poorly implemented
  that it still had race conditions and caused inconsistent server-side
  state occasionally, we are now using a sorted set (ZSET) that keeps
  track of unconfirmed (neither ACK'ed *nor* FAIL'ed) and aging items.

  Note however: the new mechanism uses a thread to do the cleaning every
  x seconds (via the `autoclean_interval` parameter) independently of
  any `get`/`pop` calls. If threading gives you a headache, check out
  the code before using it. Remember, autocleaning is enabled by
  default! To disable it, pass ``autoclean_interval=None`` to the
  constructor -- this also disables any threading code; it's recommended
  to use it always for producer-only instances.


3.0.0 - 2014-11-13
------------------

- BREAKING CHANGE (very unlikely, though): `push`/`put` now returns the
  uid of the just added item. Before it always returned `None`.
- `push` has been renamed to `put`; `push` stays as an alias, but is
  deprecated and will be removed in version 4.
- `pop` has been renamed to `get`; `pop` stays as an alias, but is
  deprecated and will be removed in version 4.
- Increased version compatibility with redis.py to "<2.11".
- Python 3.4 support
- More tests. Introduced tox for testing.
- Added `serializer` parameter to support custom serializers,
  e.g. for automatic JSON conversion. See README for details, especially
  when using Python 3.


2.0.0 - 2014-06-26
------------------

- SafeRedisQueue is now officially compatible with recent versions
  (roughly speaking 2.7-2.10) of redis.py.

  For versions 2.4 and 2.6 please continue using the 1.x development
  line.

  See README.rst for details on compatibility.


1.2.0 - 2014-06-26
------------------

- Raise compatible redis.py version up to 2.6.x. Updated README with
  compatibility details.



1.1.0 - 2014-06-20
------------------

- The constructor now accepts a "url" keyword parameter that supports
  typical redis URL a la "redis://[:password]@localhost:6379/0". See
  README for details.


1.0.1 - 2013-06-26
------------------

- Changed dependency on redis to require at least version 2.4.10 as
  redis.StrictRedis, which we use, was only introduced in that version.
  This should not affect anyone negatively as you wouldn't have to be able
  to use saferedisqueue at all if your project or package used an older
  version so far.
  (Thanks Telofy!)


1.0.0 - 2013-06-05
------------------

- Released as open-source under 3-clause BSD license. Code identical to 0.3.0.


0.3.0 - 2012-05-22
------------------

- The constructor now accepts an "autoclean_interval" value to set the interval
  at which the ackbuf -> backup rotation and backup requeuing happens.
  Setting the value to `None` disables autoclean completely.
  Default: 60 (seconds).


0.2.2 - 2012-03-29
------------------

- Negative timeout makes .pop() non-blocking.


0.2.1 - 2012-03-09
------------------

- Added setup.py and publish it on our internal package directory.


0.2.0 - 2012-03-08
------------------

- Renamed methods ("push_item" -> "push" etc.)
- New autoclean method that is called on every .pop()
- Internal: New names for keys in the redis db.
