from rest_framework.authentication import SessionAuthentication


class SessionAuthentication401(SessionAuthentication):
    """Session login that answers an anonymous caller with 401, not 403.

    DRF answers 403 when the first authenticator has no challenge header. 401 is what the
    storefront needs in order to show the login screen.
    """

    def authenticate_header(self, request) -> str:  # type: ignore[no-untyped-def]
        return "Session"
