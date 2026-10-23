from django.conf import settings
from django.utils.module_loading import import_string

from .search import SearchService


def get_search_service() -> SearchService:
    """The search implementation named in settings, so Phase 1B can swap it in."""
    service: SearchService = import_string(settings.SEARCH_BACKEND)()
    return service
