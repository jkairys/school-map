class SuburbResolverError(Exception):
    """Base for suburb_resolver errors."""


class NoMatchError(SuburbResolverError):
    """OTH autocomplete returned zero suburb candidates for the query."""


class ParseError(SuburbResolverError):
    """OTH autocomplete returned a payload we could not parse into Match objects."""


class AutocompleteUnavailableError(SuburbResolverError):
    """The OTH autocomplete endpoint is unreachable or anti-bot blocked.

    If this is raised consistently, the resolver needs to run inside the
    camoufox session (issue 10) — see PRD.
    """
