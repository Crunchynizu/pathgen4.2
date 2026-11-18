#!/usr/bin/env python
"""Django's command-line utility for PathGen 4.2."""
import os
import sys


def main():
    # `manage.py test` uses the test settings; everything else uses development.
    running_tests = len(sys.argv) > 1 and sys.argv[1] == "test"
    os.environ.setdefault(
        "DJANGO_SETTINGS_MODULE",
        "config.settings.test" if running_tests else "config.settings.development",
    )
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
