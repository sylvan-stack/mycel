"""Finite public search and private, failure-tolerant query preparation."""
from __future__ import annotations

from dataclasses import dataclass, field

from ._credentials import Credentials
from ._embedding_plan import PlanningError, load_tokenizer, plan_query
from ._errors import MycelError
from ._retrieval import _unit_vector, resolve_search_scope, validate_search
from ._safeguards import InvocationPolicy
from ._voyage import ProviderFailure, VoyageClient


@dataclass(frozen=True)
class QueryEmbedding:
    vector: tuple[float, ...] | None = field(default=None, repr=False)
    reason: str | None = None


def prepare_query(settings, query, *, credentials=None, policy=None, _client_factory=VoyageClient):
    """Embed complete query bytes once, outside every store snapshot.

    Local planning faults and sanitized provider failures leave wording search
    available. Cancellation still reaches the ordinary command boundary.
    Nothing here creates document plans, vectors or deferred result receipts.
    """
    settings.require_valid()
    validate_search(query)
    policy = InvocationPolicy('search') if policy is None else policy
    if not isinstance(policy, InvocationPolicy):
        raise MycelError('invalid_input', 'Query preparation requires an explicit invocation policy.')
    credentials = credentials or Credentials(settings, policy)
    try:
        tokenizer = load_tokenizer(settings.values['embedding']['model'])
        plan = plan_query(query, model=settings.values['embedding']['model'],
                          dimensions=settings.values['embedding']['dimensions'], tokenizer=tokenizer)
        client = _client_factory(credentials, policy, tokenizer=tokenizer)
        response = client.query(plan)
        try:
            _unit_vector(response.vectors[0])
        except MycelError:
            raise ProviderFailure('invalid_response') from None
        return QueryEmbedding(response.vectors[0])
    except ProviderFailure as error:
        if error.kind == 'cancelled':
            raise KeyboardInterrupt() from None
        return QueryEmbedding(reason=str(error))
    except PlanningError:
        return QueryEmbedding(reason='The complete query could not be planned within the verified embedding limits.')
    except MycelError:
        return QueryEmbedding(reason='Query embedding is unavailable for the current configuration.')


def handle_search(invocation):
    from ._build_identity import current_build
    from ._cli import Result, invocation_store
    from ._freshness import Deadline
    from ._search_store import search_from_store

    arguments = iter(invocation.arguments)
    query, only, k, no_fresh = None, None, 10, False
    for argument in arguments:
        if argument == '--':
            query = next(arguments)
            break
        elif argument == '--only':
            only = next(arguments)
        elif argument == '--k':
            k = int(next(arguments))
        elif argument == '--no-fresh':
            no_fresh = True
        else:
            query = argument
    validate_search(query, k, only)
    # Refuse unknown/disabled/missing scope before store or provider access.
    resolve_search_scope(invocation.settings, invocation.repositories)
    with invocation_store(invocation) as (connection, inspection):
        if inspection.dimensions != invocation.settings.values['embedding']['dimensions']:
            embedding = QueryEmbedding(reason='The store vector dimensions differ from settings. Run mycel init before using meaning search.')
        else:
            embedding = prepare_query(invocation.settings, query)
        deadline = Deadline.after(invocation.settings.values['search']['freshness_seconds'])
        return Result(search_from_store(connection, invocation.settings, query,
            invocation.repositories, query_vector=embedding.vector, meaning_reason=embedding.reason,
            k=k, only=only, deadline=deadline, no_fresh=no_fresh, build=current_build()))
