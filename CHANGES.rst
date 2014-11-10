=======
Changes
=======

Unreleased
----------

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
