# Copyright 2014 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Twisted Application Plugin code for the MAAS Region."""

from __future__ import (
    absolute_import,
    print_function,
    unicode_literals,
    )

str = None

__metaclass__ = type
__all__ = [
    "RegionServiceMaker",
]

from twisted.application.service import IServiceMaker
from twisted.plugin import IPlugin
from twisted.python import usage
from zope.interface import implementer


class Options(usage.Options):
    """Command line options for the MAAS Region Controller."""


@implementer(IServiceMaker, IPlugin)
class RegionServiceMaker:
    """Create a service for the Twisted plugin."""

    options = Options

    def __init__(self, name, description):
        self.tapname = name
        self.description = description

    def makeService(self, options):
        """Construct a service."""
        from twisted.internet import reactor
        # This is a workaround until we implement proper unbounded threadpool
        # with a cleanup method.
        reactor.suggestThreadPoolSize(1024 * 10)
        # Get something going with the logs.
        from provisioningserver import logger
        logger.basicConfig()
        # Some region services use the ORM at class-load time: force Django to
        # load the models first.
        try:
            from django import setup as django_setup
        except ImportError:
            pass  # Django < 1.7
        else:
            django_setup()
        # Prevent other libraries from starting the reactor via crochet.
        # In other words, this makes crochet.setup() a no-op.
        import crochet
        crochet.no_setup()
        # Populate the region's event-loop with services and return it to
        # twistd, which will then be responsible for starting it.
        from maasserver import eventloop
        eventloop.loop.populate()
        return eventloop.loop.services
