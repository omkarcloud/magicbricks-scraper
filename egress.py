"""The one network helper the magicbricks module needs: the Accept-Language
its sessions send. magicbricks.com is an Indian English-language site, so
every session announces the list a desktop Chrome in India sends — on your
own connection or on MAGICBRICKS_PROXY alike."""

INDIAN_ENGLISH = "en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7"


def site_accept_language(site=None):
    return INDIAN_ENGLISH


def accept_language(proxy=None, country=None):
    return INDIAN_ENGLISH
