django-fuzzy-dates
=================

Introduction
-----

This package provides a custom model field for storing not only typical dates
("yyyy.mm.dd"), but also a year with only a month ("yyyy.mm"), or just a year by
itself ("yyyy"). Dates with no day or no month are "fuzzy" because they are less
precise than typical dates.  This can be useful for concepts such as timelines
that include points where precise data is not available or required (e.g.,
"1492: Columbus reaches the new world" or "Oct. 2002: I begin my year abroad").


The FuzzyDate Object
-----

Fuzzy dates can be instantiated directly in a few different ways:

1) with a python 'datetime' object
2) with a python 'date' object
3) with a string in the format "yyyy", "yyyy.mm", or "yyyy.mm.dd"
4) with keyword arguments "y", "m", and "d"

Here we create one FuzzyDate with a datetime and another with a date:

    $ ./manage.py shell
    ...
    >>> from fuzzy_dates import FuzzyDate
    >>> from datetime import datetime
    >>> today = datetime.today()
    >>> FuzzyDate(today)
    FuzzyDate('2024.03.15')
    >>> FuzzyDate(today.date())
    FuzzyDate('2024.03.15')

Here we create one with a string and another with keyword arguments:

    >>> fd1 = FuzzyDate("2019.01")
    >>> fd2 = FuzzyDate(y="2024", m="2", d="28")

Note that when printing the object, the output is formatted in a more
user-friendly way:

    >>> print(fd1)
    01/2019
    >>> print(fd2)
    02/28/2024

Note also that the individual components of the date are available in the
object's "year", "month", and "day" attributes:

    >>> fd1.year
    '2019'
    >>> fd1.month
    '01'
    >>> fd1.day
    ''

If you want to see the non-fuzzy start and end dates of a FuzzyDate instance,
you can call the instance's "get_range()" method.  It will return a pair of
non-fuzzy FuzzyDate instances:

    >>> fd1.get_range()
    (FuzzyDate('2019.01.01'), FuzzyDate('2019.01.31'))

A FuzzyDate can tell you whether it's fuzzy or not -- that is, if either the
month or day is unspecified.  You might use this, for example, in a form where
the user can supply a time of day as well as a date.  A time of day is only
meaningful if the date is fully specified, so your form might have a `clean()`
method like:

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("start_time"):
            start_date = cleaned_data.get("start_date")
            if not start_date or start_date.is_fuzzy:
                self.add_error("start_time", "If start time is specified, a start date with month, day, and year must also be specified.")


Customization
-----

The format of a stringified FuzzyDate object can be tweaked with the settings
FUZZY_DATE_FIELD_ORDER and FUZZY_DATE_FIELD_SEPARATOR.  These default to "mdy"
and "/".  If we change these (e.g., to "ymd" and "-"), we'll see a different
result

    # With FUZZY_DATE_FIELD_ORDER = "ymd" and FUZZY_DATE_FIELD_SEPARATOR = "-"
    $ ./manage.py shell
    ...
    >>> fd = FuzzyDate("2019.01")
    >>> print(fd)
    2019-01

Note that the dot ("."), dash ("-"), and forward slash ("/") are the only valid
values for FUZZY_DATE_FIELD_SEPARATOR.

By default, the printed date includes leading zeros in values like "01".  This
can be changed with the setting "FUZZY_DATE_TRIM_LEADING_ZEROS".  By setting
this to True, January 2009 (for example) could be printed as "1/2019" instead
of as "01/2019"

Note that changing the FUZZY_DATE_FIELD_ORDER setting will change the order of
the components in the printed date, but the value must still be exactly three
characters long and contain "y", "m", and "d" in some combination.


Using FuzzyDates in Models
-----

Fuzzy dates are probably most useful as fields on a Django model.  Therefore,
this package provides a model field, "FuzzyDateField". Here is a quick example
of how the field might be used in your own "models.py" module.

    from django.db import models
    from fuzzy_dates import FuzzyDateField

    class Event(models.Model):
        name = models.CharField(max_length=50)
        date = FuzzyDateField(blank=True)

        def __str__(self):
            return f"{self.name}: {self.date}"

Note that since FuzzyDate inherits its properties from the `string` class, we
can define the model with `blank=True` just as we would with a string.  However,
unlike with a string, you do not need to pass a `max_length` parameter.


Sorting and Filtering
-----

Fuzzy dates can be sorted alongside non-fuzzy dates.  For example, if we create
a few model instances like this:

    $ ./manage.py shell
    ...
    >>> from <your_app>.models import Event
    >>> Event.objects.create(name="A New Year", date="1992")
    >>> Event.objects.create(name="New Year's Party", date="1991.12.31")
    >>> Event.objects.create(name="New Year's Headache", date="1992.01.01")

We can sort them in the usual way like this:

    >>> for ev in Event.objects.order_by("date"): print(ev)
    ... 
    New Year's Party: 12/31/1991
    A New Year: 1992
    New Year's Headache: 01/01/1992

Or we can filter them like this:

    >>> for ev in Event.objects.filter(date__gte="1992").order_by("date"): print(ev)
    ... 
    A New Year: 1992
    New Year's Headache: 01/01/1992


Using FuzzyDates In Forms
-----

The Fuzzy date model field uses a custom form widget with separate entries for
the year, month, and day.  This form field, which can be imported directly with

    >>> from fuzzy_dates import FuzzyDateFormField

will appear in a Django ModelForm that maps to an object with a FuzzyDateField.
It is also used in the Django admin change view for such an object.  Again, the
ordering of the year, month, and day fields will follow the order prescribed by
the FUZZY_DATE_FIELD_ORDER setting.
