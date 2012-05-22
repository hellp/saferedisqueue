=======
Changes
=======

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
