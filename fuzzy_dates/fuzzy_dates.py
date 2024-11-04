import calendar
import re
from datetime import date, datetime
from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

# This regex matches dates in the format yyyy, yyyy.mm, or yyyy.mm.dd (other
# separators are allowed, too, e.g., yyyy-mm-dd or yyyy/mm/dd). Thanks to
# https://stackoverflow.com/questions/15474741/python-regex-optional-capture-group
DATE_PATTERN = re.compile(r"(\d{4})(?:[.\-/](\d{2})(?:[.\-/](\d{2}))?)?$")
DATE_FIELD_ORDER = getattr(settings, "FUZZY_DATE_FIELD_ORDER", "mdy").lower()
DATE_FIELD_SEPARATOR = getattr(settings, "FUZZY_DATE_FIELD_SEPARATOR", "/")
DATE_FIELD_PLACEHOLDERS = {
    "y": "yyyy",
    "m": "mm",
    "d": "dd",
}
DATE_FIELD_REQUIRED = {
    "y": True,
    "m": False,
    "d": False,
}
TRIM_CHAR = "0" if getattr(settings, "FUZZY_DATE_TRIM_LEADING_ZEROS", False) else ""


if len(DATE_FIELD_ORDER) != 3 or set(DATE_FIELD_ORDER) != set("ymd"):
    raise ValueError("The FUZZY_DATE_FIELD_ORDER setting must be a 3-character string containing 'y', 'm', and 'd'.")

if DATE_FIELD_SEPARATOR not in ("-", ".", "/"):
    raise ValueError("The FUZZY_DATE_FIELD_SEPARATOR setting must be one of '-', '.', or '/'.")


# We use a custom metaclass to normalize parameters before they are passed to
# the class's "__new__()" and "__init__()" methods.  It also allows FuzzyDate
# instances to be initialized either with a string or via keyword arguments.
class CustomMeta(type):
    def __call__(cls, seed=None, *args, **kwargs):
        if seed:
            if isinstance(seed, str):
                if m := DATE_PATTERN.match(seed):
                    year, month, day = m.groups()
                else:
                    raise ValueError("Dates given as a string must be formatted as yyyy, yyyy.mm, or yyyy.mm.dd")
            elif isinstance(seed, date) or isinstance(seed, datetime):
                year, month, day = seed.year, seed.month, seed.day
            else:
                raise TypeError("Only a string, a date, or a datetime can be passed as an initialization argument")
        else:
            # These could be strings, ints, or None at this point
            year = kwargs.get("y")
            month = kwargs.get("m")
            day = kwargs.get("d")

        if not year:
            raise ValueError("Year must be specified")

        if day and not month:
            raise ValueError("If day is specified, month must also be specified")

        fuzzy_value = "00"
        month = month or fuzzy_value
        day = day or fuzzy_value

        try:
            # Check that values are valid, replacing any fuzzy values with 1. This
            # lets us eliminate invalid dates like 2000.13.01 or 2000.01.32.
            int_year = int(year)
            int_month = int(month) if month != fuzzy_value else 1
            int_day = int(day) if day != fuzzy_value else 1
            if int_year < 1000 or int_year > 9999:
                # Keep the year within this range as years outside it would break
                # sorting (e.g., "900" > "1000" alphanumerically speaking). Later
                # on I might try to relax this restriction by padding short years
                # with zeros, but it would take some doing.
                raise ValueError("The year must be no less than 1000 and no greater than 9999.")
            # else
            date(year=int_year, month=int_month, day=int_day)
        except ValueError as e:
            raise e

        kwargs = {"y": f"{year}", "m": f"{month:>02}", "d": f"{day:>02}"}
        return super().__call__(*args, **kwargs)


# All dates are stored in the DB as strings formatted as "yyyy.mm.dd". Using
# this format means that comparing and sorting dates is as easy as comparing
# and sorting strings. For fuzzy dates (e.g., just a year or just a year and
# a month), we use a value of "00" in place of the missing month and/or day.
# Fuzzy dates can then be sorted with non-fuzzy dates.
class FuzzyDate(str, metaclass=CustomMeta):
    def __new__(cls, **kwargs):
        return super().__new__(cls, "{y}.{m}.{d}".format(**kwargs))

    def __init__(self, **kwargs):
        self.year = kwargs["y"]
        self.month = kwargs["m"] if kwargs["m"] != "00" else ""
        self.day = kwargs["d"] if kwargs["d"] != "00" else ""
        return super().__init__()

    def __repr__(self):
        return "FuzzyDate({})".format(super().__repr__())

    def __str__(self):
        data_dict = dict(zip("ymd", self.as_list()))
        return DATE_FIELD_SEPARATOR.join(
            [data_dict[el].lstrip(TRIM_CHAR) for el in DATE_FIELD_ORDER if data_dict[el]]
        )

    def as_list(self):
        return [self.year, self.month, self.day]

    def as_date(self, default=None):
        non_fuzzy = None
        if self.is_fuzzy:
            if default is None:
                return None
            elif default == "start":
                non_fuzzy = self.get_start()
            elif default == "end":
                non_fuzzy = self.get_end()
            else:
                raise ValueError("Valid values for `default` are `None`, `start`, and `end`.")
        else:
            non_fuzzy = self

        return date(*[int(v) for v in non_fuzzy.as_list()])

    def get_start(self):
        year = self.year
        month = self.month or "01"
        day = self.day or "01"
        return FuzzyDate(y=year, m=month, d=day)

    def get_end(self):
        year = self.year
        month = self.month or "12"
        day = self.day or str(calendar.monthrange(int(year), int(month))[1])
        return FuzzyDate(y=year, m=month, d=day)

    def get_range(self):
        return (
            self.get_start(),
            self.get_end(),
        )

    @property
    def is_fuzzy(self):
        return self.day == ""


class FuzzyDateWidget(forms.MultiWidget):
    def __init__(self, attrs=None):
        # Define the input widgets in the user's preferred order.
        widgets = [
            forms.NumberInput(attrs={
                "min": 1, "placeholder": DATE_FIELD_PLACEHOLDERS[el]
            }) for el in DATE_FIELD_ORDER
        ]
        super().__init__(widgets, attrs)

    def decompress(self, value):
        if value:  # will be a FuzzyDate object
            data_dict = dict(zip("ymd", value.as_list()))
            return [data_dict[el] for el in DATE_FIELD_ORDER]  # rearrange to the user's preferred order
        return ["", "", ""]


class FuzzyDateFormField(forms.MultiValueField):

    def __init__(self, *args, **kwargs):
        # Remove default values of `models.Charfield`
        # that are not valid for `forms.MultiValueField`:
        # See `django/db/models/fields/__init__.py:Charfield.formfield`.
        for k in ("max_length", "empty_value"):
            kwargs.pop(k, None)

        fields = [
            forms.IntegerField(
                min_value=1, required=DATE_FIELD_REQUIRED[el]
            ) for el in DATE_FIELD_ORDER
        ]
        kwargs["require_all_fields"] = False
        super().__init__(fields, *args, **kwargs)
        self.widget = FuzzyDateWidget()
        for field in fields:
            for validator in field.validators:
                if isinstance(validator, MinValueValidator):
                    validator.message = "Ensure all values are greater than 1."

    def compress(self, data_list):
        if data_list:
            data_dict = dict(zip(DATE_FIELD_ORDER, data_list))
            try:
                return FuzzyDate(**data_dict)
            except ValueError as e:
                raise ValidationError(e)
        return ""


class FuzzyDateField(models.CharField):

    def __init__(self, *args, **kwargs):
        kwargs["max_length"] = 10
        super().__init__(*args, **kwargs)

    def formfield(self, **kwargs):
        kwargs.update({"form_class": FuzzyDateFormField})
        return super().formfield(**kwargs)

    def from_db_value(self, value, expression, connection):
        if value:
            # Values coming from the DB should be in the format yyyy.mm.dd
            return FuzzyDate(value)
        # else
        return value

    def to_python(self, value):
        if value and not isinstance(value, FuzzyDate):
            try:
                if m := DATE_PATTERN.match(value):
                    y, m, d = m.groups()
                    value = FuzzyDate(y=y, m=m, d=d)
                else:
                    raise ValidationError("Date strings must be formatted as 'yyyy', 'yyyy.mm', or 'yyyy.mm.dd'")
            except TypeError as e:
                raise ValidationError(e)
        return value
