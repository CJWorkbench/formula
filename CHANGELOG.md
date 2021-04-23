2021-04-23.01
-------------

* Handle `Date` the same way we handle `Timestamp`. In Excel, all dates are
  Numbers. When the result is a Number, we don't interpret it as a Workbench
  Date -- same as with timestamp, users see the unformatted Excel Numbers.)

2020-09-15.02
-------------

* Return '#VALUE!' as Text. Previously, Workbench would notify that the step
  crashed if it returned '#VALUE!'

2020-09-15.01
-------------

* Convert True/False formula output into "True" and "False" (Text). Previously,
  Workbench would notify that the step crashed.
